from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sentriface.graph_service import GlobalIdentityGraphService
from sentriface.storage.sqlite_store import (
    SCHEMA_VERSION,
    SQLiteIdentityStore,
    _schema_migrations,
)


class NoteRevisionDomainTest(unittest.TestCase):
    def _store(self, root: Path) -> SQLiteIdentityStore:
        store = SQLiteIdentityStore(root / "sentriface.db", embedding_dim=2)
        store.initialize()
        return store

    def _observation_evidence(
        self,
        store: SQLiteIdentityStore,
        graph: GlobalIdentityGraphService,
        first_person_id: str,
        second_person_id: str,
    ) -> None:
        observation = store.create_observation(
            "note-test-observation-create",
            participant_ids=[first_person_id, second_person_id],
        )
        store._finalize_observation_without_graph_evidence(
            observation.observation_id, "note-test-observation-finalize",
        )
        graph.record_observation_evidence(
            observation.observation_id, "note-test-observation-evidence",
        )

    def test_create_note_without_mentions_records_revision_actor_and_journal(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            graph = GlobalIdentityGraphService(store)
            owner = store.create_person("Owner")
            actor = {
                "user_id": "operator-1",
                "username": "operator",
                "display_name": "Operator One",
                "roles": ["operator"],
            }

            note = graph.create_note(
                owner.person_id,
                "Context only",
                "note-create",
                actor=actor,
                source="test",
            )

            self.assertEqual(note.content, "Context only")
            self.assertEqual(note.revision_number, 1)
            self.assertEqual(note.mentioned_person_ids, ())
            self.assertEqual(graph.get_global_projection().connections, ())
            revisions = graph.list_note_revisions(note.note_id)
            self.assertEqual(len(revisions), 1)
            self.assertEqual(revisions[0].actor["user_id"], "operator-1")
            self.assertEqual(revisions[0].author_name, "Operator One")
            operation = store.get_operation("note-create")
            self.assertEqual(operation["operation_type"], "note.create")
            self.assertEqual(operation["status"], "COMMITTED")

    def test_directed_and_duplicate_explicit_mentions(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            graph = GlobalIdentityGraphService(store)
            first = store.create_person("A")
            second = store.create_person("B")

            first_note = graph.create_note(
                first.person_id,
                "@B and again @B",
                "note-a-to-b",
                mentioned_person_ids=[second.person_id, second.person_id],
            )
            graph.create_note(
                second.person_id,
                "@A",
                "note-b-to-a",
                mentioned_person_ids=[first.person_id],
            )

            self.assertEqual(first_note.mentioned_person_ids, (second.person_id,))
            forward = graph.get_connection_evidence(first.person_id, second.person_id)
            reverse = graph.get_connection_evidence(second.person_id, first.person_id)
            self.assertEqual(len(forward), 1)
            self.assertEqual(len(reverse), 1)
            self.assertEqual(
                (forward[0].source_person_id, forward[0].target_person_id),
                (first.person_id, second.person_id),
            )
            self.assertEqual(
                (reverse[0].source_person_id, reverse[0].target_person_id),
                (second.person_id, first.person_id),
            )

    def test_edit_reconciles_only_that_notes_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            graph = GlobalIdentityGraphService(store)
            owner = store.create_person("A")
            first = store.create_person("B")
            second = store.create_person("C")
            self._observation_evidence(store, graph, owner.person_id, first.person_id)
            other_note = graph.create_note(
                owner.person_id,
                "Other @B",
                "other-note-create",
                mentioned_person_ids=[first.person_id],
            )
            edited_note = graph.create_note(
                owner.person_id,
                "@B",
                "edited-note-create",
                mentioned_person_ids=[first.person_id],
            )

            updated = graph.update_note(
                edited_note.note_id,
                "@C",
                "edited-note-update",
                mentioned_person_ids=[second.person_id],
                expected_revision_number=1,
            )

            self.assertEqual(updated.revision_number, 2)
            self.assertEqual(updated.mentioned_person_ids, (second.person_id,))
            first_evidence = graph.get_connection_evidence(owner.person_id, first.person_id)
            self.assertEqual(
                {item.evidence_type for item in first_evidence},
                {"CO_OBSERVED", "NOTE_REFERENCE"},
            )
            self.assertEqual(
                len([item for item in first_evidence if item.evidence_type == "NOTE_REFERENCE"]),
                1,
            )
            self.assertEqual(
                len(graph.get_connection_evidence(owner.person_id, second.person_id)),
                1,
            )
            inactive = graph.get_connection_evidence(
                owner.person_id, first.person_id, include_inactive=True,
            )
            self.assertEqual(
                len([item for item in inactive if not item.active]),
                1,
            )
            self.assertEqual(graph.get_note(other_note.note_id).status, "ACTIVE")

    def test_removing_and_retiring_mentions_preserves_other_evidence_and_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            graph = GlobalIdentityGraphService(store)
            owner = store.create_person("A")
            target = store.create_person("B")
            self._observation_evidence(store, graph, owner.person_id, target.person_id)
            note = graph.create_note(
                owner.person_id,
                "@B",
                "remove-note-create",
                mentioned_person_ids=[target.person_id],
            )

            graph.update_note(
                note.note_id,
                "No references",
                "remove-note-reference",
                mentioned_person_ids=[],
            )
            active = graph.get_connection_evidence(owner.person_id, target.person_id)
            self.assertEqual(len(active), 1)
            self.assertEqual(active[0].evidence_type, "CO_OBSERVED")

            second_note = graph.create_note(
                owner.person_id,
                "@B again",
                "retire-note-create",
                mentioned_person_ids=[target.person_id],
            )
            retired = graph.retire_note(second_note.note_id, "retire-note")

            self.assertEqual(retired.status, "RETIRED")
            self.assertIsNone(graph.get_note(second_note.note_id))
            self.assertIsNotNone(graph.get_note(second_note.note_id, include_retired=True))
            self.assertEqual(len(graph.list_note_revisions(second_note.note_id)), 1)
            remaining = graph.get_connection_evidence(owner.person_id, target.person_id)
            self.assertEqual(len(remaining), 1)
            self.assertEqual(remaining[0].evidence_type, "CO_OBSERVED")
            self.assertEqual(store.get_operation("retire-note")["status"], "COMMITTED")

    def test_self_reference_has_no_evidence_and_no_face_identity_can_be_referenced(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            graph = GlobalIdentityGraphService(store)
            owner = store.create_person("Owner")
            context_only = store.create_person("Context Only")

            self_note = graph.create_note(
                owner.person_id,
                "@Owner",
                "self-note",
                mentioned_person_ids=[owner.person_id],
            )
            graph.create_note(
                owner.person_id,
                "@Context Only",
                "no-face-note",
                mentioned_person_ids=[context_only.person_id],
            )

            self.assertEqual(self_note.mentioned_person_ids, (owner.person_id,))
            self.assertEqual(graph.get_person_neighbors(owner.person_id)[0].target_person_id,
                             context_only.person_id)
            with sqlite3.connect(store.db_path) as conn:
                self.assertEqual(
                    conn.execute(
                        """
                        SELECT COUNT(*) FROM relationship_evidence
                        WHERE source_person_id = target_person_id
                        """
                    ).fetchone()[0],
                    0,
                )

    def test_raw_reference_ids_survive_later_canonical_change(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            graph = GlobalIdentityGraphService(store)
            raw_owner = store.create_person("Raw Owner")
            survivor = store.create_person("Survivor")
            target = store.create_person("Target")
            note = graph.create_note(
                raw_owner.person_id,
                "@Target",
                "raw-note",
                mentioned_person_ids=[target.person_id],
            )
            store._set_canonical_person_id_for_merge(
                raw_owner.person_id, survivor.person_id, "raw-owner-map",
            )

            evidence = graph.get_connection_evidence(survivor.person_id, target.person_id)
            self.assertEqual(len(evidence), 1)
            self.assertEqual(evidence[0].source_person_id, raw_owner.person_id)
            self.assertEqual(evidence[0].target_person_id, target.person_id)
            self.assertEqual(graph.get_note(note.note_id).owner_person_id, raw_owner.person_id)

    def test_failed_save_rolls_back_revision_mentions_evidence_projection_and_journal(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            graph = GlobalIdentityGraphService(store)
            owner = store.create_person("A")
            first = store.create_person("B")
            second = store.create_person("C")
            note = graph.create_note(
                owner.person_id,
                "@B",
                "rollback-note-create",
                mentioned_person_ids=[first.person_id],
            )

            with patch(
                "sentriface.storage.sqlite_store._transition_journal_operation",
                side_effect=RuntimeError("simulated note journal failure"),
            ):
                with self.assertRaisesRegex(RuntimeError, "simulated note journal failure"):
                    graph.update_note(
                        note.note_id,
                        "@C",
                        "rollback-note-update",
                        mentioned_person_ids=[second.person_id],
                    )

            current = graph.get_note(note.note_id)
            self.assertEqual(current.revision_number, 1)
            self.assertEqual(current.mentioned_person_ids, (first.person_id,))
            self.assertEqual(len(graph.list_note_revisions(note.note_id)), 1)
            self.assertEqual(
                len(graph.get_connection_evidence(owner.person_id, first.person_id)), 1,
            )
            self.assertEqual(
                graph.get_connection_evidence(owner.person_id, second.person_id), [],
            )
            self.assertIsNone(store.get_operation("rollback-note-update"))
            self.assertTrue(graph.validate_projection()["valid"])

    def test_v21_legacy_note_migrates_without_fabricated_mentions(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "sentriface.db"
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA foreign_keys=ON")
                conn.execute("BEGIN")
                for migration in _schema_migrations():
                    if migration.to_version > 21:
                        break
                    migration.apply(conn)
                conn.execute(
                    """
                    INSERT INTO persons(person_id, name, metadata, created_at, notes)
                    VALUES ('legacy-owner', 'Legacy Owner', '{}', ?, '@Legacy Target')
                    """,
                    ("2026-08-08T00:00:00+00:00",),
                )
                conn.execute(
                    """
                    INSERT INTO persons(person_id, name, metadata, created_at, notes)
                    VALUES ('legacy-target', 'Legacy Target', '{}', ?, '')
                    """,
                    ("2026-08-08T00:00:00+00:00",),
                )
                conn.commit()

            store = SQLiteIdentityStore(db_path, embedding_dim=2)
            embedding = store.add_embedding(
                "legacy-owner", (1.0, 0.0), 0.9,
            )
            detail = store.add_recognition_detail(
                embedding.embedding_id,
                "legacy-owner",
                "legacy-image",
                "Legacy Owner",
                "existing",
                "2026-08-08",
                "12:00",
                "Lobby",
                1,
                "Visit",
                notes="Legacy sighting @Legacy Target",
            )
            store.initialize()
            graph = GlobalIdentityGraphService(store)

            note = graph.get_person_note("legacy-owner")
            self.assertEqual(note.content, "@Legacy Target")
            self.assertEqual(note.mentioned_person_ids, ())
            self.assertEqual(len(graph.list_note_revisions(note.note_id)), 1)
            self.assertEqual(
                graph.get_connection_evidence("legacy-owner", "legacy-target"), [],
            )
            with sqlite3.connect(db_path) as conn:
                self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM note_mentions").fetchone()[0], 0)
                sighting_note = conn.execute(
                    """
                    SELECT r.content
                    FROM notes n
                    JOIN note_revisions r ON r.note_id = n.note_id
                    WHERE n.subject_type = 'RECOGNITION_DETAIL' AND n.subject_id = ?
                    """,
                    (detail.detail_id,),
                ).fetchone()
            self.assertEqual(sighting_note[0], "Legacy sighting @Legacy Target")


if __name__ == "__main__":
    unittest.main()
