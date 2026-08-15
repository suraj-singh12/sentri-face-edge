from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from sentriface.api_server import (
    SentriFaceApiHandler,
    _required_capability,
    _validate_integrity_recovery_payload,
)
from sentriface.auth import ROLE_CAPABILITIES
from sentriface.cli import build_dev_engine
from sentriface.errors import GraphProjectionPostcheckError
from sentriface.integrity import (
    FutureIntegrityHandling,
    IntegrityFinding,
    IntegrityReport,
    IntegritySeverity,
)
from sentriface.integrity_recovery_service import (
    IntegrityRecoveryApplication,
    RecoveryTokenError,
)
from sentriface.models import utc_now
from sentriface.storage.sqlite_store import (
    _begin_journal_operation,
    _transition_journal_operation,
)


INTEGRITY_ROUTES = (
    ("POST", "/api/integrity/check"),
    ("POST", "/api/integrity/graph-rebuild/prepare"),
    ("POST", "/api/integrity/graph-rebuild/execute"),
    ("POST", "/api/integrity/repairs/r01/prepare"),
    ("POST", "/api/integrity/repairs/r01/execute"),
    ("POST", "/api/integrity/repairs/r02/prepare"),
    ("POST", "/api/integrity/repairs/r02/execute"),
    ("GET", "/api/integrity/revert-operations"),
    ("POST", "/api/integrity/reverts/prepare"),
    ("POST", "/api/integrity/reverts/execute"),
)
ACTOR = {
    "user_id": "administrator-1",
    "username": "owner",
    "display_name": "Owner",
    "roles": ["administrator"],
}


