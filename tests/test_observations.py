from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sentriface.engine import FaceEngine
from sentriface.storage.sqlite_store import (
    SCHEMA_VERSION,
    SQLiteIdentityStore,
    _schema_migrations,
)


class ObservationStorageTest(unittest.TestCase):
    def _store(self, root: Path) -> SQLiteIdentityStore:
        store = SQLiteIdentityStore(root / "sentriface.db", embedding_dim=2)
        store.initialize()
        return store

    def _legacy_media(
        self, store: SQLiteIdentityStore, person_id: str, media_id: str,
    ) -> str:
        embedding = store.add_embedding(
            person_id,
            (1.0, 0.0),
            0.9,
            source_image=f"/managed/{media_id}",
        )
        store.add_recognition_detail(
            embedding.embedding_id,
            person_id,
            media_id,
            "Observed Person",
            "accepted",
            "2026-08-08",
            "12:00",
            "Lobby",
            1,
            "Arrival",
            image_path=f"/managed/{media_id}",
        )
        return f"/managed/{media_id}"

    def test_domain_finalization_is_gated_until_atomic_p6_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            engine = object.__new__(FaceEngine)
            engine.store = store
            person = store.create_person("Review Person")
            observation = store.create_observation(
                "gated-finalize-create", participant_ids=[person.person_id],
            )

            with self.assertRaisesRegex(
                RuntimeError, "only available through complete_photo_review",
            ):
                engine.finalize_observation(
                    observation.observation_id, "gated-finalize",
                )

            self.assertEqual(
                store.get_observation(observation.observation_id).status,
                "DRAFT",
            )
            self.assertIsNone(store.get_operation("gated-finalize"))
            with sqlite3.connect(store.db_path) as conn:
                self.assertEqual(
                    conn.execute("SELECT COUNT(*) FROM relationship_evidence").fetchone()[0],
                    0,
                )

    def test_fresh_database_has_v19_observation_schema_and_empty_draft_is_valid(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))

            observation = store.create_observation(
                "observation-create-empty",
                observed_at="2026-08-08T12:00:00+00:00",
                location="Lobby",
                context={"occasion": "Arrival"},
            )
            retried = store.create_observation(
                "observation-create-empty",
                observed_at="2026-08-08T12:00:00+00:00",
                location="Lobby",
                context={"occasion": "Arrival"},
            )

            self.assertEqual(observation.status, "DRAFT")
            self.assertEqual(retried.observation_id, observation.observation_id)
            self.assertEqual(observation.location, "Lobby")
            self.assertEqual(observation.context, {"occasion": "Arrival"})
            self.assertEqual(store.list_observation_participants(observation.observation_id), [])
            with sqlite3.connect(store.db_path) as conn:
                self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
                tables = {
                    row[0] for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
            self.assertTrue({"observations", "observation_media", "observation_participants"} <= tables)

    def test_single_and_multi_person_observations_finalize(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            first = store.create_person("First")
            second = store.create_person("Second")
            single = store.create_observation(
                "single-create", participant_ids=[first.person_id],
            )
            multi = store.create_observation(
                "multi-create", participant_ids=[first.person_id, second.person_id],
            )

            self.assertEqual(len(store.list_observation_participants(single.observation_id)), 1)
            self.assertEqual(len(store.list_observation_participants(multi.observation_id)), 2)
            self.assertEqual(
                store._finalize_observation_without_graph_evidence(
                    single.observation_id, "single-finalize",
                ).status,
                "FINALIZED",
            )
            self.assertEqual(
                store._finalize_observation_without_graph_evidence(
                    multi.observation_id, "multi-finalize",
                ).status,
                "FINALIZED",
            )

    def test_multiple_existing_media_memberships_and_lookup(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            person = store.create_person("Media Person")
            first_path = self._legacy_media(store, person.person_id, "first.jpg")
            second_path = self._legacy_media(store, person.person_id, "second.jpg")
            observation = store.create_observation("media-observation")

            first = store.attach_observation_media(
                observation.observation_id,
                "first.jpg",
                "attach-first",
                media_path=first_path,
            )
            store.attach_observation_media(
                observation.observation_id,
                "second.jpg",
                "attach-second",
                media_path=second_path,
            )

            self.assertEqual(first.media_path, first_path)
            self.assertEqual(
                {item.media_id for item in store.list_observation_media(observation.observation_id)},
                {"first.jpg", "second.jpg"},
            )
            self.assertEqual(
                [item.observation_id for item in store.list_observations_for_media("first.jpg")],
                [observation.observation_id],
            )

    def test_duplicate_and_canonical_equivalent_participants_are_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            source = store.create_person("Source")
            survivor = store.create_person("Survivor")
            store._set_canonical_person_id_for_merge(
                source.person_id, survivor.person_id, "canonical-map-observation",
            )
            observation = store.create_observation("canonical-observation")

            original = store.add_observation_participant(
                observation.observation_id, source.person_id, "participant-source",
            )
            retried = store.add_observation_participant(
                observation.observation_id, source.person_id, "participant-source",
            )
            duplicate = store.add_observation_participant(
                observation.observation_id, source.person_id, "participant-source-duplicate",
            )
            canonical_duplicate = store.add_observation_participant(
                observation.observation_id, survivor.person_id, "participant-survivor-duplicate",
            )

            self.assertEqual(original.person_id, source.person_id)
            self.assertEqual(retried.person_id, source.person_id)
            self.assertEqual(original.canonical_person_id, survivor.person_id)
            self.assertEqual(duplicate.person_id, source.person_id)
            self.assertEqual(canonical_duplicate.person_id, source.person_id)
            self.assertEqual(len(store.list_observation_participants(observation.observation_id)), 1)

    def test_invalid_person_is_rejected_without_journal_record(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            observation = store.create_observation("invalid-person-observation")

            with self.assertRaisesRegex(KeyError, "Unknown person"):
                store.add_observation_participant(
                    observation.observation_id, "missing", "invalid-person-add",
                )

            self.assertIsNone(store.get_operation("invalid-person-add"))
            self.assertEqual(store.list_observation_participants(observation.observation_id), [])

    def test_archived_and_deleted_people_remain_historical_participants(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            archived = store.create_person("Archived")
            deleted = store.create_person("Deleted")
            store.archive_person(archived.person_id, "archive-observation-person")
            store.soft_delete_person(deleted.person_id, "delete-observation-person")

            observation = store.create_observation(
                "historical-participants",
                participant_ids=[archived.person_id, deleted.person_id],
            )
            participants = store.list_observation_participants(observation.observation_id)

            self.assertEqual(
                {item.person_lifecycle_status for item in participants},
                {"ARCHIVED", "DELETED"},
            )
            self.assertEqual(
                {item.person_id for item in participants},
                {archived.person_id, deleted.person_id},
            )

    def test_person_lookup_remove_and_finalized_mutation_rules(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            person = store.create_person("Lookup Person")
            observation = store.create_observation(
                "lookup-observation", participant_ids=[person.person_id],
            )

            self.assertEqual(
                [item.observation_id for item in store.list_observations_for_person(person.person_id)],
                [observation.observation_id],
            )
            removed = store.remove_observation_participant(
                observation.observation_id, person.person_id, "remove-participant",
            )
            self.assertTrue(removed["removed"])
            with self.assertRaisesRegex(ValueError, "requires at least one"):
                store._finalize_observation_without_graph_evidence(
                    observation.observation_id, "empty-finalize",
                )
            store.add_observation_participant(
                observation.observation_id, person.person_id, "readd-participant",
            )
            store._finalize_observation_without_graph_evidence(
                observation.observation_id, "finalize-lookup",
            )
            with self.assertRaisesRegex(ValueError, "cannot be changed"):
                store.remove_observation_participant(
                    observation.observation_id, person.person_id, "remove-finalized",
                )

    def test_create_rollback_removes_event_memberships_and_journal(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            person = store.create_person("Rollback Person")
            media_path = self._legacy_media(store, person.person_id, "rollback.jpg")

            with patch(
                "sentriface.storage.sqlite_store._transition_journal_operation",
                side_effect=RuntimeError("simulated final journal failure"),
            ):
                with self.assertRaisesRegex(RuntimeError, "simulated final journal failure"):
                    store.create_observation(
                        "observation-rollback",
                        participant_ids=[person.person_id],
                        media=[{"media_id": "rollback.jpg", "media_path": media_path}],
                    )

            self.assertIsNone(store.get_operation("observation-rollback"))
            with sqlite3.connect(store.db_path) as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0], 0)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM observation_media").fetchone()[0], 0)
                self.assertEqual(
                    conn.execute("SELECT COUNT(*) FROM observation_participants").fetchone()[0],
                    0,
                )

    def test_journal_records_create_add_attach_and_finalize(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            person = store.create_person("Journal Person")
            media_path = self._legacy_media(store, person.person_id, "journal.jpg")
            actor = {"user_id": "operator-1", "username": "operator", "roles": ["operator"]}
            observation = store.create_observation(
                "journal-observation-create",
                actor=actor,
                source="test",
                context={"occasion": "Briefing"},
            )
            updated = store.update_observation(
                observation.observation_id,
                "journal-observation-update",
                location="Room 1",
                actor=actor,
            )
            self.assertEqual(updated.location, "Room 1")
            self.assertEqual(updated.context, {"occasion": "Briefing"})
            store.add_observation_participant(
                observation.observation_id,
                person.person_id,
                "journal-observation-participant",
                actor=actor,
            )
            store.attach_observation_media(
                observation.observation_id,
                "journal.jpg",
                "journal-observation-media",
                media_path=media_path,
                actor=actor,
            )
            store._finalize_observation_without_graph_evidence(
                observation.observation_id, "journal-observation-finalize", actor=actor,
            )

            expected = {
                "journal-observation-create": "observation.create",
                "journal-observation-update": "observation.update",
                "journal-observation-participant": "observation.participant.add",
                "journal-observation-media": "observation.media.attach",
                "journal-observation-finalize": "observation.finalize",
            }
            for operation_id, operation_type in expected.items():
                operation = store.get_operation(operation_id)
                self.assertEqual(operation["operation_type"], operation_type)
                self.assertEqual(operation["status"], "COMMITTED")
                self.assertEqual(operation["actor"]["user_id"], "operator-1")

    def test_v18_migration_preserves_legacy_sighting_and_adds_bridge(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "sentriface.db"
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA foreign_keys=ON")
                conn.execute("BEGIN")
                for migration in _schema_migrations():
                    if migration.to_version > 18:
                        break
                    migration.apply(conn)
                conn.execute(
                    """
                    INSERT INTO persons(
                        person_id, name, metadata, created_at, lifecycle_status,
                        identity_status, biometric_status, lifecycle_changed_at
                    ) VALUES ('legacy-person', 'Legacy', '{}', ?, 'ACTIVE',
                              'IDENTIFIED', 'ENROLLED', ?)
                    """,
                    ("2026-08-08T00:00:00+00:00", "2026-08-08T00:00:00+00:00"),
                )
                conn.execute(
                    """
                    INSERT INTO embeddings(
                        embedding_id, person_id, vector, quality_score, created_at
                    ) VALUES ('legacy-face', 'legacy-person', ?, 0.9, ?)
                    """,
                    (sqlite3.Binary(b"12345678"), "2026-08-08T00:00:00+00:00"),
                )
                conn.execute(
                    """
                    INSERT INTO recognition_details(
                        detail_id, embedding_id, person_id, image_id, name, decision,
                        seen_date, seen_time, place_seen, individual_count,
                        event_occasion, created_at
                    ) VALUES ('legacy-detail', 'legacy-face', 'legacy-person', 'legacy.jpg',
                              'Legacy', 'accepted', '2026-08-08', '12:00', 'Lobby', 1,
                              'Arrival', '2026-08-08T00:00:00+00:00')
                    """
                )
                conn.commit()

            store = SQLiteIdentityStore(db_path, embedding_dim=2)
            store.initialize()

            details = store.list_recognition_details_for_person("legacy-person")
            self.assertEqual(len(details), 1)
            self.assertEqual(details[0].image_id, "legacy.jpg")
            with sqlite3.connect(db_path) as conn:
                columns = {
                    row[1] for row in conn.execute("PRAGMA table_info(recognition_details)")
                }
                bridge = conn.execute(
                    "SELECT observation_id FROM recognition_details WHERE detail_id = 'legacy-detail'"
                ).fetchone()[0]
            self.assertIn("observation_id", columns)
            self.assertIsNone(bridge)


if __name__ == "__main__":
    unittest.main()
