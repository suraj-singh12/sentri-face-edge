from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from sentriface.errors import StructuredRepairPostcheckError, StructuredRepairRefused
from sentriface.integrity import ReadOnlyIntegrityChecker
from sentriface.storage.sqlite_store import SQLiteIdentityStore
from sentriface.storage import sqlite_store as sqlite_store_module
from sentriface.structured_repair_service import StructuredRepairService


ACTOR = {"user_id": "operator-1", "display_name": "Operator"}


class StructuredRepairR01Test(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = SQLiteIdentityStore(Path(self.temp.name) / "sentriface.db", embedding_dim=2)
        self.store.initialize()
        self.service = StructuredRepairService(self.store)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _merged_archived(self, *, transitive: bool = False):
        source = self.store.create_person("Source")
        survivor = self.store.create_person("Survivor")
        intermediate = None
        if transitive:
            intermediate = self.store.create_person("Intermediate")
            self.store.execute_identity_merge(
                source.person_id, intermediate.person_id, "merge-source", actor=ACTOR,
            )
            self.store.execute_identity_merge(
                intermediate.person_id, survivor.person_id, "merge-intermediate", actor=ACTOR,
            )
        else:
            self.store.execute_identity_merge(
                source.person_id, survivor.person_id, "merge-source", actor=ACTOR,
            )
        self.store.archive_person(survivor.person_id, "archive-survivor", ACTOR)
        return source, intermediate, survivor

    def _rows(self, table: str):
        with sqlite3.connect(self.store.db_path) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY rowid")]

    def test_exact_finding_repairs_and_preserves_history_and_projection(self) -> None:
        source, _, survivor = self._merged_archived()
        pre = self.service.prepare_restore_archived_canonical_survivor(survivor.person_id)
        immutable_before = {
            table: self._rows(table) for table in (
                "merge_operations", "merge_affected_items", "merge_conflict_resolutions",
                "identity_corrections", "observations", "observation_participants",
                "observation_media", "notes", "note_revisions", "note_revision_mentions",
                "note_mentions", "relationship_evidence", "graph_connections",
            )
        }
        journal_before = self._rows("operation_journal")
        person_ops_before = self._rows("person_operations")
        revision_before = int(self.store.get_graph_revision()[1:])

        result = self.service.restore_archived_canonical_survivor(
            pre, "repair-r01", actor=ACTOR, reason="Restore proven merge survivor",
        )

        self.assertEqual(result["postcheck_status"], "PASS")
        self.assertEqual(result["graph_revision_after"], f"g{revision_before + 1}")
        lifecycle = self.store.get_person_lifecycle(survivor.person_id)
        self.assertEqual(lifecycle["lifecycle_status"], "ACTIVE")
        self.assertIsNone(lifecycle["canonical_person_id"])
        self.assertEqual(self.store.resolve_canonical_person_id(source.person_id), survivor.person_id)
        self.assertFalse(any(
            item.invariant_id == "P11-IDENTITY-003"
            for item in ReadOnlyIntegrityChecker(self.store.db_path).run().findings
        ))
        for table, rows in immutable_before.items():
            self.assertEqual(self._rows(table), rows, table)
        self.assertEqual(self._rows("person_operations"), person_ops_before)
        self.assertEqual(self._rows("operation_journal")[:len(journal_before)], journal_before)
        archive_rows = [row for row in person_ops_before if row["operation_id"] == "archive-survivor"]
        self.assertEqual(len(archive_rows), 1)
        repair_journal = self.store.get_operation("repair-r01")
        self.assertEqual(repair_journal["status"], "COMMITTED")
        self.assertEqual(repair_journal["operation_type"], "integrity.repair.canonical-survivor.restore")

    def test_transitive_merge_paths_succeed_unchanged(self) -> None:
        source, intermediate, survivor = self._merged_archived(transitive=True)
        pre = self.service.prepare_restore_archived_canonical_survivor(survivor.person_id)
        self.assertEqual(len(pre.merge_paths), 2)
        manifests = self._rows("merge_operations")
        result = self.service.restore_archived_canonical_survivor(
            pre, "repair-transitive", actor=ACTOR, reason="Restore terminal",
        )
        self.assertEqual(result["merge_path_count"], 2)
        self.assertEqual(self._rows("merge_operations"), manifests)
        self.assertEqual(self.store.resolve_canonical_person_id(source.person_id), survivor.person_id)
        self.assertEqual(self.store.resolve_canonical_person_id(intermediate.person_id), survivor.person_id)

    def test_correction_evidence_and_merge_authority_remain_unchanged(self) -> None:
        original = self.store.create_person("Original")
        corrected = self.store.create_person("Corrected")
        other = self.store.create_person("Other")
        survivor = self.store.create_person("Survivor")
        observation = self.store.create_observation(
            "observation-create", participant_ids=[original.person_id, other.person_id],
        )
        self.store._finalize_observation_without_graph_evidence(
            observation.observation_id, "observation-finalize",
        )
        self.store.record_observation_evidence(observation.observation_id, "observation-evidence")
        self.store.correct_observation_identity(
            observation.observation_id, original.person_id, corrected.person_id,
            "observation-correction", actor=ACTOR,
        )
        self.store.execute_identity_merge(
            corrected.person_id, survivor.person_id, "merge-corrected", actor=ACTOR,
        )
        self.store.archive_person(survivor.person_id, "archive-survivor", ACTOR)
        corrections = self._rows("identity_corrections")
        participants = self._rows("observation_participants")
        evidence = self._rows("relationship_evidence")
        graph = self._rows("graph_connections")
        pre = self.service.prepare_restore_archived_canonical_survivor(survivor.person_id)
        self.service.restore_archived_canonical_survivor(
            pre, "repair-corrected", actor=ACTOR, reason="Restore proven survivor",
        )
        self.assertEqual(self._rows("identity_corrections"), corrections)
        self.assertEqual(self._rows("observation_participants"), participants)
        self.assertEqual(self._rows("relationship_evidence"), evidence)
        self.assertEqual(self._rows("graph_connections"), graph)

    def test_same_committed_operation_id_returns_result_and_new_id_refuses(self) -> None:
        _, _, survivor = self._merged_archived()
        pre = self.service.prepare_restore_archived_canonical_survivor(survivor.person_id)
        first = self.service.restore_archived_canonical_survivor(
            pre, "repair-once", actor=ACTOR, reason="Restore terminal",
        )
        second = self.service.restore_archived_canonical_survivor(
            pre, "repair-once", actor=ACTOR, reason="Retry",
        )
        self.assertEqual(first, second)
        with self.assertRaises(StructuredRepairRefused):
            self.service.restore_archived_canonical_survivor(
                pre, "repair-new", actor=ACTOR, reason="Stale retry",
            )
        self.assertIsNone(self.store.get_operation("repair-new"))

    def test_changed_fingerprint_or_later_lifecycle_operation_refuses_without_mutation(self) -> None:
        _, _, survivor = self._merged_archived()
        pre = self.service.prepare_restore_archived_canonical_survivor(survivor.person_id)
        before = self._rows("operation_journal")
        with self.assertRaises(StructuredRepairRefused):
            self.service.restore_archived_canonical_survivor(
                replace(pre, finding_fingerprint="0" * 64),
                "repair-stale-fingerprint", actor=ACTOR, reason="Wrong token",
            )
        self.assertEqual(self._rows("operation_journal"), before)
        self.store.archive_person(survivor.person_id, "newer-archive", ACTOR)
        after_later = self._rows("operation_journal")
        with self.assertRaises(StructuredRepairRefused):
            self.service.restore_archived_canonical_survivor(
                pre, "repair-stale-operation", actor=ACTOR, reason="Stale state",
            )
        self.assertEqual(self._rows("operation_journal"), after_later)

    def test_changed_terminal_survivor_refuses_stale_diagnosis(self) -> None:
        _, _, survivor = self._merged_archived()
        pre = self.service.prepare_restore_archived_canonical_survivor(survivor.person_id)
        self.store.restore_person(survivor.person_id, "normal-restore", ACTOR)
        replacement = self.store.create_person("Replacement")
        self.store.execute_identity_merge(
            survivor.person_id, replacement.person_id, "later-merge", actor=ACTOR,
        )
        before = self._rows("operation_journal")
        with self.assertRaises(StructuredRepairRefused):
            self.service.restore_archived_canonical_survivor(
                pre, "repair-changed-survivor", actor=ACTOR, reason="Stale target",
            )
        self.assertEqual(self._rows("operation_journal"), before)

    def test_deleted_terminal_and_healthy_or_nonterminal_person_refuse(self) -> None:
        source, _, survivor = self._merged_archived()
        self.store.soft_delete_person(survivor.person_id, "delete-survivor", ACTOR)
        before = self._rows("operation_journal")
        with self.assertRaises(StructuredRepairRefused):
            self.service.prepare_restore_archived_canonical_survivor(survivor.person_id)
        with self.assertRaises(StructuredRepairRefused):
            self.service.prepare_restore_archived_canonical_survivor(source.person_id)
        healthy = self.store.create_person("Healthy")
        with self.assertRaises(StructuredRepairRefused):
            self.service.prepare_restore_archived_canonical_survivor(healthy.person_id)
        self.assertEqual(self._rows("operation_journal")[:len(before)], before)

    def test_ambiguous_identity_corruption_refuses(self) -> None:
        _, _, survivor = self._merged_archived()
        other = self.store.create_person("Other")
        with sqlite3.connect(self.store.db_path) as conn:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute(
                "UPDATE persons SET deleted_at = 'bad' WHERE person_id = ?",
                (other.person_id,),
            )
        before = self._rows("operation_journal")
        with self.assertRaises(StructuredRepairRefused):
            self.service.prepare_restore_archived_canonical_survivor(survivor.person_id)
        self.assertEqual(self._rows("operation_journal"), before)

    def test_canonical_cycle_and_dangling_target_refuse_without_repair_mutation(self) -> None:
        for corruption in ("cycle", "dangling"):
            with self.subTest(corruption=corruption):
                self.tearDown()
                self.setUp()
                source, _, survivor = self._merged_archived()
                with sqlite3.connect(self.store.db_path) as conn:
                    conn.execute("PRAGMA foreign_keys=OFF")
                    conn.execute("DROP TRIGGER persons_canonical_update")
                    target = source.person_id if corruption == "cycle" else "missing-person"
                    conn.execute(
                        "UPDATE persons SET lifecycle_status='MERGED', canonical_person_id=?, deleted_at=COALESCE(deleted_at, 'bad') WHERE person_id=?",
                        (target, survivor.person_id),
                    )
                before = self._rows("operation_journal")
                with self.assertRaises(StructuredRepairRefused):
                    self.service.prepare_restore_archived_canonical_survivor(survivor.person_id)
                self.assertEqual(self._rows("operation_journal"), before)

    def test_malformed_manifest_refuses(self) -> None:
        _, _, survivor = self._merged_archived()
        with sqlite3.connect(self.store.db_path) as conn:
            conn.execute("DROP TRIGGER merge_conflicts_no_update")
            conn.execute(
                "UPDATE merge_conflict_resolutions SET inverse_data = '{}' WHERE merge_operation_id = 'merge-source'"
            )
        before = self._rows("operation_journal")
        with self.assertRaises(StructuredRepairRefused):
            self.service.prepare_restore_archived_canonical_survivor(survivor.person_id)
        self.assertEqual(self._rows("operation_journal"), before)

    def test_failure_after_started_rolls_back_authority_and_records_failed_attempt(self) -> None:
        _, _, survivor = self._merged_archived()
        pre = self.service.prepare_restore_archived_canonical_survivor(survivor.person_id)
        lifecycle_before = self.store.get_person_lifecycle(survivor.person_id)
        revision_before = self.store.get_graph_revision()
        merges_before = self._rows("merge_operations")
        with patch(
            "sentriface.storage.sqlite_store._restore_archived_person_in_transaction",
            side_effect=RuntimeError("injected after STARTED"),
        ):
            with self.assertRaisesRegex(RuntimeError, "injected"):
                self.service.restore_archived_canonical_survivor(
                    pre, "repair-failed", actor=ACTOR, reason="Failure test",
                )
        self.assertEqual(self.store.get_person_lifecycle(survivor.person_id), lifecycle_before)
        self.assertEqual(self.store.get_graph_revision(), revision_before)
        self.assertEqual(self._rows("merge_operations"), merges_before)
        operation = self.store.get_operation("repair-failed")
        self.assertEqual(operation["status"], "FAILED")
        self.assertTrue(operation["details"]["transaction_rolled_back"])
        with self.assertRaises(RuntimeError):
            self.service.restore_archived_canonical_survivor(
                pre, "repair-failed", actor=ACTOR, reason="Cannot reuse failure",
            )
        refreshed = self.service.prepare_restore_archived_canonical_survivor(
            survivor.person_id,
        )
        retried = self.service.restore_archived_canonical_survivor(
            refreshed, "repair-retry", actor=ACTOR, reason="New operation retry",
        )
        self.assertEqual(retried["postcheck_status"], "PASS")

    def test_immediate_validation_failure_rolls_back_lifecycle_and_revision(self) -> None:
        _, _, survivor = self._merged_archived()
        pre = self.service.prepare_restore_archived_canonical_survivor(survivor.person_id)
        before = self.store.get_person_lifecycle(survivor.person_id)
        revision = self.store.get_graph_revision()
        with patch(
            "sentriface.storage.sqlite_store._validate_r01_postconditions",
            side_effect=RuntimeError("injected validation failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "validation"):
                self.service.restore_archived_canonical_survivor(
                    pre, "repair-validation-failed", actor=ACTOR, reason="Failure test",
                )
        self.assertEqual(self.store.get_person_lifecycle(survivor.person_id), before)
        self.assertEqual(self.store.get_graph_revision(), revision)

    def test_failure_before_commit_rolls_back_and_does_not_report_success(self) -> None:
        _, _, survivor = self._merged_archived()
        pre = self.service.prepare_restore_archived_canonical_survivor(survivor.person_id)
        before = self.store.get_person_lifecycle(survivor.person_id)
        revision = self.store.get_graph_revision()
        original_transition = sqlite_store_module._transition_journal_operation

        def fail_commit(conn, operation_id, target_status, details=None):
            if target_status == "COMMITTED":
                raise RuntimeError("injected before commit")
            return original_transition(conn, operation_id, target_status, details)

        with patch(
            "sentriface.storage.sqlite_store._transition_journal_operation",
            side_effect=fail_commit,
        ):
            with self.assertRaisesRegex(RuntimeError, "before commit"):
                self.service.restore_archived_canonical_survivor(
                    pre, "repair-commit-failed", actor=ACTOR, reason="Failure test",
                )
        self.assertEqual(self.store.get_person_lifecycle(survivor.person_id), before)
        self.assertEqual(self.store.get_graph_revision(), revision)
        operation = self.store.get_operation("repair-commit-failed")
        self.assertEqual(operation["status"], "FAILED")
        self.assertFalse(any(
            item.get("details", {}).get("changed")
            for item in operation["status_history"]
        ))

    def test_failed_postcheck_is_surfaced_without_automatic_repair(self) -> None:
        _, _, survivor = self._merged_archived()
        pre = self.service.prepare_restore_archived_canonical_survivor(survivor.person_id)
        stale_report = ReadOnlyIntegrityChecker(self.store.db_path).run()
        journal_count = len(self._rows("operation_journal"))
        with patch(
            "sentriface.structured_repair_service.ReadOnlyIntegrityChecker"
        ) as checker:
            checker.return_value.run.return_value = stale_report
            with self.assertRaises(StructuredRepairPostcheckError):
                self.service.restore_archived_canonical_survivor(
                    pre, "repair-postcheck", actor=ACTOR, reason="Postcheck test",
                )
        self.assertEqual(
            self.store.get_person_lifecycle(survivor.person_id)["lifecycle_status"],
            "ACTIVE",
        )
        self.assertEqual(len(self._rows("operation_journal")), journal_count + 1)
        self.assertEqual(self.store.get_operation("repair-postcheck")["status"], "COMMITTED")


if __name__ == "__main__":
    unittest.main()
