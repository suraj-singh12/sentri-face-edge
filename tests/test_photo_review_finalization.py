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
from sentriface.storage.sqlite_store import _list_embeddings_in_transaction
from sentriface.engine import FaceEngine
from sentriface.cli import build_dev_engine
from sentriface.config import RuntimeConfig


class PhotoReviewFinalizationTest(unittest.TestCase):
    def _store(self, root: Path) -> SQLiteIdentityStore:
        store = SQLiteIdentityStore(root / "sentriface.db", embedding_dim=2)
        store.initialize()
        return store

    def _pending(
        self, store: SQLiteIdentityStore, pending_id: str, media_path: str, vector: tuple[float, float],
        quality_status: QualityStatus = QualityStatus.GOOD,
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
            quality=QualityReport(quality_status, 0.9),
        ))

    def test_poor_face_state_is_persisted_and_search_policy_is_authoritative(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            person = store.create_person("Known without photo")
            self.assertEqual(store.get_person(person.person_id).biometric_status, "NO_FACE")
            self.assertEqual(store.list_embeddings_for_person(person.person_id), [])
            for index, state in enumerate(("POOR_ACCEPTED", "PROOF_ONLY")):
                staged_id = f"poor-{index}"
                review_id = f"review-{index}"
                self._pending(
                    store, staged_id, f"/managed/{index}.jpg", (1.0 - index * 0.2, index * 0.2),
                    QualityStatus.BAD,
                )
                store.create_photo_review(review_id, f"{index}.jpg", [{
                    "face_id": staged_id, "staged_face_type": "PENDING_ADDITION",
                    "staged_face_id": staged_id,
                }], media_path=f"/managed/{index}.jpg")
                store.set_photo_review_face_decision(
                    review_id, staged_id, "ACCEPT_EXISTING_PERSON", person_id=person.person_id,
                    recognition_detail={"date": "2026-09-27", "time_precision": "unknown", "embedding_state": state},
                )
                store.complete_photo_review(review_id, f"op-{index}")
            records = store.list_embeddings_for_person(person.person_id)
            self.assertEqual({record.recognition_state for record in records}, {"POOR_ACCEPTED", "PROOF_ONLY"})
            self.assertEqual(store.get_person(person.person_id).biometric_status, "ENROLLED")
            ids = [record.embedding_id for record in records]
            self.assertEqual(
                store.current_embedding_person_ids(ids),
                {record.embedding_id: person.person_id for record in records if record.recognition_state == "POOR_ACCEPTED"},
            )
            self.assertEqual(
                store.current_embedding_person_ids(ids, quality_only=False),
                {record.embedding_id: person.person_id for record in records if record.recognition_state == "POOR_ACCEPTED"},
            )
            reopened = self._store(Path(temp))
            self.assertEqual(
                {record.recognition_state for record in reopened.list_embeddings_for_person(person.person_id)},
                {"POOR_ACCEPTED", "PROOF_ONLY"},
            )
            engine = build_dev_engine(Path(temp), RuntimeConfig(data_dir=Path(temp), embedding_dim=2))
            engine.initialize()
            self.assertEqual(
                [match.person_id for match in engine._search_unique_people((1.0, 0.0), quality_only=True)],
                [person.person_id],
            )
            self.assertEqual(
                [match.person_id for match in engine._search_unique_people((1.0, 0.0), quality_only=False)],
                [person.person_id],
            )
            proof = next(record for record in records if record.recognition_state == "PROOF_ONLY")
            self.assertNotIn(proof.embedding_id, [match.embedding_id for match in engine.index.search((1.0, 0.0), 10)])
            engine.index.add(proof)  # stale-cache defense still consults current embedding authority
            self.assertNotIn(
                proof.embedding_id,
                [embedding_id for match in engine._search_unique_people((1.0, 0.0), quality_only=False) for embedding_id in match.embedding_ids],
            )
            with store._connect() as conn:
                merge_records = _list_embeddings_in_transaction(conn)
            engine._publish_merge_index(merge_records)
            self.assertNotIn(
                proof.embedding_id,
                [match.embedding_id for match in engine.index.search((1.0, 0.0), 10)],
            )
            self._pending(store, "good-reference", "/managed/good.jpg", (0.0, 1.0))
            store.create_photo_review("good-review", "good.jpg", [{
                "face_id": "good-face", "staged_face_type": "PENDING_ADDITION",
                "staged_face_id": "good-reference",
            }], media_path="/managed/good.jpg")
            store.set_photo_review_face_decision(
                "good-review", "good-face", "ACCEPT_EXISTING_PERSON", person_id=person.person_id,
            )
            store.complete_photo_review("good-review", "good-op")
            all_records = store.list_embeddings_for_person(person.person_id)
            good_id = next(record.embedding_id for record in all_records if record.recognition_state == "GOOD")
            poor_id = next(record.embedding_id for record in all_records if record.recognition_state == "POOR_ACCEPTED")
            self.assertEqual(store.current_embedding_person_ids([good_id, poor_id]), {good_id: person.person_id})
            self.assertEqual(store.current_embedding_person_ids([good_id, poor_id], quality_only=False), {
                good_id: person.person_id, poor_id: person.person_id,
            })

    def test_proof_only_duplicate_check_prevents_unreviewed_new_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            self._pending(store, "proof-pending", "/managed/proof.jpg", (1.0, 0.0), QualityStatus.BAD)
            store.create_photo_review("proof-source", "proof.jpg", [{
                "face_id": "face-0", "staged_face_type": "PENDING_ADDITION",
                "staged_face_id": "proof-pending",
            }], media_path="/managed/proof.jpg")
            store.set_photo_review_face_decision(
                "proof-source", "face-0", "ACCEPT_NEW_PERSON", new_person_name="Tony",
                recognition_detail={"embedding_state": "PROOF_ONLY"},
            )
            first = store.complete_photo_review("proof-source", "proof-source-op")
            self.assertEqual(len(first["created_person_ids"]), 1)
            self.assertEqual(
                [item["person_id"] for item in store.proof_only_duplicate_candidates([(1.0, 0.0)], 0.5)],
                first["created_person_ids"],
            )
            engine = build_dev_engine(Path(temp), RuntimeConfig(data_dir=Path(temp), embedding_dim=2))
            engine.initialize()
            self.assertEqual(engine._search_unique_people((1.0, 0.0), quality_only=False), [])
            self.assertIsNone(next(
                candidate.match for candidate in engine._rank_people_for_vector((1.0, 0.0))
                if candidate.summary.person.person_id == first["created_person_ids"][0]
            ))
            self._review(store, review_id="possible-duplicate")
            store.set_photo_review_face_decision(
                "possible-duplicate", "face-0", "ACCEPT_NEW_PERSON", new_person_name="Tony Copy",
            )
            with self.assertRaisesRegex(ValueError, "Proof-only duplicate check"):
                store.complete_photo_review("possible-duplicate", "possible-duplicate-op")
            self.assertIsNone(store.get_operation("possible-duplicate-op"))
            store.set_photo_review_face_decision(
                "possible-duplicate", "face-0", "ACCEPT_EXISTING_PERSON",
                person_id=first["created_person_ids"][0],
            )
            existing = store.complete_photo_review("possible-duplicate", "use-existing-op")
            self.assertEqual(existing["created_person_ids"], [])
            self.assertEqual(existing["participant_ids"], first["created_person_ids"])

            self._review(store, review_id="create-anyway")
            store.set_photo_review_face_decision(
                "create-anyway", "face-0", "ACCEPT_NEW_PERSON", new_person_name="Distinct Person",
                recognition_detail={"proof_only_duplicate_override": True},
            )
            rejected = store.complete_photo_review("create-anyway", "create-anyway-op")
            self.assertEqual(len(rejected["created_person_ids"]), 1)
            self.assertNotEqual(rejected["created_person_ids"][0], first["created_person_ids"][0])

    def test_encounter_read_filters_mentions_participation_and_origin(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            present = store.create_person("Present")
            mentioned = store.create_person("Mentioned")
            self._review(store)
            store.set_photo_review_face_decision(
                "review", "face-0", "ACCEPT_EXISTING_PERSON", person_id=present.person_id,
                recognition_detail={
                    "date": "2026-09-26", "time": "19:00", "time_precision": "exact",
                    "place_seen": "Hall", "event_occasion": "Reception", "event_context": "public",
                    "event_notes": "Hosted by @Mentioned", "event_mentioned_person_ids": [mentioned.person_id],
                },
            )
            result = store.complete_photo_review("review", "encounter-read-op")
            observation_id = result["observation_id"]
            embedding_id = result["embedding_ids"][0]
            self.assertEqual(store.face_origins_for_embeddings([embedding_id])[embedding_id][0]["face_origin"], "ENCOUNTER")
            self.assertEqual(store.query_encounters(person_id=present.person_id)["events"][0]["person_status"], "PRESENT")
            mention_event = store.query_encounters(person_id=mentioned.person_id)["events"][0]
            self.assertEqual(mention_event["person_status"], "MENTIONED")
            self.assertEqual(mention_event["person_media"], [])
            self.assertEqual(store.query_encounters(mentioned_person_id=mentioned.person_id)["events"][0]["observation_id"], observation_id)
            self.assertEqual(store.query_encounters(participant_id=mentioned.person_id)["events"], [])
            self.assertEqual(store.query_encounters(location="Elsewhere")["events"], [])
            self.assertEqual(store.query_encounters(context="public")["events"][0]["observation_id"], observation_id)
            self.assertEqual(store.query_encounters(date_from="2026-09-27")["events"], [])
            self.assertEqual(store.query_encounters(search="Reception")["events"][0]["observation_id"], observation_id)
            self.assertEqual(store.get_encounter_read(observation_id)["mentioned_person_ids"], [mentioned.person_id])

    def test_event_pages_and_present_plus_mentioned_do_not_add_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            person = store.create_person("Both")
            for day in ("2026-09-25", "2026-09-27"):
                review_id = f"review-{day}"
                self._review(store, review_id=review_id)
                store.set_photo_review_face_decision(
                    review_id, "face-0", "ACCEPT_EXISTING_PERSON", person_id=person.person_id,
                    recognition_detail={
                        "date": day, "time_precision": "unknown",
                        "event_notes": "Plain @Both", "event_mentioned_person_ids": [person.person_id] if day.endswith("27") else [],
                    },
                )
                store.complete_photo_review(review_id, f"op-{day}")
            first_page = store.query_encounters(limit=1, person_id=person.person_id)
            self.assertEqual(first_page["events"][0]["person_status"], "BOTH")
            self.assertIsNotNone(first_page["next_cursor"])
            second_page = store.query_encounters(limit=1, cursor=first_page["next_cursor"], person_id=person.person_id)
            self.assertEqual(second_page["events"][0]["person_status"], "PRESENT")
            self.assertIsNone(second_page["next_cursor"])
            self.assertEqual(store.query_encounters(person_id=person.person_id, person_status="MENTIONED")["events"], [])
            with sqlite3.connect(store.db_path) as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM relationship_evidence").fetchone()[0], 0)

    def test_event_note_selected_id_has_encounter_provenance_without_graph_edge(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            mentioned = store.create_person("Mentioned without photo")
            self._review(store)
            store.set_photo_review_face_decision(
                "review", "face-0", "ACCEPT_NEW_PERSON", new_person_name="Observed",
                notes="Sighting note @Mentioned", mentioned_person_ids=[],
                recognition_detail={
                    "date": "2026-09-27", "time_precision": "unknown",
                    "event_notes": "Event note @Mentioned",
                    "event_mentioned_person_ids": [mentioned.person_id],
                },
            )
            result = store.complete_photo_review("review", "event-note-op")
            with sqlite3.connect(store.db_path) as conn:
                context = conn.execute(
                    "SELECT context FROM observations WHERE observation_id = ?",
                    (result["observation_id"],),
                ).fetchone()[0]
                note_subjects = conn.execute("SELECT subject_type FROM notes").fetchall()
                evidence_types = conn.execute("SELECT evidence_type FROM relationship_evidence").fetchall()
            import json
            self.assertEqual(json.loads(context)["event_mentioned_person_ids"], [mentioned.person_id])
            self.assertEqual([item[0] for item in note_subjects], ["RECOGNITION_DETAIL"])
            self.assertEqual(evidence_types, [])
            self.assertEqual(store.get_person(mentioned.person_id).biometric_status, "NO_FACE")
            mentioned_events = store.query_encounters(person_id=mentioned.person_id)
            self.assertEqual(len(mentioned_events["events"]), 1)
            self.assertEqual(mentioned_events["events"][0]["person_status"], "MENTIONED")
            self.assertNotIn(mentioned.person_id, mentioned_events["events"][0]["participant_ids"])
            self.assertEqual(store.get_encounter_read(result["observation_id"])["mentioned_person_ids"], [mentioned.person_id])

    def test_new_person_sighting_note_uses_selected_id_reference_not_person_note(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            mentioned = store.create_person("Referenced")
            self._review(store)
            store.set_photo_review_face_decision(
                "review", "face-0", "ACCEPT_NEW_PERSON", new_person_name="Observed",
                notes="Met @Referenced", mentioned_person_ids=[mentioned.person_id],
                recognition_detail={"date": "2026-09-27", "time_precision": "unknown"},
            )
            result = store.complete_photo_review("review", "sighting-note-op")
            observed = store.get_person(result["created_person_ids"][0])
            self.assertEqual(observed.notes, "")
            with sqlite3.connect(store.db_path) as conn:
                subjects = [row[0] for row in conn.execute("SELECT subject_type FROM notes")]
                evidence = [row[0] for row in conn.execute("SELECT evidence_type FROM relationship_evidence")]
            self.assertEqual(subjects, ["RECOGNITION_DETAIL"])
            self.assertEqual(evidence, ["NOTE_REFERENCE"])

    def test_invalid_poor_face_state_rolls_back_person_encounter_and_journal(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            self._pending(
                store, "bad-face", "/managed/bad.jpg", (1.0, 0.0), QualityStatus.BAD,
            )
            store.create_photo_review("bad-review", "bad.jpg", [{
                "face_id": "bad-face", "staged_face_type": "PENDING_ADDITION",
                "staged_face_id": "bad-face",
            }], media_path="/managed/bad.jpg")
            store.set_photo_review_face_decision(
                "bad-review", "bad-face", "ACCEPT_NEW_PERSON", new_person_name="Should Roll Back",
                recognition_detail={"embedding_state": "GOOD"},
            )
            with self.assertRaisesRegex(ValueError, "Poor-quality review face"):
                store.complete_photo_review("bad-review", "bad-review-op")
            with sqlite3.connect(store.db_path) as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM persons").fetchone()[0], 0)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0], 0)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0], 0)
            self.assertIsNone(store.get_operation("bad-review-op"))

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
                    "time_precision": "approximate",
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
            encounter = store.get_observation(result["observation_id"])
            self.assertEqual(encounter.observed_at, "2026-08-08T12:00:00")
            self.assertEqual(encounter.location, "Lobby")
            self.assertEqual(encounter.context["occasion"], "Arrival")
            self.assertEqual(encounter.context["category"], "unknown")
            self.assertEqual(encounter.context["time_precision"], "approximate")
            self.assertEqual(len(result["note_ids"]), 1)
            details = store.list_recognition_details_for_person(first.person_id)
            self.assertEqual(len(details), 1)
            with sqlite3.connect(store.db_path) as conn:
                self.assertEqual(conn.execute(
                    "SELECT observation_id FROM recognition_details WHERE detail_id = ?",
                    (details[0].detail_id,),
                ).fetchone()[0], result["observation_id"])
                self.assertEqual(conn.execute(
                    "SELECT subject_type, subject_id FROM notes WHERE note_id = ?",
                    (result["note_ids"][0],),
                ).fetchone(), ("RECOGNITION_DETAIL", details[0].detail_id))
            evidence = store.get_connection_evidence(first.person_id, mentioned.person_id)
            self.assertEqual([item.evidence_type for item in evidence], ["NOTE_REFERENCE"])
            self.assertEqual(store.get_operation("mixed-op")["status"], "COMMITTED")

    def test_conflicting_face_event_metadata_rolls_back_complete_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            first = store.create_person("First")
            second = store.create_person("Second")
            self._review(store, 2)
            for face, person, place in (("face-0", first, "Lobby"), ("face-1", second, "Gate")):
                store.set_photo_review_face_decision(
                    "review", face, "ACCEPT_EXISTING_PERSON", person_id=person.person_id,
                    recognition_detail={"date": "2026-08-08", "time": "12:00", "place_seen": place},
                )
            with self.assertRaisesRegex(ValueError, "Conflicting Encounter place_seen"):
                store.complete_photo_review("review", "conflict-op")
            self.assertIsNone(store.get_operation("conflict-op"))
            with sqlite3.connect(store.db_path) as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0], 0)

    def test_unselected_literal_mention_creates_no_note_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            owner = store.create_person("Owner")
            mentioned = store.create_person("Mentioned")
            self._review(store)
            store.set_photo_review_face_decision(
                "review", "face-0", "ACCEPT_EXISTING_PERSON", person_id=owner.person_id,
                notes="Saw @Mentioned", mentioned_person_ids=[],
                recognition_detail={"date": "2026-08-08"},
            )
            result = store.complete_photo_review("review", "plain-mention-op")
            self.assertEqual(len(result["note_ids"]), 1)
            self.assertEqual(store.get_connection_evidence(owner.person_id, mentioned.person_id), [])

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
