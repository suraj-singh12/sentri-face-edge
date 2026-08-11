from __future__ import annotations

import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from sentriface.errors import StructuredRepairPostcheckError, StructuredRepairRefused
from sentriface.integrity import ReadOnlyIntegrityChecker
from sentriface.models import NoteReferenceRepairPlan, utc_now
from sentriface.storage.sqlite_store import (
    SQLiteIdentityStore,
    _begin_journal_operation,
    _insert_relationship_evidence,
    _replace_graph_projection,
    _transition_journal_operation,
)
from sentriface.structured_repair_service import StructuredRepairService


ACTOR = {"user_id": "operator-1", "display_name": "Operator"}


class StructuredRepairR02Test(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = SQLiteIdentityStore(
            Path(self.temp.name) / "sentriface.db", embedding_dim=2,
        )
        self.store.initialize()
        self.service = StructuredRepairService(self.store)
        self.owner = self.store.create_person("Owner")
        self.person = self.store.create_person("Referenced")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _rows(self, table: str) -> list[dict]:
        with sqlite3.connect(self.store.db_path) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(row) for row in conn.execute(
                f"SELECT * FROM {table} ORDER BY rowid"
            )]

    def _report(self):
        return ReadOnlyIntegrityChecker(self.store.db_path).run()

    def _assert_clean(self) -> None:
        report = self._report()
        self.assertFalse(report.findings_truncated)
        self.assertEqual([
            (item.invariant_id, item.message)
            for item in report.findings
            if item.severity.value in {"CRITICAL", "ERROR"}
        ], [])

    def _note(self):
        return self.store.create_note(
            self.owner.person_id,
            "Referenced",
            "note-create",
            mentioned_person_ids=[self.person.person_id],
            actor=ACTOR,
        )

    def _active_mention(self, note_id: str) -> sqlite3.Row:
        with self.store._connect() as conn:
            return conn.execute(
                """
                SELECT m.*, n.owner_person_id FROM note_mentions m
                JOIN notes n USING(note_id)
                WHERE m.note_id=? AND m.active=1
                """,
                (note_id,),
            ).fetchone()

    def _retire_current_without_revision_change(self, note_id: str) -> None:
        with self.store._connect() as conn:
            mention = conn.execute(
                "SELECT * FROM note_mentions WHERE note_id=? AND active=1",
                (note_id,),
            ).fetchone()
            latest = conn.execute(
                """
                SELECT revision_id FROM note_revisions
                WHERE note_id=? ORDER BY revision_number DESC LIMIT 1
                """,
                (note_id,),
            ).fetchone()[0]
            _begin_journal_operation(
                conn, "test.r02.missing-occurrence", operation_id="drift-retire",
                actor=ACTOR,
            )
            changed_at = utc_now()
            conn.execute(
                """
                UPDATE note_mentions
                SET active=0, retired_revision_id=?, retired_operation_id='drift-retire',
                    retired_at=? WHERE mention_id=?
                """,
                (latest, changed_at, mention["mention_id"]),
            )
            conn.execute(
                """
                UPDATE relationship_evidence
                SET active=0, deactivated_operation_id='drift-retire', deactivated_at=?
                WHERE evidence_type='NOTE_REFERENCE' AND source_entity_id=? AND active=1
                """,
                (changed_at, mention["mention_id"]),
            )
            _transition_journal_operation(conn, "drift-retire", "COMMITTED", {})

    def _retire_active_evidence(
        self, note_id: str, operation_id: str = "drift-evidence-retire",
    ) -> None:
        mention = self._active_mention(note_id)
        with self.store._connect() as conn:
            _begin_journal_operation(
                conn, "test.r02.missing-evidence", operation_id=operation_id,
                actor=ACTOR,
            )
            conn.execute(
                """
                UPDATE relationship_evidence
                SET active=0, deactivated_operation_id=?,
                    deactivated_at=?
                WHERE evidence_type='NOTE_REFERENCE' AND source_entity_id=? AND active=1
                """,
                (operation_id, utc_now(), mention["mention_id"]),
            )
            _transition_journal_operation(
                conn, operation_id, "COMMITTED", {},
            )

    def _append_duplicate_evidence(self, note_id: str) -> str:
        mention = self._active_mention(note_id)
        with self.store._connect() as conn:
            _begin_journal_operation(
                conn, "test.r02.duplicate", operation_id="drift-duplicate", actor=ACTOR,
            )
            evidence_id = _insert_relationship_evidence(
                conn,
                evidence_type="NOTE_REFERENCE",
                source_entity_type="NOTE",
                source_entity_id=str(mention["mention_id"]),
                evidence_revision_id="drift-duplicate",
                source_person_id=self.owner.person_id,
                target_person_id=self.person.person_id,
                relationship_type="REFERENCES",
                directionality="DIRECTED",
                source="test",
                created_operation_id="drift-duplicate",
                created_at=utc_now(),
            )
            _transition_journal_operation(conn, "drift-duplicate", "COMMITTED", {})
            return evidence_id

    def _reactivate_retired_evidence(self, note_id: str) -> None:
        with sqlite3.connect(self.store.db_path) as conn:
            conn.execute("DROP TRIGGER relationship_evidence_deactivation_only")
            conn.execute(
                """
                UPDATE relationship_evidence
                SET active=1, deactivated_operation_id=NULL, deactivated_at=NULL
                WHERE evidence_type='NOTE_REFERENCE'
                  AND source_entity_id IN (
                    SELECT mention_id FROM note_mentions WHERE note_id=?
                  )
                """,
                (note_id,),
            )

    def test_append_occurrence_and_evidence_preserves_retired_history(self) -> None:
        note = self._note()
        self._retire_current_without_revision_change(note.note_id)
        retired_before = self._rows("note_mentions")
        evidence_before = self._rows("relationship_evidence")
        revisions_before = self._rows("note_revisions")
        mentions_before = self._rows("note_revision_mentions")
        pre = self.service.prepare_note_reference_reconciliation(
            note.note_id, self.person.person_id,
        )
        self.assertEqual(pre.plan, NoteReferenceRepairPlan.APPEND_OCCURRENCE_AND_EVIDENCE)
        revision = int(self.store.get_graph_revision()[1:])
        result = self.service.reconcile_note_reference_state(
            pre, "repair-append-occurrence", actor=ACTOR, reason="Reconcile current support",
        )
        self.assertEqual(result["postcheck_status"], "PASS")
        self.assertEqual(result["occurrences_appended"], 1)
        self.assertEqual(result["evidence_appended"], 1)
        self.assertEqual(result["graph_revision_after"], f"g{revision + 1}")
        self.assertEqual(self._rows("note_mentions")[:1], retired_before)
        self.assertEqual(self._rows("relationship_evidence")[:1], evidence_before)
        self.assertEqual(self._rows("note_revisions"), revisions_before)
        self.assertEqual(self._rows("note_revision_mentions"), mentions_before)
        operation = self.store.get_operation("repair-append-occurrence")
        self.assertEqual(operation["operation_type"], "integrity.repair.note-reference.reconcile")
        self.assertEqual(operation["status"], "COMMITTED")
        self.assertEqual(
            [item["to_status"] for item in operation["status_history"]],
            ["STARTED", "COMMITTED"],
        )
        self.assertNotIn("content", str(operation["details"]).lower())
        self.assertLessEqual(len(operation["affected_entities"]), 50)
        self._assert_clean()

    def test_retire_stale_occurrence_and_active_evidence(self) -> None:
        note = self._note()
        self.store.update_note(
            note.note_id, "none", "remove-mention", mentioned_person_ids=[], actor=ACTOR,
        )
        with sqlite3.connect(self.store.db_path) as conn:
            conn.execute("DROP TRIGGER note_mentions_deactivation_only")
            conn.execute("DROP TRIGGER relationship_evidence_deactivation_only")
            conn.execute(
                """
                UPDATE note_mentions SET active=1, retired_revision_id=NULL,
                    retired_operation_id=NULL, retired_at=NULL WHERE note_id=?
                """,
                (note.note_id,),
            )
            conn.execute(
                """
                UPDATE relationship_evidence SET active=1,
                    deactivated_operation_id=NULL, deactivated_at=NULL
                WHERE evidence_type='NOTE_REFERENCE'
                """
            )
        pre = self.service.prepare_note_reference_reconciliation(
            note.note_id, self.person.person_id,
        )
        self.assertEqual(pre.plan, NoteReferenceRepairPlan.RETIRE_OCCURRENCE_AND_EVIDENCE)
        revision = int(self.store.get_graph_revision()[1:])
        result = self.service.reconcile_note_reference_state(
            pre, "repair-retire-occurrence", actor=ACTOR, reason="Retire stale current state",
        )
        self.assertEqual(result["occurrences_retired"], 1)
        self.assertEqual(result["evidence_retired"], 1)
        self.assertEqual(result["graph_revision_after"], f"g{revision + 1}")
        self._assert_clean()

    def test_occurrence_only_retirement_does_not_churn_graph_revision(self) -> None:
        note = self._note()
        self.store.update_note(
            note.note_id, "none", "remove-mention", mentioned_person_ids=[], actor=ACTOR,
        )
        evidence_before = self._rows("relationship_evidence")
        with sqlite3.connect(self.store.db_path) as conn:
            conn.execute("DROP TRIGGER note_mentions_deactivation_only")
            conn.execute(
                """
                UPDATE note_mentions SET active=1, retired_revision_id=NULL,
                    retired_operation_id=NULL, retired_at=NULL WHERE note_id=?
                """,
                (note.note_id,),
            )
        pre = self.service.prepare_note_reference_reconciliation(
            note.note_id, self.person.person_id,
        )
        revision = self.store.get_graph_revision()
        result = self.service.reconcile_note_reference_state(
            pre, "repair-occurrence-only", actor=ACTOR, reason="Retire stale occurrence",
        )
        self.assertEqual(result["evidence_retired"], 0)
        self.assertEqual(result["graph_revision_after"], revision)
        self.assertEqual(self._rows("relationship_evidence"), evidence_before)
        self._assert_clean()

    def test_append_missing_evidence(self) -> None:
        note = self._note()
        self._retire_active_evidence(note.note_id)
        retired_before = self._rows("relationship_evidence")
        pre = self.service.prepare_note_reference_reconciliation(
            note.note_id, self.person.person_id,
        )
        self.assertEqual(pre.plan, NoteReferenceRepairPlan.APPEND_EVIDENCE)
        result = self.service.reconcile_note_reference_state(
            pre, "repair-append-evidence", actor=ACTOR, reason="Restore current evidence",
        )
        self.assertEqual(result["evidence_appended"], 1)
        self.assertEqual(self._rows("relationship_evidence")[:1], retired_before)
        self._assert_clean()

    def test_replace_all_duplicate_active_evidence(self) -> None:
        note = self._note()
        self._append_duplicate_evidence(note.note_id)
        old_ids = {row["evidence_id"] for row in self._rows("relationship_evidence")}
        pre = self.service.prepare_note_reference_reconciliation(
            note.note_id, self.person.person_id,
        )
        self.assertEqual(
            pre.plan, NoteReferenceRepairPlan.REPLACE_DUPLICATE_ACTIVE_EVIDENCE,
        )
        result = self.service.reconcile_note_reference_state(
            pre, "repair-duplicates", actor=ACTOR, reason="Replace duplicate current evidence",
        )
        self.assertEqual(result["evidence_retired"], 2)
        self.assertEqual(result["evidence_appended"], 1)
        rows = self._rows("relationship_evidence")
        self.assertTrue(all(not row["active"] for row in rows if row["evidence_id"] in old_ids))
        self.assertEqual(sum(row["active"] for row in rows), 1)
        self._assert_clean()

    def test_retire_stale_evidence_from_inactive_occurrence(self) -> None:
        note = self._note()
        self.store.update_note(
            note.note_id, "none", "remove-mention", mentioned_person_ids=[], actor=ACTOR,
        )
        occurrence_before = self._rows("note_mentions")
        self._reactivate_retired_evidence(note.note_id)
        pre = self.service.prepare_note_reference_reconciliation(
            note.note_id, self.person.person_id,
        )
        self.assertEqual(pre.plan, NoteReferenceRepairPlan.RETIRE_STALE_EVIDENCE)
        result = self.service.reconcile_note_reference_state(
            pre, "repair-stale-evidence", actor=ACTOR, reason="Retire stale support",
        )
        self.assertEqual(result["evidence_retired"], 1)
        self.assertEqual(self._rows("note_mentions"), occurrence_before)
        self._assert_clean()

    def test_repeated_history_and_multiple_replacements_remain_immutable(self) -> None:
        note = self._note()
        self.store.update_note(
            note.note_id, "none", "history-remove", mentioned_person_ids=[], actor=ACTOR,
        )
        self.store.update_note(
            note.note_id, "again", "history-readd",
            mentioned_person_ids=[self.person.person_id], actor=ACTOR,
        )
        for index in range(3):
            self._retire_active_evidence(
                note.note_id, f"drift-evidence-retire-{index}",
            )
            pre = self.service.prepare_note_reference_reconciliation(
                note.note_id, self.person.person_id,
            )
            history_before = [
                row for row in self._rows("relationship_evidence") if not row["active"]
            ]
            self.service.reconcile_note_reference_state(
                pre,
                f"repair-history-{index}",
                actor=ACTOR,
                reason="Append current replacement",
            )
            self.assertEqual(
                [row for row in self._rows("relationship_evidence") if not row["active"]],
                history_before,
            )
        self.assertEqual(sum(row["active"] for row in self._rows("relationship_evidence")), 1)
        self._assert_clean()

    def test_co_observed_and_manual_support_remain_byte_identical(self) -> None:
        note = self._note()
        observation = self.store.create_observation(
            "support-observation", participant_ids=[self.owner.person_id, self.person.person_id],
        )
        self.store._finalize_observation_without_graph_evidence(
            observation.observation_id, "support-finalize",
        )
        self.store.record_observation_evidence(
            observation.observation_id, "support-co-observed", actor=ACTOR,
        )
        with self.store._connect() as conn:
            _begin_journal_operation(
                conn, "test.manual-association", operation_id="support-manual", actor=ACTOR,
            )
            _insert_relationship_evidence(
                conn,
                evidence_type="MANUAL_ASSOCIATION",
                source_entity_type="MANUAL_ASSERTION",
                source_entity_id="support-assertion",
                evidence_revision_id="support-manual",
                source_person_id=self.owner.person_id,
                target_person_id=self.person.person_id,
                relationship_type="ASSOCIATED_WITH",
                directionality="UNDIRECTED",
                source="test",
                created_operation_id="support-manual",
                created_at=utc_now(),
            )
            _replace_graph_projection(conn)
            _transition_journal_operation(conn, "support-manual", "COMMITTED", {})
        other_before = [
            row for row in self._rows("relationship_evidence")
            if row["evidence_type"] != "NOTE_REFERENCE"
        ]
        self._retire_active_evidence(note.note_id)
        pre = self.service.prepare_note_reference_reconciliation(
            note.note_id, self.person.person_id,
        )
        self.service.reconcile_note_reference_state(
            pre, "repair-with-other-support", actor=ACTOR, reason="Restore note support",
        )
        self.assertEqual([
            row for row in self._rows("relationship_evidence")
            if row["evidence_type"] != "NOTE_REFERENCE"
        ], other_before)
        types = {
            evidence_type
            for row in self.store.get_global_graph_projection().connections
            for evidence_type in row.evidence_types
        }
        self.assertEqual(
            types, {"NOTE_REFERENCE", "CO_OBSERVED", "MANUAL_ASSOCIATION"},
        )
        self._assert_clean()

    def test_canonical_self_collapse_still_advances_once(self) -> None:
        note = self._note()
        self.store.execute_identity_merge(
            self.owner.person_id, self.person.person_id, "collapse-merge", actor=ACTOR,
        )
        self._retire_active_evidence(note.note_id)
        self.assertEqual(self.store.get_global_graph_projection().connections, ())
        pre = self.service.prepare_note_reference_reconciliation(
            note.note_id, self.person.person_id,
        )
        revision = int(self.store.get_graph_revision()[1:])
        result = self.service.reconcile_note_reference_state(
            pre, "repair-collapsed", actor=ACTOR, reason="Restore collapsed provenance",
        )
        self.assertEqual(result["graph_revision_after"], f"g{revision + 1}")
        self.assertEqual(self.store.get_global_graph_projection().connections, ())
        self._assert_clean()

    def test_correction_then_merge_and_merge_then_correction_remain_valid(self) -> None:
        note = self._note()
        first = self.store.create_person("First")
        second = self.store.create_person("Second")
        third = self.store.create_person("Third")
        fourth = self.store.create_person("Fourth")
        first_observation = self.store.create_observation(
            "first-observation", participant_ids=[first.person_id, second.person_id],
        )
        self.store._finalize_observation_without_graph_evidence(
            first_observation.observation_id, "first-finalize",
        )
        self.store.record_observation_evidence(
            first_observation.observation_id, "first-evidence", actor=ACTOR,
        )
        self.store.correct_observation_identity(
            first_observation.observation_id,
            first.person_id,
            third.person_id,
            "correction-then-merge",
            actor=ACTOR,
        )
        self.store.execute_identity_merge(
            third.person_id, second.person_id, "merge-after-correction", actor=ACTOR,
        )
        second_observation = self.store.create_observation(
            "second-observation", participant_ids=[fourth.person_id, self.person.person_id],
        )
        self.store._finalize_observation_without_graph_evidence(
            second_observation.observation_id, "second-finalize",
        )
        self.store.record_observation_evidence(
            second_observation.observation_id, "second-evidence", actor=ACTOR,
        )
        survivor = self.store.create_person("Survivor")
        self.store.execute_identity_merge(
            fourth.person_id, survivor.person_id, "merge-before-correction", actor=ACTOR,
        )
        self.store.correct_observation_identity(
            second_observation.observation_id,
            survivor.person_id,
            self.owner.person_id,
            "correction-after-merge",
            actor=ACTOR,
        )
        self._retire_active_evidence(note.note_id)
        pre = self.service.prepare_note_reference_reconciliation(
            note.note_id, self.person.person_id,
        )
        self.service.reconcile_note_reference_state(
            pre, "repair-after-transformations", actor=ACTOR, reason="Reconcile note support",
        )
        self._assert_clean()

    def test_committed_retry_and_stale_or_changed_token_rules(self) -> None:
        note = self._note()
        self._retire_active_evidence(note.note_id)
        pre = self.service.prepare_note_reference_reconciliation(
            note.note_id, self.person.person_id,
        )
        first = self.service.reconcile_note_reference_state(
            pre, "repair-once", actor=ACTOR, reason="Repair once",
        )
        second = self.service.reconcile_note_reference_state(
            pre, "repair-once", actor=ACTOR, reason="Exact retry",
        )
        self.assertEqual(first, second)
        with self.assertRaises(KeyError):
            self.service.reconcile_note_reference_state(
                replace(pre, finding_fingerprint="f" * 64),
                "repair-once", actor=ACTOR, reason="Operation ID misuse",
            )
        with self.assertRaises(StructuredRepairRefused):
            self.service.reconcile_note_reference_state(
                pre, "repair-new", actor=ACTOR, reason="Stale retry",
            )
        with self.assertRaises(StructuredRepairRefused):
            self.service.reconcile_note_reference_state(
                replace(pre, finding_fingerprint="0" * 64),
                "repair-changed-token", actor=ACTOR, reason="Changed token",
            )

    def test_failed_id_cannot_be_reused_and_fresh_diagnosis_can_retry(self) -> None:
        note = self._note()
        self._retire_active_evidence(note.note_id)
        pre = self.service.prepare_note_reference_reconciliation(
            note.note_id, self.person.person_id,
        )

        def inject(phase: str) -> None:
            if phase == "after_evidence_append":
                raise RuntimeError("injected append failure")

        with patch(
            "sentriface.storage.sqlite_store._r02_failure_checkpoint",
            side_effect=inject,
        ):
            with self.assertRaisesRegex(RuntimeError, "append failure"):
                self.service.reconcile_note_reference_state(
                    pre, "repair-failed-id", actor=ACTOR, reason="Failure retry test",
                )
        with self.assertRaises(RuntimeError):
            self.service.reconcile_note_reference_state(
                pre, "repair-failed-id", actor=ACTOR, reason="Cannot reuse failed ID",
            )
        with self.assertRaises(StructuredRepairRefused):
            self.service.reconcile_note_reference_state(
                pre, "repair-old-diagnosis", actor=ACTOR, reason="Old diagnosis is stale",
            )
        refreshed = self.service.prepare_note_reference_reconciliation(
            note.note_id, self.person.person_id,
        )
        result = self.service.reconcile_note_reference_state(
            refreshed, "repair-fresh-id", actor=ACTOR, reason="Fresh diagnosis retry",
        )
        self.assertEqual(result["postcheck_status"], "PASS")

    def test_postcheck_failure_is_surfaced_without_second_repair(self) -> None:
        note = self._note()
        self._retire_active_evidence(note.note_id)
        pre = self.service.prepare_note_reference_reconciliation(
            note.note_id, self.person.person_id,
        )
        stale_report = self._report()
        journal_count = len(self._rows("operation_journal"))
        with patch(
            "sentriface.structured_repair_service.ReadOnlyIntegrityChecker"
        ) as checker:
            checker.return_value.run.return_value = stale_report
            with self.assertRaises(StructuredRepairPostcheckError):
                self.service.reconcile_note_reference_state(
                    pre, "repair-postcheck", actor=ACTOR, reason="Post-check test",
                )
        self.assertEqual(len(self._rows("operation_journal")), journal_count + 1)
        self.assertEqual(self.store.get_operation("repair-postcheck")["status"], "COMMITTED")
        self.assertEqual(sum(row["active"] for row in self._rows("relationship_evidence")), 1)

    def test_newer_revision_and_changed_evidence_history_refuse_stale_tokens(self) -> None:
        note = self._note()
        self._retire_current_without_revision_change(note.note_id)
        pre = self.service.prepare_note_reference_reconciliation(
            note.note_id, self.person.person_id,
        )
        self.store.update_note(
            note.note_id,
            "new authoritative revision",
            "newer-note-revision",
            mentioned_person_ids=[self.person.person_id],
            actor=ACTOR,
        )
        journal_before = self._rows("operation_journal")
        with self.assertRaises(StructuredRepairRefused):
            self.service.reconcile_note_reference_state(
                pre, "repair-stale-revision", actor=ACTOR, reason="Stale revision",
            )
        self.assertEqual(self._rows("operation_journal"), journal_before)

        self.tearDown()
        self.setUp()
        note = self._note()
        self._retire_active_evidence(note.note_id)
        pre = self.service.prepare_note_reference_reconciliation(
            note.note_id, self.person.person_id,
        )
        mention = self._active_mention(note.note_id)
        with self.store._connect() as conn:
            _begin_journal_operation(
                conn, "test.r02.retired-history", operation_id="later-evidence-history",
                actor=ACTOR,
            )
            evidence_id = _insert_relationship_evidence(
                conn,
                evidence_type="NOTE_REFERENCE",
                source_entity_type="NOTE",
                source_entity_id=str(mention["mention_id"]),
                evidence_revision_id="later-evidence-history",
                source_person_id=self.owner.person_id,
                target_person_id=self.person.person_id,
                relationship_type="REFERENCES",
                directionality="DIRECTED",
                source="test",
                created_operation_id="later-evidence-history",
                created_at=utc_now(),
            )
            conn.execute(
                """
                UPDATE relationship_evidence SET active=0,
                    deactivated_operation_id='later-evidence-history', deactivated_at=?
                WHERE evidence_id=?
                """,
                (utc_now(), evidence_id),
            )
            _transition_journal_operation(conn, "later-evidence-history", "COMMITTED", {})
        journal_before = self._rows("operation_journal")
        with self.assertRaises(StructuredRepairRefused):
            self.service.reconcile_note_reference_state(
                pre, "repair-stale-evidence-history", actor=ACTOR, reason="Stale evidence",
            )
        self.assertEqual(self._rows("operation_journal"), journal_before)

    def test_changed_revision_mentions_and_graph_revision_refuse(self) -> None:
        note = self._note()
        self._retire_current_without_revision_change(note.note_id)
        pre = self.service.prepare_note_reference_reconciliation(
            note.note_id, self.person.person_id,
        )
        with sqlite3.connect(self.store.db_path) as conn:
            conn.execute("DROP TRIGGER note_revision_mentions_no_delete")
            conn.execute(
                "DELETE FROM note_revision_mentions WHERE revision_id=?",
                (pre.latest_revision_id,),
            )
        before = self._rows("operation_journal")
        with self.assertRaises(StructuredRepairRefused):
            self.service.reconcile_note_reference_state(
                pre, "repair-stale-mentions", actor=ACTOR, reason="Stale mention snapshot",
            )
        self.assertEqual(self._rows("operation_journal"), before)

        self.tearDown()
        self.setUp()
        note = self._note()
        self._retire_active_evidence(note.note_id)
        pre = self.service.prepare_note_reference_reconciliation(
            note.note_id, self.person.person_id,
        )
        self.store.create_person("Later person")
        before = self._rows("operation_journal")
        with self.assertRaises(StructuredRepairRefused):
            self.service.reconcile_note_reference_state(
                pre, "repair-stale-graph-revision", actor=ACTOR, reason="Stale graph",
            )
        self.assertEqual(self._rows("operation_journal"), before)

    def test_healthy_and_wholly_missing_groups_refuse(self) -> None:
        note = self._note()
        with self.assertRaises(StructuredRepairRefused):
            self.service.prepare_note_reference_reconciliation(
                note.note_id, self.person.person_id,
            )
        with sqlite3.connect(self.store.db_path) as conn:
            conn.execute("DROP TRIGGER relationship_evidence_no_delete")
            conn.execute("DROP TRIGGER note_mentions_no_delete")
            conn.execute("DELETE FROM relationship_evidence")
            conn.execute("DELETE FROM note_mentions WHERE note_id=?", (note.note_id,))
            conn.execute("DELETE FROM graph_connections")
        with self.assertRaises(StructuredRepairRefused):
            self.service.prepare_note_reference_reconciliation(
                note.note_id, self.person.person_id,
            )

    def test_malformed_retirement_and_evidence_provenance_refuse(self) -> None:
        note = self._note()
        self.store.update_note(
            note.note_id, "none", "remove-mention", mentioned_person_ids=[], actor=ACTOR,
        )
        with sqlite3.connect(self.store.db_path) as conn:
            conn.execute("PRAGMA ignore_check_constraints=ON")
            conn.execute("DROP TRIGGER note_mentions_deactivation_only")
            conn.execute("UPDATE note_mentions SET retired_revision_id=NULL WHERE note_id=?", (note.note_id,))
        with self.assertRaises(StructuredRepairRefused):
            self.service.prepare_note_reference_reconciliation(
                note.note_id, self.person.person_id,
            )

    def test_unrelated_authority_error_and_invalid_canonical_states_refuse(self) -> None:
        note = self._note()
        self._retire_active_evidence(note.note_id)
        other = self.store.create_person("Other")
        with sqlite3.connect(self.store.db_path) as conn:
            conn.execute(
                "UPDATE persons SET deleted_at='invalid' WHERE person_id=?",
                (other.person_id,),
            )
        before = self._rows("operation_journal")
        with self.assertRaises(StructuredRepairRefused):
            self.service.prepare_note_reference_reconciliation(
                note.note_id, self.person.person_id,
            )
        self.assertEqual(self._rows("operation_journal"), before)

        for corruption in ("cycle", "dangling"):
            with self.subTest(corruption=corruption):
                self.tearDown()
                self.setUp()
                note = self._note()
                self._retire_active_evidence(note.note_id)
                with sqlite3.connect(self.store.db_path) as conn:
                    conn.execute("PRAGMA foreign_keys=OFF")
                    conn.execute("PRAGMA ignore_check_constraints=ON")
                    conn.execute("DROP TRIGGER persons_canonical_update")
                    if corruption == "cycle":
                        conn.execute(
                            """
                            UPDATE persons SET lifecycle_status='MERGED', deleted_at=?,
                                canonical_person_id=? WHERE person_id=?
                            """,
                            (utc_now(), self.person.person_id, self.owner.person_id),
                        )
                        conn.execute(
                            """
                            UPDATE persons SET lifecycle_status='MERGED', deleted_at=?,
                                canonical_person_id=? WHERE person_id=?
                            """,
                            (utc_now(), self.owner.person_id, self.person.person_id),
                        )
                    else:
                        conn.execute(
                            """
                            UPDATE persons SET lifecycle_status='MERGED', deleted_at=?,
                                canonical_person_id='missing-person' WHERE person_id=?
                            """,
                            (utc_now(), self.person.person_id),
                        )
                before = self._rows("operation_journal")
                with self.assertRaises(StructuredRepairRefused):
                    self.service.prepare_note_reference_reconciliation(
                        note.note_id, self.person.person_id,
                    )
                self.assertEqual(self._rows("operation_journal"), before)

    def test_invalid_correction_chain_and_evidence002_refuse(self) -> None:
        note = self._note()
        self._retire_active_evidence(note.note_id)
        first = self.store.create_person("First correction")
        second = self.store.create_person("Second correction")
        third = self.store.create_person("Third correction")
        embedding = self.store.add_embedding(first.person_id, (1.0, 0.0), 0.9)
        for operation_id in ("move-one", "move-two"):
            self.store.begin_operation("identity.face.move", operation_id=operation_id)
            self.store.mark_operation_committed(operation_id)
        with sqlite3.connect(self.store.db_path) as conn:
            conn.execute("PRAGMA foreign_keys=OFF")
            conn.execute(
                "INSERT INTO identity_corrections VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    "correction-one", "FACE_OWNERSHIP", None, None,
                    embedding.embedding_id, first.person_id, second.person_id,
                    "move-one", utc_now(),
                ),
            )
            conn.execute(
                "INSERT INTO identity_corrections VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    "correction-two", "FACE_OWNERSHIP", None, None,
                    embedding.embedding_id, third.person_id, "missing-person",
                    "move-two", utc_now(),
                ),
            )
        before = self._rows("operation_journal")
        with self.assertRaises(StructuredRepairRefused):
            self.service.prepare_note_reference_reconciliation(
                note.note_id, self.person.person_id,
            )
        self.assertEqual(self._rows("operation_journal"), before)

        self.tearDown()
        self.setUp()
        note = self._note()
        self._retire_active_evidence(note.note_id)
        with sqlite3.connect(self.store.db_path) as conn:
            conn.execute("DROP TRIGGER relationship_evidence_identity_immutable")
            conn.execute(
                "UPDATE relationship_evidence SET relationship_type='ASSOCIATED_WITH'"
            )
        with self.assertRaises(StructuredRepairRefused):
            self.service.prepare_note_reference_reconciliation(
                note.note_id, self.person.person_id,
            )

    def test_ambiguous_multiple_plans_refuse(self) -> None:
        note = self._note()
        self.store.update_note(
            note.note_id, "none", "remove-first", mentioned_person_ids=[], actor=ACTOR,
        )
        self.store.update_note(
            note.note_id, "again", "readd", mentioned_person_ids=[self.person.person_id], actor=ACTOR,
        )
        with sqlite3.connect(self.store.db_path) as conn:
            conn.execute("DROP TRIGGER relationship_evidence_deactivation_only")
            conn.execute(
                """
                UPDATE relationship_evidence SET active=1,
                    deactivated_operation_id=NULL, deactivated_at=NULL
                WHERE source_entity_id IN (
                  SELECT mention_id FROM note_mentions WHERE note_id=? AND active=0
                )
                """,
                (note.note_id,),
            )
        with self.assertRaises(StructuredRepairRefused):
            self.service.prepare_note_reference_reconciliation(
                note.note_id, self.person.person_id,
            )

    def test_all_transaction_checkpoints_roll_back_and_record_failed(self) -> None:
        phases = (
            "after_journal_started",
            "after_duplicate_evidence_retire_phase",
            "after_replacement_evidence_append",
            "after_graph_projection",
            "after_graph_revision_advance",
            "after_immediate_validation",
            "before_commit",
        )
        for index, phase in enumerate(phases):
            with self.subTest(phase=phase):
                if index:
                    self.tearDown()
                    self.setUp()
                note = self._note()
                self._append_duplicate_evidence(note.note_id)
                pre = self.service.prepare_note_reference_reconciliation(
                    note.note_id, self.person.person_id,
                )
                authority_before = {
                    table: self._rows(table) for table in (
                        "note_mentions", "relationship_evidence", "graph_connections",
                    )
                }
                revision_before = self.store.get_graph_revision()

                def inject(current: str) -> None:
                    if current == phase:
                        raise RuntimeError(f"injected {phase}")

                operation_id = f"repair-failed-{index}"
                with patch(
                    "sentriface.storage.sqlite_store._r02_failure_checkpoint",
                    side_effect=inject,
                ):
                    with self.assertRaisesRegex(RuntimeError, phase):
                        self.service.reconcile_note_reference_state(
                            pre, operation_id, actor=ACTOR, reason="Rollback test",
                        )
                for table, rows in authority_before.items():
                    self.assertEqual(self._rows(table), rows, table)
                self.assertEqual(self.store.get_graph_revision(), revision_before)
                operation = self.store.get_operation(operation_id)
                self.assertEqual(operation["status"], "FAILED")
                self.assertTrue(operation["details"]["transaction_rolled_back"])

    def test_each_plan_mutation_checkpoint_rolls_back(self) -> None:
        cases = (
            ("after_occurrence_append", "append-occurrence"),
            ("after_occurrence_retirement", "retire-occurrence"),
            ("after_evidence_append", "append-evidence"),
            ("after_evidence_retirement", "retire-evidence"),
        )
        for index, (phase, case) in enumerate(cases):
            with self.subTest(phase=phase):
                if index:
                    self.tearDown()
                    self.setUp()
                note = self._note()
                if case == "append-occurrence":
                    self._retire_current_without_revision_change(note.note_id)
                elif case == "retire-occurrence":
                    self.store.update_note(
                        note.note_id, "none", "remove-for-failure",
                        mentioned_person_ids=[], actor=ACTOR,
                    )
                    with sqlite3.connect(self.store.db_path) as conn:
                        conn.execute("DROP TRIGGER note_mentions_deactivation_only")
                        conn.execute(
                            """
                            UPDATE note_mentions SET active=1, retired_revision_id=NULL,
                                retired_operation_id=NULL, retired_at=NULL WHERE note_id=?
                            """,
                            (note.note_id,),
                        )
                elif case == "append-evidence":
                    self._retire_active_evidence(note.note_id)
                else:
                    self.store.update_note(
                        note.note_id, "none", "remove-for-stale-evidence",
                        mentioned_person_ids=[], actor=ACTOR,
                    )
                    self._reactivate_retired_evidence(note.note_id)
                pre = self.service.prepare_note_reference_reconciliation(
                    note.note_id, self.person.person_id,
                )
                before = {
                    table: self._rows(table) for table in (
                        "note_mentions", "relationship_evidence", "graph_connections",
                    )
                }
                revision = self.store.get_graph_revision()

                def inject(current: str) -> None:
                    if current == phase:
                        raise RuntimeError(f"injected {phase}")

                operation_id = f"repair-plan-failure-{index}"
                with patch(
                    "sentriface.storage.sqlite_store._r02_failure_checkpoint",
                    side_effect=inject,
                ):
                    with self.assertRaisesRegex(RuntimeError, phase):
                        self.service.reconcile_note_reference_state(
                            pre, operation_id, actor=ACTOR, reason="Rollback plan step",
                        )
                for table, rows in before.items():
                    self.assertEqual(self._rows(table), rows, table)
                self.assertEqual(self.store.get_graph_revision(), revision)
                self.assertEqual(self.store.get_operation(operation_id)["status"], "FAILED")


if __name__ == "__main__":
    unittest.main()
