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
from sentriface.media_registry import media_content_identity
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

    def test_v29_review_migrates_to_v30_without_changing_historical_media(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "sentriface.db"
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                for migration in _schema_migrations():
                    if migration.to_version > 29:
                        break
                    migration.apply(conn)
                conn.execute(
                    "INSERT INTO photo_reviews(review_id, media_id, media_path, source, status, created_at) "
                    "VALUES ('legacy-review', 'legacy-media', '/managed/legacy.jpg', 'check-photo', "
                    "'CANCELLED', '2026-01-01T00:00:00+00:00')"
                )
            store = SQLiteIdentityStore(db_path, embedding_dim=2)
            store.initialize()
            with sqlite3.connect(db_path) as conn:
                self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
                self.assertEqual(conn.execute(
                    "SELECT review_phase, media_path FROM photo_reviews WHERE review_id = 'legacy-review'"
                ).fetchone(), ("LEGACY", "/managed/legacy.jpg"))
                self.assertEqual(conn.execute(
                    "SELECT media_id, media_path FROM photo_review_media WHERE review_id = 'legacy-review'"
                ).fetchone(), ("legacy-media", "/managed/legacy.jpg"))

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

    def test_durable_encounter_review_relations_commit_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = self._store(root)
            session = store.create_init_session("/managed/queue")
            media = ["/managed/one.jpg", "/managed/two.jpg"]
            store.save_init_session_media(session.session_id, [*media, media[0]])
            faces = [
                InitFace(
                    init_face_id=f"encounter-face-{index}", session_id=session.session_id,
                    group_id=f"group-{index}", source_image=media[index // 2],
                    face=DetectedFace(FaceBox(1, 1, 10, 10, 0.9), 0.9),
                    vector=(1.0 - index * 0.2, index * 0.2),
                    quality=QualityReport(QualityStatus.GOOD, 0.9),
                ) for index in range(3)
            ]
            store.save_init_faces(faces)
            media_ids = [item["media_id"] for item in store.list_init_session_media(session.session_id)]
            planned = store.plan_init_session_encounters(session.session_id, [media_ids])
            review_id = planned[0]["review_id"]
            store.save_encounter_review_event(review_id, {
                "date": "2026-09-28", "time_precision": "unknown", "event_context": "ordinary",
                "event_occasion": "Meeting", "event_notes": "Three participants",
                "event_mentioned_person_ids": [],
            })
            self.assertEqual(store.query_encounters()["events"], [])
            for index, face in enumerate(faces):
                store.set_photo_review_face_decision(
                    review_id, face.init_face_id, "ACCEPT_NEW_PERSON",
                    new_person_key=f"person-{index}", new_person_name=f"Person {index}",
                )
            reopened = self._store(root)
            self.assertTrue(reopened.list_init_session_encounter_reviews(session.session_id)[0]["event_details_complete"])
            ready = reopened.complete_encounter_identity_review(review_id)
            self.assertEqual(ready["phase"], "RELATIONS")
            candidates = ready["relation_candidates"]
            self.assertEqual(len(candidates), 3)
            self.assertEqual(
                {item["support"] for item in candidates},
                {"SHARED_FRAME", "SAME_ENCOUNTER_ONLY"},
            )
            for index, candidate in enumerate(candidates):
                reopened.set_encounter_relation_decision(
                    review_id, candidate["first_ref"], candidate["second_ref"],
                    "EXCLUDE" if index == 0 else "INCLUDE",
                )
            self.assertEqual(reopened.query_encounters()["events"], [])
            result = reopened.complete_photo_review(review_id, "encounter-final-op")
            self.assertEqual(reopened.complete_photo_review(review_id, "encounter-final-op"), result)
            self.assertEqual(len(result["created_person_ids"]), 3)
            self.assertEqual(len(result["participant_ids"]), 3)
            self.assertEqual(len(reopened.list_observation_media(result["observation_id"])), 2)
            self.assertEqual(result["graph_evidence_count"], 2)
            reopened.rebuild_graph_projection("encounter-rebuild-op", reason="Verify excluded pair remains absent")
            with sqlite3.connect(reopened.db_path) as conn:
                self.assertEqual(conn.execute(
                    "SELECT COUNT(*) FROM encounter_relation_decisions WHERE observation_id = ? AND active = 1",
                    (result["observation_id"],),
                ).fetchone()[0], 3)
                self.assertEqual(conn.execute(
                    "SELECT COUNT(*) FROM relationship_evidence WHERE evidence_type = 'CO_OBSERVED' AND active = 1",
                ).fetchone()[0], 2)
            replacement = reopened.create_person("Corrected Person")
            reopened.correct_observation_identity(
                result["observation_id"], result["participant_ids"][0], replacement.person_id,
                "encounter-correction-op",
            )
            with sqlite3.connect(reopened.db_path) as conn:
                active_decisions = conn.execute(
                    "SELECT first_person_id, second_person_id, disposition FROM encounter_relation_decisions "
                    "WHERE observation_id = ? AND active = 1",
                    (result["observation_id"],),
                ).fetchall()
                active_evidence = conn.execute(
                    "SELECT source_person_id, target_person_id FROM relationship_evidence "
                    "WHERE source_entity_id = ? AND evidence_type = 'CO_OBSERVED' AND active = 1",
                    (result["observation_id"],),
                ).fetchall()
                self.assertGreater(conn.execute(
                    "SELECT COUNT(*) FROM encounter_relation_decisions WHERE observation_id = ? AND active = 0",
                    (result["observation_id"],),
                ).fetchone()[0], 0)
            included = {tuple(sorted((a, b))) for a, b, disposition in active_decisions if disposition == "INCLUDE"}
            excluded = {tuple(sorted((a, b))) for a, b, disposition in active_decisions if disposition == "EXCLUDE"}
            evidence_pairs = {tuple(sorted((a, b))) for a, b in active_evidence}
            self.assertEqual(evidence_pairs, included)
            self.assertFalse(evidence_pairs & excluded)

            duplicate_session = reopened.create_init_session("/managed/second-queue")
            reopened.save_init_session_media(duplicate_session.session_id, [media[0]])
            with self.assertRaisesRegex(ValueError, "already belongs to finalized Encounter"):
                reopened.plan_init_session_encounters(
                    duplicate_session.session_id,
                    [[item["media_id"] for item in reopened.list_init_session_media(duplicate_session.session_id)]],
                )

    def test_mixed_finalized_media_can_be_excluded_before_planning(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = self._store(root)
            owner = store.create_person("Media owner")
            previous = store.create_observation(
                "media-previous", participant_ids=[owner.person_id],
                observed_at="2026-09-27T10:00:00+00:00",
            )
            existing_path = "/managed/already.jpg"
            self._pending(store, "media-existing-pending", existing_path, (1.0, 0.0))
            store.attach_observation_media(
                previous.observation_id, media_content_identity(existing_path),
                "media-existing", media_path=existing_path,
            )
            store._finalize_observation_without_graph_evidence(previous.observation_id, "media-previous-final")
            session = store.create_init_session("/managed/mixed")
            fresh_path = "/managed/fresh.jpg"
            store.save_init_session_media(session.session_id, [existing_path, fresh_path])
            store.save_init_faces([InitFace(
                init_face_id="fresh-face", session_id=session.session_id,
                group_id="fresh-group", source_image=fresh_path,
                face=DetectedFace(FaceBox(1, 1, 10, 10, 0.9), 0.9),
                vector=(1.0, 0.0), quality=QualityReport(QualityStatus.GOOD, 0.9),
            )])
            media = store.list_init_session_media(session.session_id)
            by_path = {item["media_path"]: item for item in media}
            self.assertEqual(by_path[existing_path]["finalized_encounter"]["observation_id"], previous.observation_id)
            self.assertEqual(by_path[fresh_path]["face_count"], 1)
            with self.assertRaisesRegex(ValueError, "already belongs to finalized Encounter"):
                store.plan_init_session_encounters(session.session_id, [[item["media_id"] for item in media]])
            self.assertEqual(store.list_init_session_encounter_reviews(session.session_id), [])
            planned = store.plan_init_session_encounters(session.session_id, [[by_path[fresh_path]["media_id"]]])
            self.assertEqual(len(planned), 1)
            self.assertEqual(planned[0]["media"][0]["media_id"], by_path[fresh_path]["media_id"])

    def test_encounter_skip_defers_without_resolving_and_returns_automatically(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            engine = build_dev_engine(root, RuntimeConfig(data_dir=root, embedding_dim=2))
            engine.initialize()
            store = engine.store
            session = store.create_init_session("/managed/skip")
            paths = ["/managed/skip-a.jpg", "/managed/skip-b.jpg"]
            store.save_init_session_media(session.session_id, paths)
            store.save_init_faces([InitFace(
                init_face_id=f"skip-face-{index}", session_id=session.session_id,
                group_id=f"skip-group-{index}", source_image=path,
                face=DetectedFace(FaceBox(1, 1, 10, 10, 0.9), 0.9),
                vector=(1.0 - index, float(index)),
                quality=QualityReport(QualityStatus.GOOD, 0.9),
            ) for index, path in enumerate(paths)])
            review_id = engine.plan_init_session_encounters(session.session_id, [[
                item["media_id"] for item in store.list_init_session_media(session.session_id)
            ]])[0]["review_id"]
            store.save_encounter_review_event(review_id, {"date": "2026-09-28", "time_precision": "unknown"})
            groups = engine.list_init_groups(session.session_id)
            self.assertEqual(len(groups), 2)
            self.assertEqual(engine.skip_encounter_identity_group(review_id, groups[0].group_id), 0)
            self.assertEqual(store.get_encounter_review(review_id)["identity_resolved"], 0)
            with self.assertRaisesRegex(ValueError, "final identity decision"):
                store.complete_encounter_identity_review(review_id)
            self.assertEqual(engine.skip_encounter_identity_group(review_id, groups[1].group_id), 2)
            self.assertEqual({item.status for item in engine.list_init_groups(session.session_id)}, {"pending"})
            self.assertEqual(engine.skip_encounter_identity_group(review_id, groups[0].group_id), 0)
            engine.set_photo_review_face_decision(
                review_id, "skip-face-1", "ACCEPT_NEW_PERSON", new_person_name="Resolved",
            )
            self.assertEqual({item.status for item in engine.list_init_groups(session.session_id)}, {"pending"})
            with self.assertRaisesRegex(ValueError, "defers"):
                store.set_photo_review_face_decision(review_id, "skip-face-0", "SKIP")
            engine.set_photo_review_face_decision(
                review_id, "skip-face-0", "EXCLUDE",
            )
            self.assertEqual(store.get_encounter_review(review_id)["identity_resolved"], 2)
            self.assertEqual(store.complete_encounter_identity_review(review_id)["phase"], "RELATIONS")

    def test_draft_recognition_overlay_respects_quality_and_never_enters_global_index(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = self._store(root)
            for quality_only, state, expected in (
                (True, "GOOD", True),
                (True, "POOR_ACCEPTED", True),
                (False, "POOR_ACCEPTED", True),
                (False, "PROOF_ONLY", False),
            ):
                session = store.create_init_session(f"/managed/queue-{quality_only}-{state}", quality_only=quality_only)
                media = [f"/managed/{session.session_id}-{index}.jpg" for index in range(2)]
                store.save_init_session_media(session.session_id, media)
                staged = [InitFace(
                    init_face_id=f"{session.session_id}-{index}", session_id=session.session_id,
                    group_id=f"group-{index}", source_image=media[index],
                    face=DetectedFace(FaceBox(1, 1, 10, 10, 0.9), 0.9),
                    vector=(1.0, 0.0),
                    quality=QualityReport(
                        QualityStatus.BAD if index == 0 and state != "GOOD" else QualityStatus.GOOD, 0.9,
                    ),
                ) for index in range(2)]
                store.save_init_faces(staged)
                review_id = store.plan_init_session_encounters(
                    session.session_id,
                    [[item["media_id"] for item in store.list_init_session_media(session.session_id)]],
                )[0]["review_id"]
                store.save_encounter_review_event(review_id, {"date": "2026-09-28", "time_precision": "unknown"})
                store.set_photo_review_face_decision(
                    review_id, staged[0].init_face_id, "ACCEPT_NEW_PERSON",
                    new_person_key="draft-a", new_person_name="Draft Person",
                    recognition_detail={"embedding_state": state},
                )
                engine = build_dev_engine(root, RuntimeConfig(data_dir=root, embedding_dim=2))
                engine.initialize()
                candidate = next(group for group in engine.list_init_groups(session.session_id) if group.group_id == "group-1")
                matches = engine.draft_matches_for_init_group(candidate, review_id)
                self.assertEqual(bool(matches), expected)
                self.assertEqual(engine._search_unique_people((1.0, 0.0), quality_only=False), [])

    def test_exact_media_bytes_deduplicate_across_filenames(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = root / "first.jpg"
            second = root / "renamed.jpg"
            first.write_bytes(b"identical retained media")
            second.write_bytes(first.read_bytes())
            self.assertEqual(media_content_identity(first), media_content_identity(second))
            store = self._store(root)
            session = store.create_init_session(str(root))
            store.save_init_session_media(session.session_id, [str(first), str(second)])
            self.assertEqual(len(store.list_init_session_media(session.session_id)), 1)

    def _active_queue_draft(self, store, suffix="matrix"):
        session = store.create_init_session(f"/managed/{suffix}")
        media = [f"/managed/{session.session_id}-{index}.jpg" for index in range(3)]
        store.save_init_session_media(session.session_id, media)
        faces = [InitFace(
            init_face_id=f"{session.session_id}-{index}", session_id=session.session_id,
            group_id=f"group-{index}", source_image=path,
            face=DetectedFace(FaceBox(1, 1, 10, 10, 0.9), 0.9), vector=(1.0, 0.0),
            quality=QualityReport(QualityStatus.BAD if index < 2 else QualityStatus.GOOD, 0.9),
        ) for index, path in enumerate(media)]
        store.save_init_faces(faces)
        review_id = store.plan_init_session_encounters(session.session_id, [[item["media_id"] for item in store.list_init_session_media(session.session_id)]])[0]["review_id"]
        store.save_encounter_review_event(review_id, {"time_precision": "unknown"})
        return session, review_id, faces

    def test_combined_committed_and_draft_quality_matrix_uses_person_identity(self):
        for committed_state, draft_state, on_score in (
            ("GOOD", "POOR_ACCEPTED", 0.0),
            ("POOR_ACCEPTED", "GOOD", 1.0),
            ("PROOF_ONLY", "POOR_ACCEPTED", 1.0),
            ("POOR_ACCEPTED", "PROOF_ONLY", 0.0),
            ("PROOF_ONLY", "PROOF_ONLY", None),
        ):
            with self.subTest(committed=committed_state, draft=draft_state), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                store = self._store(root)
                person = store.create_person("Tony")
                record = store.add_embedding(person.person_id, (0.0, 1.0), 0.9)
                with store._connect() as conn:
                    conn.execute("UPDATE embeddings SET recognition_state = ? WHERE embedding_id = ?", (committed_state, record.embedding_id))
                session, review_id, faces = self._active_queue_draft(store)
                if draft_state == "GOOD":
                    with store._connect() as conn:
                        conn.execute("UPDATE init_faces SET quality_status = 'good' WHERE init_face_id = ?", (faces[0].init_face_id,))
                store.set_photo_review_face_decision(review_id, faces[0].init_face_id, "ACCEPT_EXISTING_PERSON", person_id=person.person_id, recognition_detail={"embedding_state": draft_state})
                engine = build_dev_engine(root, RuntimeConfig(data_dir=root, embedding_dim=2))
                engine.initialize()
                group = next(item for item in engine.list_init_groups(session.session_id) if item.group_id == "group-2")
                on = engine.encounter_matches_for_init_group(group, review_id)
                self.assertEqual(on[0]["score"] if on else None, on_score if on_score else None)
                store.set_init_session_quality_policy(session.session_id, False)
                off = engine.encounter_matches_for_init_group(group, review_id)
                expected_off = 1.0 if draft_state != "PROOF_ONLY" else None
                self.assertEqual(off[0]["score"] if off else None, expected_off)
                for candidate in on + off:
                    self.assertEqual(candidate["person_id"], person.person_id)
                    self.assertFalse(candidate["draft_created"])
                self.assertEqual(len(store.list_embeddings()), 1)
                engine._rebuild_index()
                reopened = self._store(root)
                self.assertEqual(len(reopened.list_encounter_draft_references(review_id)), 1)
                store.cancel_photo_review(review_id)
                self.assertEqual(engine.encounter_matches_for_init_group(group, review_id), [])
                self.assertEqual(len(store.list_embeddings()), 1)

    def test_draft_proof_only_duplicate_guard_reuse_override_and_atomic_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = self._store(root)
            session, review_id, faces = self._active_queue_draft(store)
            store.set_photo_review_face_decision(review_id, faces[0].init_face_id, "ACCEPT_NEW_PERSON", new_person_key="tony", new_person_name="Tony", recognition_detail={"embedding_state": "PROOF_ONLY"})
            reopened = self._store(root)
            candidates = reopened.proof_only_duplicate_candidates([faces[2].vector], 0.5, review_id=review_id)
            self.assertEqual([(item["name"], item["draft_created"], item["draft_person_key"]) for item in candidates], [("Tony", True, "tony")])
            engine = build_dev_engine(root, RuntimeConfig(data_dir=root, embedding_dim=2))
            engine.initialize()
            group = next(item for item in engine.list_init_groups(session.session_id) if item.group_id == "group-2")
            self.assertEqual(engine.encounter_matches_for_init_group(group, review_id), [])
            for quality in (True, False):
                self.assertEqual(engine._search_unique_people((1.0, 0.0), quality_only=quality), [])
            with self.assertRaisesRegex(ValueError, "proof-only Person"):
                store.set_photo_review_face_decision(review_id, faces[2].init_face_id, "ACCEPT_NEW_PERSON", new_person_key="tony2", new_person_name="Tony 2")
            with self.assertRaisesRegex(KeyError, "Unknown review face"):
                store.set_photo_review_face_decisions(review_id, [{"face_id": faces[1].init_face_id}, {"face_id": "missing"}], decision="ACCEPT_NEW_PERSON", new_person_key="tony", new_person_name="Tony")
            self.assertEqual(store.get_encounter_review(review_id)["identity_resolved"], 1)
            store.set_photo_review_face_decision(review_id, faces[1].init_face_id, "ACCEPT_NEW_PERSON", new_person_key="tony", new_person_name="Tony", recognition_detail={"embedding_state": "PROOF_ONLY"})
            self.assertEqual(len(store.proof_only_duplicate_candidates([faces[2].vector], 0.5, review_id=review_id)), 1)
            store.set_photo_review_face_decision(review_id, faces[2].init_face_id, "ACCEPT_NEW_PERSON", new_person_key="tony2", new_person_name="Tony 2", recognition_detail={"proof_only_duplicate_override": True})
            self.assertEqual(store.get_encounter_review(review_id)["identity_resolved"], 3)
            self.assertEqual(store.list_persons(), [])
            self.assertEqual(store.list_embeddings(), [])
            store.cancel_photo_review(review_id)
            self.assertEqual(store.proof_only_duplicate_candidates([(1.0, 0.0)], 0.5, review_id=review_id), [])

    def test_durable_media_removal_restart_restore_and_grouping_lock(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = self._store(root)
            session = store.create_init_session("/managed/removal")
            media = [root / f"remove-{index}.jpg" for index in range(2)]
            for index, path in enumerate(media):
                path.write_bytes(f"fixture-{index}".encode())
            store.save_init_session_media(session.session_id, [str(path) for path in media])
            store.save_init_faces([InitFace(init_face_id=f"remove-{index}", session_id=session.session_id, group_id=f"group-{index}", source_image=str(path), face=DetectedFace(FaceBox(1, 1, 10, 10, 0.9), 0.9), vector=(1.0, 0.0), quality=QualityReport(QualityStatus.GOOD, 0.9)) for index, path in enumerate(media)])
            items = store.list_init_session_media(session.session_id)
            excluded = items[0]["media_id"]
            store.set_init_media_excluded(session.session_id, excluded, True)
            store = self._store(root)
            self.assertTrue(next(item for item in store.list_init_session_media(session.session_id) if item["media_id"] == excluded)["excluded"])
            with self.assertRaisesRegex(ValueError, "Every selected media"):
                store.plan_init_session_encounters(session.session_id, [[item["media_id"] for item in items]])
            store.set_init_media_excluded(session.session_id, excluded, False)
            store.set_init_media_excluded(session.session_id, excluded, True)
            engine = build_dev_engine(root, RuntimeConfig(data_dir=root, embedding_dim=2))
            engine.initialize()
            reviews = engine.plan_init_session_encounters(session.session_id, [[item["media_id"] for item in items if item["media_id"] != excluded]])
            self.assertEqual(len(reviews[0]["faces"]), 1)
            for _ in range(3):
                groups = engine.refresh_init_groups(session.session_id)
                review_face = reviews[0]["faces"][0]["face_id"]
                group = next(group for group in groups if any(face.init_face_id == review_face for face in group.faces))
                self.assertEqual(engine.get_init_group(session.session_id, group.group_id).group_id, group.group_id)
            with self.assertRaisesRegex(ValueError, "locked"):
                store.set_init_media_excluded(session.session_id, excluded, False)
            self.assertTrue(all(path.exists() for path in media))
            self.assertEqual(store.query_encounters()["events"], [])

    def test_serial_encounters_resume_after_first_commit_and_close_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = self._store(root)
            session = store.create_init_session("/managed/serial")
            media = ["/managed/serial-1.jpg", "/managed/serial-2.jpg"]
            store.save_init_session_media(session.session_id, media)
            store.save_init_faces([InitFace(
                init_face_id=f"serial-{index}", session_id=session.session_id,
                group_id=f"group-{index}", source_image=path,
                face=DetectedFace(FaceBox(1, 1, 10, 10, 0.9), 0.9),
                vector=(1.0, 0.0), quality=QualityReport(QualityStatus.GOOD, 0.9),
            ) for index, path in enumerate(media)])
            ids_by_path = {item["media_path"]: item["media_id"] for item in store.list_init_session_media(session.session_id)}
            reviews = store.plan_init_session_encounters(
                session.session_id, [[ids_by_path[media[0]]], [ids_by_path[media[1]]]],
            )
            self.assertEqual([item["phase"] for item in reviews], ["EVENT", "WAITING"])
            with self.assertRaisesRegex(ValueError, "active Encounter"):
                store.save_encounter_review_event(reviews[1]["review_id"], {"date": "2026-09-28"})
            first_id = reviews[0]["review_id"]
            store.save_encounter_review_event(first_id, {"date": "2026-09-28", "time_precision": "unknown"})
            store.set_photo_review_face_decision(
                first_id, "serial-0", "ACCEPT_NEW_PERSON",
                new_person_key="first", new_person_name="First",
            )
            store.complete_encounter_identity_review(first_id)
            store.complete_photo_review(first_id, "serial-first-op")
            resumed = self._store(root).list_init_session_encounter_reviews(session.session_id)
            self.assertEqual([item["phase"] for item in resumed], ["RELATIONS", "EVENT"])
            self.assertEqual([item["status"] for item in resumed], ["COMPLETED", "IN_PROGRESS"])
            store.save_encounter_review_event(reviews[1]["review_id"], {"date": "2026-09-29", "time_precision": "unknown"})
            store.set_photo_review_face_decision(
                reviews[1]["review_id"], "serial-1", "ACCEPT_NEW_PERSON",
                new_person_key="second", new_person_name="Second",
            )
            store.complete_encounter_identity_review(reviews[1]["review_id"])
            store.complete_photo_review(reviews[1]["review_id"], "serial-second-op")
            self.assertEqual(store.list_init_sessions(), [])
            self.assertEqual(len(store.list_init_session_encounter_reviews(session.session_id)), 2)

    def test_active_draft_lifecycle_guards_and_merge_relation_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            people = [store.create_person(name) for name in ("A", "B", "C")]
            session = store.create_init_session("/managed/guards")
            path = "/managed/guards.jpg"
            store.save_init_session_media(session.session_id, [path])
            store.save_init_faces([InitFace(
                init_face_id=f"guard-face-{index}", session_id=session.session_id,
                group_id=f"guard-group-{index}", source_image=path,
                face=DetectedFace(FaceBox(index * 10, 1, 10, 10, 0.9), 0.9),
                vector=(1.0 - index * 0.2, index * 0.2),
                quality=QualityReport(QualityStatus.GOOD, 0.9),
            ) for index in range(3)])
            review_id = store.plan_init_session_encounters(session.session_id, [[
                store.list_init_session_media(session.session_id)[0]["media_id"],
            ]])[0]["review_id"]
            store.save_encounter_review_event(review_id, {"date": "2026-09-28", "time_precision": "unknown"})
            for index, person in enumerate(people):
                store.set_photo_review_face_decision(
                    review_id, f"guard-face-{index}", "ACCEPT_EXISTING_PERSON",
                    person_id=person.person_id,
                )
            with self.assertRaisesRegex(ValueError, "active Encounter draft"):
                store.archive_person(people[0].person_id, "guard-archive-op")
            with self.assertRaisesRegex(ValueError, "active Encounter draft"):
                store.permanently_delete_person(people[0].person_id, "guard-delete-op")
            with self.assertRaisesRegex(ValueError, "active Encounter draft"):
                store.preview_identity_merge(people[2].person_id, people[1].person_id)
            self.assertIsNone(store.get_operation("guard-archive-op"))
            self.assertIsNone(store.get_operation("guard-delete-op"))
            ready = store.complete_encounter_identity_review(review_id)
            for pair in ready["relation_candidates"]:
                names = {pair["first_name"], pair["second_name"]}
                disposition = "EXCLUDE" if names == {"A", "C"} else "INCLUDE"
                store.set_encounter_relation_decision(
                    review_id, pair["first_ref"], pair["second_ref"], disposition,
                )
            store.complete_photo_review(review_id, "guard-complete-op")
            with self.assertRaisesRegex(ValueError, "collapse distinct Encounter Relation decisions"):
                store.preview_identity_merge(people[2].person_id, people[1].person_id)

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

    def test_encounter_graph_failure_preserves_draft_for_retry(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            session = store.create_init_session("/managed/rollback")
            path = "/managed/rollback.jpg"
            store.save_init_session_media(session.session_id, [path])
            store.save_init_faces([InitFace(
                init_face_id=f"rollback-face-{index}", session_id=session.session_id,
                group_id=f"rollback-group-{index}", source_image=path,
                face=DetectedFace(FaceBox(index * 12, 1, 10, 10, 0.9), 0.9),
                vector=(1.0 - index * 0.2, index * 0.2),
                quality=QualityReport(QualityStatus.GOOD, 0.9),
            ) for index in range(2)])
            media_id = store.list_init_session_media(session.session_id)[0]["media_id"]
            review_id = store.plan_init_session_encounters(session.session_id, [[media_id]])[0]["review_id"]
            store.save_encounter_review_event(review_id, {
                "date": "2026-09-28", "time_precision": "unknown",
            })
            for index in range(2):
                store.set_photo_review_face_decision(
                    review_id, f"rollback-face-{index}", "ACCEPT_NEW_PERSON",
                    new_person_key=f"rollback-person-{index}", new_person_name=f"Person {index}",
                )
            candidate = store.complete_encounter_identity_review(review_id)["relation_candidates"][0]
            store.set_encounter_relation_decision(
                review_id, candidate["first_ref"], candidate["second_ref"], "INCLUDE",
            )
            with patch(
                "sentriface.storage.sqlite_store._replace_graph_projection",
                side_effect=RuntimeError("forced encounter graph failure"),
            ):
                with self.assertRaisesRegex(RuntimeError, "forced encounter graph failure"):
                    store.complete_photo_review(review_id, "encounter-rollback-op")
            self.assertIsNone(store.get_operation("encounter-rollback-op"))
            draft = store.list_init_session_encounter_reviews(session.session_id)[0]
            self.assertEqual(draft["status"], "IN_PROGRESS")
            self.assertEqual(draft["phase"], "RELATIONS")
            self.assertEqual(draft["relations"][0]["disposition"], "INCLUDE")
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
