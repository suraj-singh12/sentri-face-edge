from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from sentriface.integrity import ReadOnlyIntegrityChecker
from sentriface.models import utc_now
from sentriface.storage.sqlite_store import SQLiteIdentityStore, _replace_graph_projection


class NoteOccurrenceIntegrityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = SQLiteIdentityStore(Path(self.temp.name) / "sentriface.db", embedding_dim=2)
        self.store.initialize()
        self.owner = self.store.create_person("Owner")
        self.a = self.store.create_person("A")
        self.b = self.store.create_person("B")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _findings(self, invariant_id: str):
        return [
            item for item in ReadOnlyIntegrityChecker(self.store.db_path).run().findings
            if item.invariant_id == invariant_id
        ]

    def _occurrences(self, note_id: str):
        with sqlite3.connect(self.store.db_path) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(row) for row in conn.execute(
                """
                SELECT mention_id, referenced_person_id, active, created_revision_id,
                       retired_revision_id, created_operation_id,
                       retired_operation_id, retired_at
                FROM note_mentions WHERE note_id=? ORDER BY created_at, mention_id
                """,
                (note_id,),
            )]

    def test_valid_single_remove_readd_remove_and_multiple_cycles_are_clean(self) -> None:
        note = self.store.create_note(
            self.owner.person_id, "A once", "note-create",
            mentioned_person_ids=[self.a.person_id],
        )
        self.assertEqual(len(self._occurrences(note.note_id)), 1)
        self.assertEqual(sum(row["active"] for row in self._occurrences(note.note_id)), 1)
        self.assertEqual(self._findings("P11-NOTE-002"), [])

        self.store.update_note(
            note.note_id, "none", "note-remove-1", mentioned_person_ids=[],
        )
        removed = self._occurrences(note.note_id)
        self.assertEqual(sum(row["active"] for row in removed), 0)
        self.assertTrue(all(
            row["retired_revision_id"] and row["retired_operation_id"] and row["retired_at"]
            for row in removed
        ))
        self.assertEqual(self._findings("P11-NOTE-002"), [])

        self.store.update_note(
            note.note_id, "A again", "note-readd-1",
            mentioned_person_ids=[self.a.person_id],
        )
        readded = self._occurrences(note.note_id)
        self.assertEqual(len(readded), 2)
        self.assertEqual(sum(row["active"] for row in readded), 1)
        self.assertEqual(self._findings("P11-NOTE-002"), [])
        self.assertEqual(self._findings("P11-NOTE-003"), [])

        self.store.update_note(
            note.note_id, "none again", "note-remove-2", mentioned_person_ids=[],
        )
        self.assertEqual(sum(row["active"] for row in self._occurrences(note.note_id)), 0)
        self.assertEqual(self._findings("P11-NOTE-002"), [])

        for cycle in range(3):
            self.store.update_note(
                note.note_id, f"A cycle {cycle}", f"note-readd-cycle-{cycle}",
                mentioned_person_ids=[self.a.person_id],
            )
            self.assertEqual(self._findings("P11-NOTE-002"), [])
            self.store.update_note(
                note.note_id, f"none cycle {cycle}", f"note-remove-cycle-{cycle}",
                mentioned_person_ids=[],
            )
            self.assertEqual(self._findings("P11-NOTE-002"), [])
        rows = self._occurrences(note.note_id)
        self.assertEqual(len(rows), 5)
        self.assertEqual(sum(row["active"] for row in rows), 0)

    def test_people_reconcile_independently_and_duplicate_input_is_normalized(self) -> None:
        note = self.store.create_note(
            self.owner.person_id, "A and B", "independent-create",
            mentioned_person_ids=[self.a.person_id, self.a.person_id, self.b.person_id],
        )
        self.assertEqual(len(self._occurrences(note.note_id)), 2)
        self.store.update_note(
            note.note_id, "A", "independent-a",
            mentioned_person_ids=[self.a.person_id, self.a.person_id],
        )
        self.store.update_note(
            note.note_id, "B", "independent-b", mentioned_person_ids=[self.b.person_id],
        )
        rows = self._occurrences(note.note_id)
        active = [row for row in rows if row["active"]]
        self.assertEqual([row["referenced_person_id"] for row in active], [self.b.person_id])
        self.assertEqual(self._findings("P11-NOTE-002"), [])
        self.assertEqual(self._findings("P11-NOTE-003"), [])

    def test_stale_active_and_multiple_active_occurrences_are_detected(self) -> None:
        note = self.store.create_note(
            self.owner.person_id, "A", "stale-create",
            mentioned_person_ids=[self.a.person_id],
        )
        self.store.update_note(note.note_id, "none", "stale-remove", mentioned_person_ids=[])
        with sqlite3.connect(self.store.db_path) as conn:
            conn.execute("DROP TRIGGER note_mentions_deactivation_only")
            conn.execute(
                """
                UPDATE note_mentions SET active=1, retired_revision_id=NULL,
                       retired_operation_id=NULL, retired_at=NULL WHERE note_id=?
                """,
                (note.note_id,),
            )
        finding = self._findings("P11-NOTE-002")
        self.assertTrue(any(
            dict(item.evidence).get("expected_active_occurrences") == "0"
            and dict(item.evidence).get("actual_active_occurrences") == "1"
            for item in finding
        ))

        self.tearDown()
        self.setUp()
        note = self.store.create_note(
            self.owner.person_id, "A", "multiple-create",
            mentioned_person_ids=[self.a.person_id],
        )
        self.store.update_note(note.note_id, "none", "multiple-remove", mentioned_person_ids=[])
        self.store.update_note(
            note.note_id, "A again", "multiple-readd",
            mentioned_person_ids=[self.a.person_id],
        )
        with sqlite3.connect(self.store.db_path) as conn:
            conn.execute("DROP INDEX idx_note_mentions_active_target")
            conn.execute("DROP TRIGGER note_mentions_deactivation_only")
            conn.execute(
                """
                UPDATE note_mentions SET active=1, retired_revision_id=NULL,
                       retired_operation_id=NULL, retired_at=NULL
                WHERE note_id=? AND active=0
                """,
                (note.note_id,),
            )
        finding = self._findings("P11-NOTE-002")
        self.assertTrue(any(
            dict(item.evidence).get("expected_active_occurrences") == "1"
            and dict(item.evidence).get("actual_active_occurrences") == "2"
            for item in finding
        ))

    def test_zero_active_current_occurrence_and_malformed_retirement_are_detected(self) -> None:
        note = self.store.create_note(
            self.owner.person_id, "A", "zero-create",
            mentioned_person_ids=[self.a.person_id],
        )
        with self.store._connect() as conn:
            mention = conn.execute(
                "SELECT mention_id FROM note_mentions WHERE note_id=?", (note.note_id,),
            ).fetchone()
            latest = conn.execute(
                "SELECT revision_id FROM note_revisions WHERE note_id=?", (note.note_id,),
            ).fetchone()
            now = utc_now()
            conn.execute(
                """
                UPDATE note_mentions SET active=0, retired_revision_id=?,
                       retired_operation_id='zero-create', retired_at=? WHERE mention_id=?
                """,
                (latest[0], now, mention[0]),
            )
            conn.execute(
                """
                UPDATE relationship_evidence SET active=0,
                       deactivated_operation_id='zero-create', deactivated_at=?
                WHERE source_entity_id=? AND evidence_type='NOTE_REFERENCE'
                """,
                (now, mention[0]),
            )
            _replace_graph_projection(conn)
        finding = self._findings("P11-NOTE-002")
        self.assertEqual(len(finding), 1)
        self.assertEqual(dict(finding[0].evidence)["actual_active_occurrences"], "0")
        self.assertEqual(self._findings("P11-NOTE-003"), [])

        with sqlite3.connect(self.store.db_path) as conn:
            conn.execute("DROP TRIGGER note_mentions_deactivation_only")
            conn.execute(
                "UPDATE note_mentions SET retired_revision_id=NULL WHERE note_id=?",
                (note.note_id,),
            )
        self.assertTrue(any(
            "invalid active/retirement provenance" in item.message
            for item in self._findings("P11-NOTE-002")
        ))

    def test_note003_still_requires_evidence_only_for_current_active_occurrence(self) -> None:
        note = self.store.create_note(
            self.owner.person_id, "A", "evidence-create",
            mentioned_person_ids=[self.a.person_id],
        )
        self.store.update_note(note.note_id, "none", "evidence-remove", mentioned_person_ids=[])
        self.store.update_note(
            note.note_id, "A again", "evidence-readd",
            mentioned_person_ids=[self.a.person_id],
        )
        self.assertEqual(self._findings("P11-NOTE-002"), [])
        self.assertEqual(self._findings("P11-NOTE-003"), [])
        with sqlite3.connect(self.store.db_path) as conn:
            active_id = conn.execute(
                "SELECT mention_id FROM note_mentions WHERE note_id=? AND active=1",
                (note.note_id,),
            ).fetchone()[0]
            conn.execute("DROP TRIGGER relationship_evidence_no_delete")
            conn.execute(
                "DELETE FROM relationship_evidence WHERE source_entity_id=?",
                (active_id,),
            )
            conn.execute("DELETE FROM graph_connections")
        self.assertEqual(self._findings("P11-NOTE-002"), [])
        self.assertEqual(len(self._findings("P11-NOTE-003")), 1)

    def test_wholly_missing_occurrence_remains_outside_note002_coverage(self) -> None:
        note = self.store.create_note(
            self.owner.person_id, "A", "missing-create",
            mentioned_person_ids=[self.a.person_id],
        )
        with sqlite3.connect(self.store.db_path) as conn:
            conn.execute("DROP TRIGGER relationship_evidence_no_delete")
            conn.execute("DROP TRIGGER note_mentions_no_delete")
            conn.execute(
                "DELETE FROM relationship_evidence WHERE source_entity_id IN (SELECT mention_id FROM note_mentions WHERE note_id=?)",
                (note.note_id,),
            )
            conn.execute("DELETE FROM note_mentions WHERE note_id=?", (note.note_id,))
            conn.execute("DELETE FROM graph_connections")
        self.assertEqual(self._findings("P11-NOTE-002"), [])
        self.assertEqual(self._findings("P11-NOTE-003"), [])

    def test_r02_append_reachability_is_finding_bound_without_history_rewrite(self) -> None:
        note = self.store.create_note(
            self.owner.person_id, "A", "reach-create",
            mentioned_person_ids=[self.a.person_id],
        )
        self.store.update_note(note.note_id, "none", "reach-remove", mentioned_person_ids=[])
        self.store.update_note(
            note.note_id, "A again", "reach-readd",
            mentioned_person_ids=[self.a.person_id],
        )
        history_before = self._occurrences(note.note_id)
        self.assertEqual(len(history_before), 2)
        self.assertEqual(self._findings("P11-NOTE-002"), [])
        self.store.begin_operation("test.current-drift", operation_id="reach-drift")
        self.store.mark_operation_committed("reach-drift")
        with self.store._connect() as conn:
            current = conn.execute(
                "SELECT mention_id FROM note_mentions WHERE note_id=? AND active=1",
                (note.note_id,),
            ).fetchone()[0]
            latest = conn.execute(
                "SELECT revision_id FROM note_revisions WHERE note_id=? ORDER BY revision_number DESC LIMIT 1",
                (note.note_id,),
            ).fetchone()[0]
            now = utc_now()
            conn.execute(
                """
                UPDATE note_mentions SET active=0, retired_revision_id=?,
                       retired_operation_id='reach-drift', retired_at=? WHERE mention_id=?
                """,
                (latest, now, current),
            )
            conn.execute(
                """
                UPDATE relationship_evidence SET active=0,
                       deactivated_operation_id='reach-drift', deactivated_at=?
                WHERE evidence_type='NOTE_REFERENCE' AND source_entity_id=? AND active=1
                """,
                (now, current),
            )
            _replace_graph_projection(conn)
        finding = self._findings("P11-NOTE-002")
        self.assertEqual(len(finding), 1)
        evidence = dict(finding[0].evidence)
        self.assertEqual(evidence["expected_active_occurrences"], "1")
        self.assertEqual(evidence["actual_active_occurrences"], "0")
        self.assertEqual(self._findings("P11-NOTE-003"), [])
        after = self._occurrences(note.note_id)
        self.assertEqual(len(after), 2)
        self.assertTrue(all(not row["active"] for row in after))


if __name__ == "__main__":
    unittest.main()
