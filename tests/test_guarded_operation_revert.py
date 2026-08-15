from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from sentriface.errors import OperationRevertPostcheckError, OperationRevertRefused
from sentriface.integrity import ReadOnlyIntegrityChecker
from sentriface.revert_service import GuardedOperationRevertService
from sentriface.storage.sqlite_store import SQLiteIdentityStore


ACTOR = {"user_id": "operator-1", "display_name": "Operator"}


class GuardedOperationRevertTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = SQLiteIdentityStore(
            Path(self.temp.name) / "sentriface.db", embedding_dim=2,
        )
        self.store.initialize()
        self.service = GuardedOperationRevertService(self.store)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _safe_merge(self, operation_id: str = "merge-safe"):
        source = self.store.create_person("Same")
        target = self.store.create_person("Same")
        self.store.execute_identity_merge(
            source.person_id, target.person_id, operation_id, actor=ACTOR,
        )
        return source, target

    def _rows(self, table: str) -> list[dict]:
        with sqlite3.connect(self.store.db_path) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(row) for row in conn.execute(
                f"SELECT * FROM {table} ORDER BY rowid"
            )]

    def test_valid_merge_revert_preserves_history_journal_and_integrity(self) -> None:
        source, target = self._safe_merge()
        precondition = self.service.prepare_revert("merge-safe")
        manifests_before = {
            table: self._rows(table) for table in (
                "merge_operations", "merge_affected_items",
                "merge_conflict_resolutions", "relationship_evidence",
            )
        }
        revision_before = int(self.store.get_graph_revision()[1:])

        result = self.service.execute_revert(
            precondition,
            "revert-safe",
            actor=ACTOR,
            reason="Separate identities after verified mistaken merge",
        )

        self.assertEqual(result["postcheck_status"], "PASS")
        self.assertEqual(result["graph_revision_after"], f"g{revision_before + 2}")
        source_state = self.store.get_person_lifecycle(source.person_id)
        self.assertEqual(source_state["lifecycle_status"], "ACTIVE")
        self.assertIsNone(source_state["canonical_person_id"])
        self.assertEqual(self.store.resolve_canonical_person_id(source.person_id), source.person_id)
        self.assertEqual(self.store.resolve_canonical_person_id(target.person_id), target.person_id)
        for table, rows in manifests_before.items():
            self.assertEqual(self._rows(table), rows, table)
        original = self.store.get_operation("merge-safe")
        self.assertEqual(original["status"], "REVERTED")
        self.assertEqual(
            [item["to_status"] for item in original["status_history"]],
            ["STARTED", "COMMITTED", "REVERTED"],
        )
        self.assertEqual(
            original["status_history"][-1]["details"]["reverted_by_operation_id"],
            "revert-safe",
        )
        revert = self.store.get_operation("revert-safe")
        self.assertEqual(revert["operation_type"], "identity.merge.revert")
        self.assertEqual(revert["status"], "COMMITTED")
        report = ReadOnlyIntegrityChecker(self.store.db_path).run()
        self.assertFalse(report.findings_truncated)
        self.assertFalse([
            item for item in report.findings
            if item.severity.value in {"CRITICAL", "ERROR"}
        ])
        with self.assertRaisesRegex(OperationRevertRefused, "already been reverted"):
            self.service.prepare_revert("merge-safe")

    def test_revert_restores_graph_projection_and_p11b_remains_equivalent(self) -> None:
        source = self.store.create_person("Same")
        target = self.store.create_person("Same")
        other = self.store.create_person("Other")
        for index, person in enumerate((source, target)):
            observation = self.store.create_observation(
                f"create-observation-{index}",
                participant_ids=[person.person_id, other.person_id],
                actor=ACTOR,
            )
            self.store._finalize_observation_without_graph_evidence(
                observation.observation_id, f"finalize-observation-{index}",
            )
            self.store.record_observation_evidence(
                observation.observation_id, f"record-evidence-{index}", actor=ACTOR,
            )
        graph_before = self._rows("graph_connections")
        self.store.execute_identity_merge(
            source.person_id, target.person_id, "merge-graph", actor=ACTOR,
        )
        precondition = self.service.prepare_revert("merge-graph")
        self.service.execute_revert(
            precondition, "revert-graph", actor=ACTOR, reason="Restore graph endpoints",
        )
        self.assertEqual(self._rows("graph_connections"), graph_before)
        self.assertTrue(self.store.validate_graph_projection()["valid"])
        rebuild = self.store.rebuild_graph_projection(
            "rebuild-after-revert", actor=ACTOR, reason="Equivalence check",
        )
        self.assertFalse(rebuild["changed"])

    def test_exact_committed_retry_returns_result_without_second_mutation(self) -> None:
        self._safe_merge()
        precondition = self.service.prepare_revert("merge-safe")
        first = self.service.execute_revert(
            precondition, "revert-once", actor=ACTOR, reason="First request",
        )
        revision = self.store.get_graph_revision()
        second = self.service.execute_revert(
            precondition, "revert-once", actor=ACTOR, reason="Retry request",
        )
        self.assertEqual(first, second)
        self.assertEqual(self.store.get_graph_revision(), revision)
        self.assertEqual(
            len([row for row in self._rows("operation_journal") if row["operation_id"] == "revert-once"]),
            1,
        )

    def test_unsupported_profile_merge_archive_repair_and_rebuild_refuse(self) -> None:
        source = self.store.create_person("Source")
        target = self.store.create_person("Target")
        self.store.execute_identity_merge(
            source.person_id, target.person_id, "merge-profile", actor=ACTOR,
        )
        with self.assertRaisesRegex(OperationRevertRefused, "profile or note"):
            self.service.prepare_revert("merge-profile")

        archived_source = self.store.create_person("Archived same")
        archived_target = self.store.create_person("Archived same")
        self.store.archive_person(archived_source.person_id, "archive-before-merge", ACTOR)
        self.store.execute_identity_merge(
            archived_source.person_id,
            archived_target.person_id,
            "merge-archived-source",
            actor=ACTOR,
        )
        with self.assertRaisesRegex(OperationRevertRefused, "lifecycle/canonical"):
            self.service.prepare_revert("merge-archived-source")

        enrolled_source = self.store.create_person("Enrolled same")
        enrolled_target = self.store.create_person("Enrolled same")
        self.store.add_embedding(enrolled_source.person_id, (1.0, 0.0), 0.9)
        self.store.execute_identity_merge(
            enrolled_source.person_id,
            enrolled_target.person_id,
            "merge-biometric-change",
            actor=ACTOR,
        )
        with self.assertRaisesRegex(OperationRevertRefused, "survivor current state"):
            self.service.prepare_revert("merge-biometric-change")

        person = self.store.create_person("Lifecycle")
        self.store.archive_person(person.person_id, "archive-person", ACTOR)
        for operation_id in ("archive-person",):
            with self.assertRaisesRegex(OperationRevertRefused, "not in the revert whitelist"):
                self.service.prepare_revert(operation_id)
        self.store.rebuild_graph_projection(
            "graph-rebuild", actor=ACTOR, reason="No-op audit",
        )
        with self.assertRaisesRegex(OperationRevertRefused, "not in the revert whitelist"):
            self.service.prepare_revert("graph-rebuild")

    def test_later_dependency_refuses_without_mutation(self) -> None:
        _, target = self._safe_merge()
        self.store.update_person_preferences(
            target.person_id, "later-preference", favorite=True, actor=ACTOR,
        )
        before = self._rows("operation_journal")
        with self.assertRaisesRegex(OperationRevertRefused, "Later dependent"):
            self.service.prepare_revert("merge-safe")
        self.assertEqual(self._rows("operation_journal"), before)

    def test_stale_token_and_changed_entity_refuse_with_zero_mutation(self) -> None:
        _, target = self._safe_merge()
        precondition = self.service.prepare_revert("merge-safe")
        before = self._rows("operation_journal")
        with self.assertRaisesRegex(OperationRevertRefused, "fingerprint"):
            self.service.execute_revert(
                replace(precondition, fingerprint="0" * 64),
                "revert-bad-token", actor=ACTOR, reason="Bad token",
            )
        self.assertEqual(self._rows("operation_journal"), before)

        self.store.update_person_preferences(
            target.person_id, "later-change", favorite=True, actor=ACTOR,
        )
        after_change = self._rows("operation_journal")
        with self.assertRaises(OperationRevertRefused):
            self.service.execute_revert(
                precondition, "revert-stale", actor=ACTOR, reason="Stale token",
            )
        self.assertEqual(self._rows("operation_journal"), after_change)
        self.assertIsNone(self.store.get_operation("revert-stale"))

    def test_malformed_journal_refuses_all_revert_preparation(self) -> None:
        self._safe_merge()
        with sqlite3.connect(self.store.db_path) as conn:
            conn.execute(
                """
                INSERT INTO operation_journal(
                    operation_id, operation_type, status, actor, context,
                    affected_entities, details, created_at
                ) VALUES ('malformed-operation', 'test.malformed', 'COMMITTED',
                          '{}', '{}', '[]', '{}', '2026-01-01T00:00:00+00:00')
                """
            )
        before = self._rows("operation_journal")
        with self.assertRaisesRegex(OperationRevertRefused, "clean authoritative"):
            self.service.prepare_revert("merge-safe")
        self.assertEqual(self._rows("operation_journal"), before)

    def test_failure_seams_roll_back_authority_graph_and_original_status(self) -> None:
        seams = (
            "after_journal_started", "during_mutation", "during_graph_update",
            "during_validation", "before_commit",
        )
        for seam in seams:
            with self.subTest(seam=seam):
                self.tearDown()
                self.setUp()
                source, target = self._safe_merge(f"merge-{seam}")
                precondition = self.service.prepare_revert(f"merge-{seam}")
                source_before = self.store.get_person_lifecycle(source.person_id)
                target_before = self.store.get_person_lifecycle(target.person_id)
                graph_before = self._rows("graph_connections")
                revision_before = self.store.get_graph_revision()
                manifest_before = self._rows("merge_operations")

                def fail(current: str) -> None:
                    if current == seam:
                        raise RuntimeError(f"injected {seam}")

                with self.assertRaisesRegex(RuntimeError, seam):
                    self.service.execute_revert(
                        precondition,
                        f"revert-{seam}",
                        actor=ACTOR,
                        reason="Failure injection",
                        failure_injector=fail,
                    )
                self.assertEqual(self.store.get_person_lifecycle(source.person_id), source_before)
                self.assertEqual(self.store.get_person_lifecycle(target.person_id), target_before)
                self.assertEqual(self._rows("graph_connections"), graph_before)
                self.assertEqual(self.store.get_graph_revision(), revision_before)
                self.assertEqual(self._rows("merge_operations"), manifest_before)
                self.assertEqual(self.store.get_operation(f"merge-{seam}")["status"], "COMMITTED")
                failed = self.store.get_operation(f"revert-{seam}")
                self.assertEqual(failed["status"], "FAILED")
                self.assertTrue(failed["details"]["transaction_rolled_back"])
                self.assertTrue(self.store.validate_graph_projection()["valid"])

    def test_failed_postcheck_is_reported_without_rewriting_committed_history(self) -> None:
        source, _ = self._safe_merge()
        precondition = self.service.prepare_revert("merge-safe")
        stale_report = replace(
            ReadOnlyIntegrityChecker(self.store.db_path).run(),
            findings_truncated=True,
        )
        with patch("sentriface.revert_service.ReadOnlyIntegrityChecker") as checker:
            checker.return_value.run.return_value = stale_report
            with self.assertRaises(OperationRevertPostcheckError):
                self.service.execute_revert(
                    precondition,
                    "revert-postcheck",
                    actor=ACTOR,
                    reason="Postcheck injection",
                )
        self.assertEqual(
            self.store.get_person_lifecycle(source.person_id)["lifecycle_status"],
            "ACTIVE",
        )
        self.assertEqual(self.store.get_operation("merge-safe")["status"], "REVERTED")
        self.assertEqual(self.store.get_operation("revert-postcheck")["status"], "COMMITTED")


if __name__ == "__main__":
    unittest.main()
