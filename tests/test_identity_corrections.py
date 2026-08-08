from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextvars import ContextVar
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sentriface.components.linear_index import LinearFaceIndex
from sentriface.correction_service import IdentityCorrectionService
from sentriface.engine import FaceEngine
from sentriface.graph_service import GlobalIdentityGraphService
from sentriface.metrics import MetricsCollector
from sentriface.models import (
    DetectedFace,
    FaceBox,
    MatchDecision,
    PendingAddition,
    QualityReport,
    QualityStatus,
)
from sentriface.storage.sqlite_store import SCHEMA_VERSION, SQLiteIdentityStore, _schema_migrations


class IdentityCorrectionTest(unittest.TestCase):
    def _store(self, root: Path) -> SQLiteIdentityStore:
        store = SQLiteIdentityStore(root / "sentriface.db", embedding_dim=2)
        store.initialize()
        return store

    def _pending(self, store, pending_id, vector, matches=None):
        store.save_pending_addition(PendingAddition(
            pending_id=pending_id,
            source_image=f"/managed/{pending_id}.jpg",
            face=DetectedFace(FaceBox(1, 1, 10, 10, 0.99), 0.9),
            vector=vector,
            matches=matches or [],
            decision=MatchDecision.UNKNOWN,
            quality=QualityReport(QualityStatus.GOOD, 0.9),
        ))

    def _finalize(self, store, review_id, assignments):
        faces = []
        for index, person in enumerate(assignments):
            pending_id = f"{review_id}-pending-{index}"
            self._pending(store, pending_id, (1.0 - index * 0.2, index * 0.2))
            faces.append({
                "face_id": f"face-{index}",
                "staged_face_type": "PENDING_ADDITION",
                "staged_face_id": pending_id,
            })
        store.create_photo_review(
            review_id, f"{review_id}.jpg", faces,
            media_path=f"/managed/{review_id}-pending-0.jpg",
        )
        for index, person in enumerate(assignments):
            store.set_photo_review_face_decision(
                review_id, f"face-{index}", "ACCEPT_EXISTING_PERSON",
                person_id=person.person_id,
            )
        return store.complete_photo_review(review_id, f"{review_id}-complete")

    def test_observation_correction_preserves_history_and_independent_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            a, b, c = [store.create_person(name) for name in ("A", "B", "C")]
            first = self._finalize(store, "o1", [a, b])
            second = self._finalize(store, "o2", [a, b])

            result = store.correct_observation_identity(
                first["observation_id"], b.person_id, c.person_id, "correct-o1",
                actor={"username": "operator"},
            )
            retry = store.correct_observation_identity(
                first["observation_id"], b.person_id, c.person_id, "correct-o1",
            )

            self.assertEqual(result, retry)
            self.assertEqual(set(result["participant_ids"]), {a.person_id, c.person_id})
            self.assertEqual(
                {item.person_id for item in store.list_observation_participants(first["observation_id"])},
                {a.person_id, c.person_id},
            )
            self.assertEqual(
                [item.observation_id for item in store.list_observations_for_person(b.person_id)],
                [second["observation_id"]],
            )
            ab = store.get_connection_evidence(a.person_id, b.person_id, include_inactive=True)
            self.assertTrue(any(item.source_entity_id == first["observation_id"] and not item.active for item in ab))
            self.assertTrue(any(item.source_entity_id == second["observation_id"] and item.active for item in ab))
            self.assertEqual(len(store.get_connection_evidence(a.person_id, c.person_id)), 1)
            corrections = store.list_corrections_for_observation(first["observation_id"])
            self.assertTrue(corrections)
            self.assertTrue(all(item.from_person_id == b.person_id for item in corrections))
            self.assertEqual(store.get_operation("correct-o1")["status"], "COMMITTED")
            self.assertTrue(store.validate_graph_projection()["valid"])

    def test_move_only_face_replaces_participant_and_preserves_raw_decision(self):
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            a, b, c = [store.create_person(name) for name in ("A", "B", "C")]
            result = self._finalize(store, "move-one", [a, b])
            embedding_id = result["embedding_assignments"]["face-1"]

            moved = store.move_face(embedding_id, c.person_id, "move-face")
            retry = store.move_face(embedding_id, c.person_id, "move-face")

            self.assertEqual(moved, retry)
            self.assertEqual(
                set(moved["participants_by_observation"][result["observation_id"]]),
                {a.person_id, c.person_id},
            )
            self.assertEqual(store.current_embedding_person_ids([embedding_id])[embedding_id], c.person_id)
            review = store.get_photo_review("move-one")
            self.assertEqual(review.faces[1].person_id, b.person_id)
            self.assertEqual(store.list_corrections_for_embedding(embedding_id)[0].from_person_id, b.person_id)
            self.assertEqual(store.get_operation("move-face")["operation_type"], "identity.face.move")

    def test_moving_one_of_two_faces_keeps_original_participant(self):
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            a, b, c = [store.create_person(name) for name in ("A", "B", "C")]
            result = self._finalize(store, "move-one-of-two", [a, b, b])
            embedding_id = result["embedding_assignments"]["face-1"]

            moved = store.move_face(embedding_id, c.person_id, "move-one-b")

            self.assertEqual(
                set(moved["participants_by_observation"][result["observation_id"]]),
                {a.person_id, b.person_id, c.person_id},
            )
            self.assertEqual(len(store.get_person_neighbors(a.person_id)), 2)

    def test_move_failure_rolls_back_ownership_corrections_graph_and_journal(self):
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            a, b, c = [store.create_person(name) for name in ("A", "B", "C")]
            result = self._finalize(store, "move-fail", [a, b])
            embedding_id = result["embedding_assignments"]["face-1"]
            with patch(
                "sentriface.storage.sqlite_store._replace_graph_projection",
                side_effect=RuntimeError("forced graph failure"),
            ):
                with self.assertRaisesRegex(RuntimeError, "forced graph failure"):
                    IdentityCorrectionService(GlobalIdentityGraphService(store)).move_face(
                        embedding_id, c.person_id, "failed-move",
                    )

            self.assertEqual(store.current_embedding_person_ids([embedding_id])[embedding_id], b.person_id)
            self.assertEqual(store.list_corrections_for_embedding(embedding_id), [])
            self.assertEqual(store.get_operation("failed-move")["status"], "FAILED")

    def test_add_face_preserves_identity_and_creates_no_graph_or_observation(self):
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            person = store.create_identified_person(
                "Raj", {"context": "Known officer"}, "create-raj",
            )
            other = store.create_person("Similar person")
            note = store.create_note(
                person.person_id, "Existing history", "raj-note",
                mentioned_person_ids=[other.person_id],
            )
            self._pending(store, "raj-face", (1.0, 0.0), matches=[])
            store.create_photo_review("add-raj", "raj.jpg", [{
                "face_id": "face-0", "staged_face_type": "PENDING_ADDITION",
                "staged_face_id": "raj-face",
            }], media_path="/managed/raj-face.jpg", source="add-face-review")
            store.set_photo_review_face_decision(
                "add-raj", "face-0", "ACCEPT_EXISTING_PERSON", person_id=person.person_id,
            )

            result = store.add_face_to_person("add-raj", person.person_id, "add-raj-op")
            retry = store.add_face_to_person("add-raj", person.person_id, "add-raj-op")

            self.assertEqual(result, retry)
            self.assertEqual(result["person_id"], person.person_id)
            self.assertEqual(result["created_person_ids"], [])
            self.assertEqual(store.get_person(person.person_id).biometric_status, "ENROLLED")
            self.assertEqual(store.get_note(note.note_id).content, "Existing history")
            self.assertEqual(store.get_person(other.person_id).lifecycle_status, "ACTIVE")
            self.assertEqual(len(store.get_global_graph_projection().connections), 1)
            self.assertEqual(
                [item.evidence_type for item in store.get_connection_evidence(
                    person.person_id, other.person_id,
                )],
                ["NOTE_REFERENCE"],
            )
            self.assertEqual(store.list_observations_for_person(person.person_id), [])
            self.assertEqual(store.get_operation("add-raj-op")["operation_type"], "identity.face.add")

    def test_add_face_failure_rolls_back_embedding_state_and_journal(self):
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            person = store.create_identified_person("Raj", {}, "create-raj")
            self._pending(store, "raj-face", (1.0, 0.0))
            store.create_photo_review("add-raj", "raj.jpg", [{
                "face_id": "face-0", "staged_face_type": "PENDING_ADDITION",
                "staged_face_id": "raj-face",
            }], media_path="/managed/raj-face.jpg", source="add-face-review")
            store.set_photo_review_face_decision(
                "add-raj", "face-0", "ACCEPT_EXISTING_PERSON", person_id=person.person_id,
            )
            with patch(
                "sentriface.storage.sqlite_store._mark_person_enrolled",
                side_effect=RuntimeError("forced enrollment failure"),
            ):
                with self.assertRaisesRegex(RuntimeError, "forced enrollment failure"):
                    IdentityCorrectionService(GlobalIdentityGraphService(store)).add_face_to_person(
                        "add-raj", person.person_id, "add-fail",
                    )

            self.assertEqual(store.list_embeddings_for_person(person.person_id), [])
            self.assertEqual(store.get_photo_review("add-raj").status, "IN_PROGRESS")
            self.assertEqual(store.get_operation("add-fail")["status"], "FAILED")

    def test_add_face_rejects_historical_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            person = store.create_identified_person("Archived", {}, "create-archived")
            self._pending(store, "archived-face", (1.0, 0.0))
            store.create_photo_review("add-archived", "archived.jpg", [{
                "face_id": "face-0", "staged_face_type": "PENDING_ADDITION",
                "staged_face_id": "archived-face",
            }], media_path="/managed/archived-face.jpg", source="add-face-review")
            store.set_photo_review_face_decision(
                "add-archived", "face-0", "ACCEPT_EXISTING_PERSON", person_id=person.person_id,
            )
            store.archive_person(person.person_id, "archive-before-add")

            with self.assertRaisesRegex(KeyError, "Unknown active person"):
                store.add_face_to_person("add-archived", person.person_id, "add-archived-op")

            self.assertIsNone(store.get_operation("add-archived-op"))

    def test_stale_index_resolves_moved_embedding_to_current_owner(self):
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            source = store.create_person("Source")
            target = store.create_person("Target")
            embedding = store.add_embedding(source.person_id, (1.0, 0.0), 0.9)
            stale_index = LinearFaceIndex()
            stale_index.rebuild([embedding])
            store.move_face(embedding.embedding_id, target.person_id, "index-move")
            engine = object.__new__(FaceEngine)
            engine.store = store
            engine.index = stale_index
            engine.config = SimpleNamespace(top_k=3)
            engine._metrics_context = ContextVar("test_metrics", default=MetricsCollector())

            matches = engine._search_unique_people((1.0, 0.0))

            self.assertEqual([item.person_id for item in matches], [target.person_id])

    def test_empty_v23_database_migrates_to_v24(self):
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "sentriface.db"
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                for migration in _schema_migrations():
                    if migration.to_version > 23:
                        break
                    migration.apply(conn)
            store = SQLiteIdentityStore(db_path, embedding_dim=2)
            store.initialize()
            with sqlite3.connect(db_path) as conn:
                self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
                self.assertIsNotNone(conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE name = 'identity_corrections'",
                ).fetchone())

    def test_v23_migration_preserves_existing_graph_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "sentriface.db"
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA foreign_keys=ON")
                for migration in _schema_migrations():
                    if migration.to_version > 23:
                        break
                    migration.apply(conn)
                for person_id in ("person-a", "person-b"):
                    conn.execute(
                        """
                        INSERT INTO persons(
                            person_id, name, metadata, created_at, lifecycle_status,
                            identity_status, biometric_status, lifecycle_changed_at
                        ) VALUES (?, ?, '{}', '2026-01-01T00:00:00+00:00',
                                  'ACTIVE', 'IDENTIFIED', 'NO_FACE',
                                  '2026-01-01T00:00:00+00:00')
                        """,
                        (person_id, person_id),
                    )
                conn.execute(
                    """
                    INSERT INTO operation_journal(
                        operation_id, operation_type, status, actor, context,
                        affected_entities, details, created_at, completed_at
                    ) VALUES ('legacy-op', 'review.complete', 'COMMITTED', '{}', '{}',
                              '[]', '{}', '2026-01-01T00:00:00+00:00',
                              '2026-01-01T00:00:00+00:00')
                    """,
                )
                conn.execute(
                    """
                    INSERT INTO operation_journal_status_history(
                        transition_id, operation_id, from_status, to_status, details, created_at
                    ) VALUES ('legacy-start', 'legacy-op', NULL, 'STARTED', '{}',
                              '2026-01-01T00:00:00+00:00')
                    """,
                )
                conn.execute(
                    """
                    INSERT INTO operation_journal_status_history(
                        transition_id, operation_id, from_status, to_status, details, created_at
                    ) VALUES ('legacy-commit', 'legacy-op', 'STARTED', 'COMMITTED',
                              '{"face_assignments":{"face-0":"person-a"},"embedding_assignments":{"face-0":"legacy-embedding"}}',
                              '2026-01-01T00:00:01+00:00')
                    """,
                )
                conn.execute(
                    """
                    INSERT INTO observations(
                        observation_id, status, source, created_operation_id,
                        created_at, updated_at, finalized_at
                    ) VALUES ('legacy-observation', 'DRAFT', 'legacy', 'legacy-op',
                              '2026-01-01T00:00:00+00:00',
                              '2026-01-01T00:00:00+00:00',
                              NULL)
                    """,
                )
                conn.executemany(
                    """
                    INSERT INTO observation_participants(
                        observation_id, person_id, operation_id, created_at
                    ) VALUES ('legacy-observation', ?, 'legacy-op',
                              '2026-01-01T00:00:00+00:00')
                    """,
                    (("person-a",), ("person-b",)),
                )
                conn.execute(
                    """
                    UPDATE observations
                    SET status = 'FINALIZED', finalized_at = '2026-01-01T00:00:00+00:00'
                    WHERE observation_id = 'legacy-observation'
                    """,
                )
                conn.execute(
                    """
                    INSERT INTO embeddings(
                        embedding_id, person_id, vector, quality_score, created_at
                    ) VALUES ('legacy-embedding', 'person-a', ?, 0.9,
                              '2026-01-01T00:00:00+00:00')
                    """,
                    (b"\x00" * 8,),
                )
                conn.execute(
                    """
                    INSERT INTO photo_reviews(
                        review_id, media_id, source, status, observation_id,
                        completed_operation_id, created_at, completed_at
                    ) VALUES ('legacy-review', 'legacy.jpg', 'legacy', 'COMPLETED',
                              'legacy-observation', 'legacy-op',
                              '2026-01-01T00:00:00+00:00',
                              '2026-01-01T00:00:01+00:00')
                    """,
                )
                conn.execute(
                    """
                    INSERT INTO photo_review_faces(
                        review_id, face_id, staged_face_type, staged_face_id,
                        decision, person_id, created_at, updated_at
                    ) VALUES ('legacy-review', 'face-0', 'PENDING_ADDITION',
                              'legacy-staged', 'ACCEPT_EXISTING_PERSON', 'person-a',
                              '2026-01-01T00:00:00+00:00',
                              '2026-01-01T00:00:00+00:00')
                    """,
                )
                conn.execute(
                    """
                    INSERT INTO relationship_evidence(
                        evidence_id, evidence_type, source_entity_type, source_entity_id,
                        source_person_id, target_person_id, relationship_type,
                        directionality, active, created_operation_id, created_at
                    ) VALUES ('legacy-evidence', 'CO_OBSERVED', 'OBSERVATION',
                              'legacy-observation', 'person-a', 'person-b',
                              'ASSOCIATED_WITH', 'UNDIRECTED', 1, 'legacy-op',
                              '2026-01-01T00:00:00+00:00')
                    """,
                )

            store = SQLiteIdentityStore(db_path, embedding_dim=2)
            store.initialize()

            evidence = store.get_connection_evidence("person-a", "person-b")
            self.assertEqual([item.evidence_id for item in evidence], ["legacy-evidence"])
            self.assertEqual(evidence[0].evidence_revision_id, "legacy-observation")
            self.assertTrue(store.validate_graph_projection()["valid"])
            with sqlite3.connect(db_path) as conn:
                self.assertEqual(conn.execute(
                    "SELECT embedding_id FROM observation_face_assignments",
                ).fetchone()[0], "legacy-embedding")


if __name__ == "__main__":
    unittest.main()
