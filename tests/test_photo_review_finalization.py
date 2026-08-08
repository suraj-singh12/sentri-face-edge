from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sentriface.models import (
    DetectedFace,
    FaceBox,
    MatchDecision,
    InitFace,
    PendingAddition,
    QualityReport,
    QualityStatus,
)
from sentriface.storage.sqlite_store import SCHEMA_VERSION, SQLiteIdentityStore
from sentriface.storage.sqlite_store import _schema_migrations
from sentriface.engine import FaceEngine


class PhotoReviewFinalizationTest(unittest.TestCase):
    def _store(self, root: Path) -> SQLiteIdentityStore:
        store = SQLiteIdentityStore(root / "sentriface.db", embedding_dim=2)
        store.initialize()
        return store

    def _pending(
        self, store: SQLiteIdentityStore, pending_id: str, media_path: str, vector: tuple[float, float],
    ) -> None:
        store.save_pending_addition(PendingAddition(
            pending_id=pending_id,
            source_image=media_path,
            face=DetectedFace(
                box=FaceBox(1, 2, 10, 12, 0.99),
                quality_score=0.9,
                crop_path=f"{media_path}.{pending_id}.crop.jpg",
            ),
            vector=vector,
            matches=[],
            decision=MatchDecision.UNKNOWN,
            quality=QualityReport(QualityStatus.GOOD, 0.9),
        ))

    def _review(self, store: SQLiteIdentityStore, count: int = 1, review_id: str = "review"):
        media_path = "/managed/photo.jpg"
        faces = []
        for index in range(count):
            pending_id = f"pending-{review_id}-{index}"
            self._pending(store, pending_id, media_path, (1.0 - index * 0.1, index * 0.1))
            faces.append({
                "face_id": f"face-{index}",
                "staged_face_type": "PENDING_ADDITION",
                "staged_face_id": pending_id,
            })
        return store.create_photo_review(
            review_id, "photo.jpg", faces, media_path=media_path,
        )

    def test_fresh_schema_and_incomplete_review_cannot_finalize(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            self._review(store, 2)
            person = store.create_person("Existing")
            store.set_photo_review_face_decision(
                "review", "face-0", "ACCEPT_EXISTING_PERSON", person_id=person.person_id,
            )

            with self.assertRaisesRegex(ValueError, "Every detected face"):
                store.complete_photo_review("review", "incomplete-op")

            self.assertIsNone(store.get_operation("incomplete-op"))
            with sqlite3.connect(store.db_path) as conn:
                self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0], 0)

    def test_v22_database_migrates_without_changing_existing_people(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "sentriface.db"
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                for migration in _schema_migrations():
                    if migration.to_version > 22:
                        break
                    migration.apply(conn)
                conn.execute(
                    """
                    INSERT INTO persons(
                        person_id, name, metadata, created_at, lifecycle_status,
                        identity_status, biometric_status, lifecycle_changed_at
                    ) VALUES ('legacy', 'Legacy', '{}', '2026-01-01T00:00:00+00:00',
                              'ACTIVE', 'IDENTIFIED', 'NO_FACE', '2026-01-01T00:00:00+00:00')
                    """,
                )
            store = SQLiteIdentityStore(db_path, embedding_dim=2)
            store.initialize()

            self.assertEqual(store.get_person("legacy").name, "Legacy")
            with sqlite3.connect(db_path) as conn:
                self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
                self.assertIsNotNone(conn.execute(
                    "SELECT name FROM sqlite_master WHERE name = 'photo_reviews'",
                ).fetchone())

    def test_single_existing_and_single_new_finalize_without_edges(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            existing = store.create_person("Existing")
            self._review(store, review_id="existing")
            store.set_photo_review_face_decision(
                "existing", "face-0", "ACCEPT_EXISTING_PERSON", person_id=existing.person_id,
            )
            existing_result = store.complete_photo_review("existing", "existing-op")

            self._review(store, review_id="new")
            store.set_photo_review_face_decision(
                "new", "face-0", "ACCEPT_NEW_PERSON", new_person_name="New Person",
            )
            new_result = store.complete_photo_review("new", "new-op")

            self.assertEqual(existing_result["graph_evidence_count"], 0)
            self.assertEqual(new_result["graph_evidence_count"], 0)
            self.assertEqual(len(new_result["created_person_ids"]), 1)
            self.assertEqual(store.get_photo_review("new").status, "COMPLETED")

    def test_mixed_three_people_skip_and_notes_commit_together(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            first = store.create_person("First")
            mentioned = store.create_person("Mentioned")
            self._review(store, 4)
            store.set_photo_review_face_decision(
                "review", "face-0", "ACCEPT_EXISTING_PERSON", person_id=first.person_id,
                notes="Met @Mentioned", mentioned_person_ids=[mentioned.person_id],
                recognition_detail={
                    "image_id": "photo.jpg#face-0",
                    "date": "2026-08-08",
                    "time": "12:00",
                    "place_seen": "Lobby",
                    "individual_count": 3,
                    "event_occasion": "Arrival",
                },
            )
            store.set_photo_review_face_decision(
                "review", "face-1", "ACCEPT_NEW_PERSON", new_person_name="Second",
            )
            store.set_photo_review_face_decision(
                "review", "face-2", "ACCEPT_NEW_PERSON", new_person_name="Third",
            )
            store.set_photo_review_face_decision("review", "face-3", "SKIP")

            result = store.complete_photo_review("review", "mixed-op")

            self.assertEqual(len(result["participant_ids"]), 3)
            self.assertEqual(result["graph_evidence_count"], 3)
            self.assertEqual(result["excluded_count"], 1)
            self.assertEqual(len(result["note_ids"]), 1)
            details = store.list_recognition_details_for_person(first.person_id)
            self.assertEqual(len(details), 1)
            with sqlite3.connect(store.db_path) as conn:
                self.assertEqual(conn.execute(
                    "SELECT observation_id FROM recognition_details WHERE detail_id = ?",
                    (details[0].detail_id,),
                ).fetchone()[0], result["observation_id"])
            evidence = store.get_connection_evidence(first.person_id, mentioned.person_id)
            self.assertEqual([item.evidence_type for item in evidence], ["NOTE_REFERENCE"])
            self.assertEqual(store.get_operation("mixed-op")["status"], "COMMITTED")

    def test_duplicate_assignments_preserve_faces_but_one_participant(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            person = store.create_person("Same Person")
            self._review(store, 2)
            for face_id in ("face-0", "face-1"):
                store.set_photo_review_face_decision(
                    "review", face_id, "ACCEPT_EXISTING_PERSON", person_id=person.person_id,
                )

            result = store.complete_photo_review("review", "duplicate-op")

            self.assertEqual(result["participant_ids"], [person.person_id])
            self.assertEqual(result["graph_evidence_count"], 0)
            self.assertEqual(len(result["face_assignments"]), 2)
            self.assertEqual(
                len(store.list_observation_participants(result["observation_id"])), 1,
            )

    def test_all_new_grouping_and_retry_are_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            self._review(store, 3)
            store.set_photo_review_face_decision(
                "review", "face-0", "ACCEPT_NEW_PERSON",
                new_person_key="pair", new_person_name="Pair",
            )
            store.set_photo_review_face_decision(
                "review", "face-1", "ACCEPT_NEW_PERSON",
                new_person_key="pair", new_person_name="Pair",
            )
            store.set_photo_review_face_decision(
                "review", "face-2", "ACCEPT_NEW_PERSON",
                new_person_key="third", new_person_name="Third",
            )

            first = store.complete_photo_review("review", "retry-op")
            second = store.complete_photo_review("review", "retry-op")

            self.assertEqual(first, second)
            self.assertEqual(len(first["created_person_ids"]), 2)
            self.assertEqual(len(first["participant_ids"]), 2)
            self.assertEqual(first["graph_evidence_count"], 1)

    def test_queue_staged_faces_attach_all_media_and_finalize_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            session = store.create_init_session("/managed/queue")
            faces = []
            for index, media_path in enumerate(("/managed/one.jpg", "/managed/two.jpg")):
                faces.append(InitFace(
                    init_face_id=f"init-{index}",
                    session_id=session.session_id,
                    group_id="group",
                    source_image=media_path,
                    face=DetectedFace(
                        FaceBox(1, 1, 10, 10, 0.9), 0.9,
                        crop_path=f"{media_path}.crop.jpg",
                    ),
                    vector=(1.0 - index * 0.1, index * 0.1),
                    quality=QualityReport(QualityStatus.GOOD, 0.9),
                ))
            store.save_init_faces(faces)
            store.create_photo_review(
                "queue-review",
                "one.jpg",
                [
                    {
                        "face_id": face.init_face_id,
                        "staged_face_type": "INIT_FACE",
                        "staged_face_id": face.init_face_id,
                    }
                    for face in faces
                ],
                media_path=faces[0].source_image,
                source="queue",
            )
            for face in faces:
                store.set_photo_review_face_decision(
                    "queue-review", face.init_face_id, "ACCEPT_NEW_PERSON",
                    new_person_key="same-person", new_person_name="Queue Person",
                )

            result = store.complete_photo_review("queue-review", "queue-review-op")

            self.assertEqual(len(result["participant_ids"]), 1)
            self.assertEqual(len(store.list_observation_media(result["observation_id"])), 2)
            self.assertEqual(store.list_init_groups(session.session_id), [])

    def test_graph_failure_rolls_back_every_authoritative_write(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            self._review(store, 2)
            for index, name in enumerate(("First", "Second")):
                store.set_photo_review_face_decision(
                    "review", f"face-{index}", "ACCEPT_NEW_PERSON", new_person_name=name,
                )

            with patch(
                "sentriface.storage.sqlite_store._replace_graph_projection",
                side_effect=RuntimeError("forced graph failure"),
            ):
                with self.assertRaisesRegex(RuntimeError, "forced graph failure"):
                    store.complete_photo_review("review", "rollback-op")

            self.assertEqual(store.get_photo_review("review").status, "IN_PROGRESS")
            self.assertIsNone(store.get_operation("rollback-op"))
            with sqlite3.connect(store.db_path) as conn:
                for table in ("persons", "embeddings", "observations", "observation_participants", "relationship_evidence"):
                    self.assertEqual(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)

    def test_event_failure_rolls_back_new_person_and_leaves_graph_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            self._review(store)
            store.set_photo_review_face_decision(
                "review", "face-0", "ACCEPT_NEW_PERSON", new_person_name="Transient",
            )

            with patch(
                "sentriface.storage.sqlite_store._attach_observation_media",
                side_effect=RuntimeError("forced event failure"),
            ):
                with self.assertRaisesRegex(RuntimeError, "forced event failure"):
                    store.complete_photo_review("review", "event-failure-op")

            self.assertIsNone(store.get_operation("event-failure-op"))
            with sqlite3.connect(store.db_path) as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM persons").fetchone()[0], 0)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0], 0)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM relationship_evidence").fetchone()[0], 0)

    def test_cancel_and_invalid_lifecycle_selection_leave_no_authoritative_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            archived = store.create_person("Archived")
            store.archive_person(archived.person_id, "archive-op")
            self._review(store)

            with self.assertRaisesRegex(KeyError, "Unknown active person"):
                store.set_photo_review_face_decision(
                    "review", "face-0", "ACCEPT_EXISTING_PERSON",
                    person_id=archived.person_id,
                )
            cancelled = store.cancel_photo_review("review")

            self.assertEqual(cancelled.status, "CANCELLED")
            with sqlite3.connect(store.db_path) as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0], 0)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM relationship_evidence").fetchone()[0], 0)

    def test_old_pending_and_queue_domain_confirmation_paths_are_gated(self) -> None:
        for method_name in (
            "confirm_pending_as_new_person",
            "confirm_pending_as_existing_person",
            "confirm_init_group",
            "confirm_init_group_existing",
            "confirm_new_person",
            "confirm_existing_person",
        ):
            self.assertFalse(hasattr(FaceEngine, method_name), method_name)


if __name__ == "__main__":
    unittest.main()