class P11ERecoveryApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.engine = build_dev_engine(Path(self.temp.name) / "data")
        self.engine.initialize()
        self.application = IntegrityRecoveryApplication(
            self.engine,
            token_secret="test-only-p11e-token-secret",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_every_route_explicitly_requires_recovery_and_only_admin_has_capability(self) -> None:
        for method, route in INTEGRITY_ROUTES:
            self.assertEqual(_required_capability(method, route), "recovery", route)
        for role in ("viewer", "operator", "custodian", "technician"):
            self.assertNotIn("recovery", ROLE_CAPABILITIES[role])
        self.assertIn("recovery", ROLE_CAPABILITIES["administrator"])

    def test_recovery_routes_bypass_recognition_model_readiness(self) -> None:
        handler = object.__new__(SentriFaceApiHandler)
        handler.server = SimpleNamespace(
            runtime="onnx",
            model_error="Recognition models are intentionally unavailable",
            models_available=lambda: False,
        )
        handler._json = Mock()
        for _, route in INTEGRITY_ROUTES:
            self.assertFalse(handler._reject_model_readiness(route), route)
        handler._json.assert_not_called()

    def test_administrator_can_run_bounded_integrity_report(self) -> None:
        report = self.application.check()
        self.assertEqual(report["contract"], "sentriface.integrity-recovery")
        self.assertEqual(report["status"], "PASS")
        self.assertTrue(report["report_token"])
        serialized = json.dumps(report)
        self.assertNotIn(str(self.engine.store.db_path), serialized)
        self.assertNotIn("database_key", serialized)

    def test_dto_redacts_sensitive_evidence_and_unsupported_findings_have_no_action(self) -> None:
        finding = IntegrityFinding(
            invariant_id="P11-IDENTITY-001",
            domain="IDENTITY",
            severity=IntegritySeverity.CRITICAL,
            message="Lifecycle state is invalid",
            entity_ids=(("person_id", "person-1"),),
            evidence=(
                ("media_path", "/private/secret/image.jpg"),
                ("diagnostic", "raw sqlite diagnostic"),
                ("note_content", "private note"),
                ("embedding", "vector"),
                ("status", "invalid"),
            ),
            future_handling=FutureIntegrityHandling.STRUCTURED_REPAIR,
        )
        report = IntegrityReport(
            started_at="2026-08-15T00:00:00+00:00",
            completed_at="2026-08-15T00:00:01+00:00",
            schema_version=28,
            graph_revision="g1",
            status="CRITICAL",
            checks_run=("P11-IDENTITY-001",),
            findings=(finding,),
            counts_by_severity={"CRITICAL": 1, "ERROR": 0, "WARNING": 0, "INFO": 0},
        )
        with patch.object(self.application, "_run_check", return_value=report):
            payload = self.application.check()
        serialized = json.dumps(payload)
        for secret in ("/private/secret", "sqlite diagnostic", "private note", "vector"):
            self.assertNotIn(secret, serialized)
        item = payload["findings"][0]
        self.assertIsNone(item["action_hint"])
        self.assertEqual(item["classification"], "MANUAL_REVIEW")
        self.assertEqual(item["evidence"], [{"name": "status", "value": "invalid"}])

    def test_execution_requires_preparation_and_tampered_token_maps_to_409_without_mutation(self) -> None:
        operation_id = str(uuid.uuid4())
        before = self.engine.list_recent_operations(500)
        with self.assertRaises(RecoveryTokenError):
            self.application.execute_r01(
                "not-a-prepared-token",
                operation_id,
                actor=ACTOR,
                reason="Must refuse",
                source="/api/integrity/repairs/r01/execute",
            )
        self.assertEqual(self.engine.list_recent_operations(500), before)
        self.assertIsNone(self.engine.get_operation(operation_id))

        handler = object.__new__(SentriFaceApiHandler)
        handler.path = "/api/integrity/repairs/r01/execute"
        handler.server = SimpleNamespace(log_event=Mock())
        handler._json = Mock()
        handler._error(RecoveryTokenError("The preparation token fingerprint changed"))
        payload = handler._json.call_args.args[0]
        self.assertEqual(handler._json.call_args.kwargs["status"], 409)
        self.assertEqual(payload["code"], "stale_precondition")
        self.assertFalse(payload["committed"])

        with self.assertRaisesRegex(Exception, "server-defined fields"):
            _validate_integrity_recovery_payload(
                "/api/integrity/repairs/r01/execute",
                {
                    "token": "valid-shape",
                    "operation_id": str(uuid.uuid4()),
                    "reason": "No patches",
                    "person_id": "client-selected-target",
                },
            )

    def test_graph_prepare_execute_and_exact_idempotent_retry(self) -> None:
        self._create_graph_drift()
        report = self.application.check()
        action = next(item for item in report["actions"] if item["action_type"] == "GRAPH_REBUILD")
        plan = self.application.prepare_graph_rebuild(
            report["report_token"], action["action_id"],
        )
        operation_id = str(uuid.uuid4())
        first = self.application.execute_graph_rebuild(
            plan["token"], operation_id, actor=ACTOR,
            reason="Repair derived drift", source="/api/integrity/graph-rebuild/execute",
        )
        second = self.application.execute_graph_rebuild(
            plan["token"], operation_id, actor=ACTOR,
            reason="Repair derived drift", source="/api/integrity/graph-rebuild/execute",
        )
        self.assertTrue(first["committed"])
        self.assertEqual(first["operation_result"], second["operation_result"])
        self.assertEqual(second["integrity_report"]["status"], "PASS")
        self.assertEqual(self.engine.get_operation(operation_id)["status"], "COMMITTED")

    def test_r01_r02_and_revert_delegate_only_through_prepared_domain_tokens(self) -> None:
        store = self.engine.store

        source = store.create_person("R01 source")
        survivor = store.create_person("R01 survivor")
        store.execute_identity_merge(
            source.person_id, survivor.person_id, str(uuid.uuid4()), actor=ACTOR,
        )
        store.archive_person(survivor.person_id, str(uuid.uuid4()), ACTOR)
        report = self.application.check()
        action = next(item for item in report["actions"] if item["action_type"] == "R01")
        plan = self.application.prepare_r01(report["report_token"], action["action_id"])
        r01 = self.application.execute_r01(
            plan["token"], str(uuid.uuid4()), actor=ACTOR,
            reason="Restore the proven survivor", source="/api/integrity/repairs/r01/execute",
        )
        self.assertTrue(r01["committed"])
        self.assertEqual(r01["integrity_report"]["status"], "PASS")

        owner = store.create_person("Note owner")
        referenced = store.create_person("Note reference")
        note = store.create_note(
            owner.person_id,
            "Reference",
            str(uuid.uuid4()),
            mentioned_person_ids=[referenced.person_id],
            actor=ACTOR,
        )
        with store._connect() as connection:
            mention = connection.execute(
                "SELECT mention_id FROM note_mentions WHERE note_id=? AND active=1",
                (note.note_id,),
            ).fetchone()
            drift_operation = str(uuid.uuid4())
            _begin_journal_operation(
                connection, "test.p11e.missing-note-evidence",
                operation_id=drift_operation, actor=ACTOR,
            )
            connection.execute(
                """
                UPDATE relationship_evidence
                SET active=0, deactivated_operation_id=?, deactivated_at=?
                WHERE evidence_type='NOTE_REFERENCE' AND source_entity_id=? AND active=1
                """,
                (drift_operation, utc_now(), mention["mention_id"]),
            )
            _transition_journal_operation(connection, drift_operation, "COMMITTED", {})
        report = self.application.check()
        action = next(item for item in report["actions"] if item["action_type"] == "R02")
        plan = self.application.prepare_r02(report["report_token"], action["action_id"])
        r02 = self.application.execute_r02(
            plan["token"], str(uuid.uuid4()), actor=ACTOR,
            reason="Restore note evidence", source="/api/integrity/repairs/r02/execute",
        )
        self.assertTrue(r02["committed"])
        self.assertEqual(r02["integrity_report"]["status"], "PASS")

        revert_source = store.create_person("Same revert profile")
        revert_target = store.create_person("Same revert profile")
        original_operation_id = str(uuid.uuid4())
        store.execute_identity_merge(
            revert_source.person_id,
            revert_target.person_id,
            original_operation_id,
            actor=ACTOR,
        )
        operation_list = self.application.list_revert_operations()
        self.assertIn(
            original_operation_id,
            {item["operation_id"] for item in operation_list["operations"]},
        )
        self.assertTrue(all(
            item["eligibility"] == "PREPARATION_REQUIRED"
            for item in operation_list["operations"]
        ))
        plan = self.application.prepare_revert(original_operation_id)
        reverted = self.application.execute_revert(
            plan["token"], str(uuid.uuid4()), actor=ACTOR,
            reason="Restore independent identity", source="/api/integrity/reverts/execute",
        )
        self.assertTrue(reverted["committed"])
        self.assertEqual(reverted["integrity_report"]["status"], "PASS")

    def test_committed_postcheck_failure_has_distinct_typed_response(self) -> None:
        report = self.application._run_check()
        committed_result = {"operation_id": "committed-operation", "changed": True}
        error = GraphProjectionPostcheckError(committed_result, report)
        payload = self.application.postcheck_failure_payload(
            "GRAPH_REBUILD", error.result, error.report,
        )
        self.assertTrue(payload["committed"])
        self.assertEqual(payload["code"], "postcheck_failed_after_commit")
        self.assertEqual(payload["operation_result"]["operation_id"], "committed-operation")
        self.assertIn("integrity_report", payload)

    def _create_graph_drift(self) -> None:
        store = self.engine.store
        first = store.create_person("Graph first")
        second = store.create_person("Graph second")
        observation = store.create_observation(
            "p11e-observation-create",
            participant_ids=[first.person_id, second.person_id],
        )
        store._finalize_observation_without_graph_evidence(
            observation.observation_id,
            "p11e-observation-finalize",
        )
        store.record_observation_evidence(
            observation.observation_id,
            "p11e-observation-evidence",
        )
        with sqlite3.connect(store.db_path) as connection:
            connection.execute("DELETE FROM graph_connections")
            connection.commit()


if __name__ == "__main__":
    unittest.main()
