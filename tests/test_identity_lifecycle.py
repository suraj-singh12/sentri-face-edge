from __future__ import annotations

import json
import sqlite3
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sentriface.storage.sqlite_store import (
    SCHEMA_VERSION,
    SQLiteIdentityStore,
    SchemaMigrationError,
    _schema_migrations,
)


class IdentityLifecycleTest(unittest.TestCase):
    def _store(self, root: Path) -> SQLiteIdentityStore:
        store = SQLiteIdentityStore(root / "sentriface.db", embedding_dim=2)
        store.initialize()
        return store

    def _create_v17_people(self, db_path: Path, people: list[dict]) -> None:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("BEGIN")
            for migration in _schema_migrations():
                if migration.to_version > 17:
                    break
                migration.apply(conn)
            for person in people:
                conn.execute(
                    """
                    INSERT INTO persons(
                        person_id, name, metadata, created_at, deleted_at,
                        enrollment_status, notes
                    ) VALUES (?, ?, ?, ?, ?, 'enrolled', '')
                    """,
                    (
                        person["person_id"],
                        person["person_id"],
                        json.dumps(person.get("metadata", {}), separators=(",", ":")),
                        "2026-08-08T00:00:00+00:00",
                        person.get("deleted_at"),
                    ),
                )
            conn.commit()

    def _assert_invalid_v17_mapping_rolls_back(
        self, people: list[dict], message: str,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "sentriface.db"
            self._create_v17_people(db_path, people)

            with self.assertRaisesRegex(SchemaMigrationError, message):
                SQLiteIdentityStore(db_path, embedding_dim=2).initialize()

            with sqlite3.connect(db_path) as conn:
                self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 17)
                columns = {
                    row[1] for row in conn.execute("PRAGMA table_info(persons)")
                }
            self.assertNotIn("canonical_person_id", columns)

    def test_v17_migration_rejects_self_canonical_mapping(self) -> None:
        self._assert_invalid_v17_mapping_rolls_back(
            [{
                "person_id": "person-a",
                "metadata": {"merged_into": "person-a"},
                "deleted_at": "2026-08-08T01:00:00+00:00",
            }],
            "self-reference",
        )

    def test_v17_migration_rejects_canonical_cycle(self) -> None:
        self._assert_invalid_v17_mapping_rolls_back(
            [
                {
                    "person_id": "person-a",
                    "metadata": {"merged_into": "person-b"},
                    "deleted_at": "2026-08-08T01:00:00+00:00",
                },
                {
                    "person_id": "person-b",
                    "metadata": {"merged_into": "person-a"},
                    "deleted_at": "2026-08-08T01:00:00+00:00",
                },
            ],
            "cycle detected",
        )

    def test_v17_migration_rejects_dangling_canonical_target(self) -> None:
        self._assert_invalid_v17_mapping_rolls_back(
            [{
                "person_id": "person-a",
                "metadata": {"merged_into": "missing-person"},
                "deleted_at": "2026-08-08T01:00:00+00:00",
            }],
            "target missing-person does not exist",
        )

    def test_v17_existing_enrolled_person_migrates_active_without_behavior_change(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "sentriface.db"
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA foreign_keys=ON")
                conn.execute("BEGIN")
                for migration in _schema_migrations():
                    if migration.to_version > 17:
                        break
                    migration.apply(conn)
                conn.execute(
                    """
                    INSERT INTO persons(
                        person_id, name, metadata, created_at, enrollment_status, notes
                    ) VALUES ('existing', 'Existing Person', '{}', ?, 'enrolled', '')
                    """,
                    ("2026-08-08T00:00:00+00:00",),
                )
                conn.execute(
                    """
                    INSERT INTO embeddings(
                        embedding_id, person_id, vector, quality_score, created_at
                    ) VALUES ('face-1', 'existing', ?, 0.9, ?)
                    """,
                    (struct.pack("2f", 1.0, 0.0), "2026-08-08T00:00:00+00:00"),
                )
                conn.commit()

            store = SQLiteIdentityStore(db_path, embedding_dim=2)
            store.initialize()

            person = store.get_person("existing")
            self.assertEqual(person.lifecycle_status, "ACTIVE")
            self.assertEqual(person.identity_status, "IDENTIFIED")
            self.assertEqual(person.biometric_status, "ENROLLED")
            self.assertEqual(person.enrollment_status, "enrolled")
            self.assertEqual(store.resolve_canonical_person_id("existing"), "existing")
            with sqlite3.connect(db_path) as conn:
                self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)

    def test_archive_retains_data_and_restore_returns_active(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            person = store.create_person("Archived Person")
            embedding = store.add_embedding(person.person_id, (1.0, 0.0), 0.9)
            store.add_recognition_detail(
                embedding.embedding_id,
                person.person_id,
                "image-1",
                person.name,
                "accepted",
                "2026-08-08",
                "12:00",
                "Lobby",
                1,
                "Arrival",
            )

            archived = store.archive_person(
                person.person_id,
                "archive-1",
                actor={"user_id": "operator-1", "username": "operator", "roles": ["operator"]},
            )

            self.assertEqual(archived["lifecycle_status"], "ARCHIVED")
            self.assertIsNone(store.get_person(person.person_id))
            historical = store.get_person(person.person_id, include_archived=True)
            self.assertEqual(historical.lifecycle_status, "ARCHIVED")
            self.assertEqual(len(store.list_embeddings_for_person(person.person_id, include_archived=True)), 1)
            self.assertEqual(len(store.list_recognition_details_for_person(person.person_id)), 1)
            self.assertEqual(store.get_operation("archive-1")["status"], "COMMITTED")
            self.assertEqual(store.get_operation("archive-1")["operation_type"], "identity.archive")

            restored = store.restore_person(person.person_id, "restore-1")

            self.assertEqual(restored["lifecycle_status"], "ACTIVE")
            self.assertEqual(store.get_person(person.person_id).lifecycle_status, "ACTIVE")
            self.assertEqual(store.get_operation("restore-1")["status"], "COMMITTED")

    def test_soft_delete_tombstones_and_retains_all_historical_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            person = store.create_person("Deleted Person")
            embedding = store.add_embedding(person.person_id, (1.0, 0.0), 0.9)
            store.add_recognition_detail(
                embedding.embedding_id,
                person.person_id,
                "image-1",
                person.name,
                "accepted",
                "2026-08-08",
                "12:00",
                "Lobby",
                1,
                "Arrival",
            )
            store.update_person_profile(
                person.person_id,
                "Deleted Person",
                "Visitor",
                "India",
                "Regular",
                "Operator",
            )

            deleted = store.soft_delete_person(person.person_id, "delete-1")

            self.assertTrue(deleted["tombstoned"])
            self.assertFalse(deleted["permanent"])
            self.assertEqual(deleted["retained_embeddings"], 1)
            self.assertEqual(deleted["retained_sightings"], 1)
            self.assertGreaterEqual(deleted["retained_profile_changes"], 1)
            self.assertIsNone(store.get_person(person.person_id))
            historical = store.get_person(person.person_id, include_archived=True)
            self.assertEqual(historical.lifecycle_status, "DELETED")
            self.assertEqual(store.resolve_canonical_person_id(person.person_id), person.person_id)
            self.assertEqual(len(store.list_embeddings_for_person(person.person_id, include_archived=True)), 1)
            self.assertEqual(len(store.list_recognition_details_for_person(person.person_id)), 1)
            self.assertEqual(store.get_operation("delete-1")["status"], "COMMITTED")
            with self.assertRaisesRegex(KeyError, "Only archived"):
                store.restore_person(person.person_id, "restore-deleted-1")

    def test_legacy_permanent_delete_entry_point_now_tombstones(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            person = store.create_person("Retained Identity")
            store.add_embedding(person.person_id, (1.0, 0.0), 0.9)

            result = store.permanently_delete_person(person.person_id, "legacy-delete-1")

            self.assertTrue(result["tombstoned"])
            self.assertFalse(result["permanent"])
            self.assertIsNotNone(store.get_person(person.person_id, include_archived=True))
            self.assertEqual(len(store.list_embeddings_for_person(person.person_id, include_archived=True)), 1)

    def test_active_and_historical_queries_separate_lifecycle_states(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            active = store.create_person("Active")
            archived = store.create_person("Archived")
            deleted = store.create_person("Deleted")
            merged = store.create_person("Merged")
            target = store.create_person("Target")
            store.archive_person(archived.person_id, "archive-query")
            store.soft_delete_person(deleted.person_id, "delete-query")
            store.set_canonical_person_id(merged.person_id, target.person_id, "map-query")

            active_ids = {item.person.person_id for item in store.list_persons()}
            historical_ids = {item.person.person_id for item in store.list_historical_persons()}

            self.assertEqual(active_ids, {active.person_id, target.person_id})
            self.assertEqual(historical_ids, {archived.person_id, deleted.person_id, merged.person_id})
            for person_id in historical_ids:
                self.assertIsNone(store.get_person(person_id))
                self.assertIsNotNone(store.get_person(person_id, include_archived=True))

    def test_canonical_mapping_and_chained_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            first = store.create_person("First")
            second = store.create_person("Second")
            survivor = store.create_person("Survivor")

            self.assertEqual(store.resolve_canonical_person_id(survivor.person_id), survivor.person_id)
            store.set_canonical_person_id(first.person_id, second.person_id, "map-1")
            store.set_canonical_person_id(second.person_id, survivor.person_id, "map-2")

            self.assertEqual(store.resolve_canonical_person_id(first.person_id), survivor.person_id)
            self.assertEqual(store.resolve_canonical_person_id(second.person_id), survivor.person_id)
            lifecycle = store.get_person_lifecycle(first.person_id)
            self.assertEqual(lifecycle["canonical_person_id"], second.person_id)
            self.assertEqual(lifecycle["resolved_canonical_person_id"], survivor.person_id)
            self.assertEqual(store.get_operation("map-1")["operation_type"], "identity.canonical-map")

    def test_invalid_canonical_mappings_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            first = store.create_person("First")
            second = store.create_person("Second")

            with self.assertRaisesRegex(ValueError, "itself"):
                store.set_canonical_person_id(first.person_id, first.person_id, "self-map")
            with self.assertRaisesRegex(KeyError, "Unknown person"):
                store.set_canonical_person_id(first.person_id, "missing", "dangling-map")

            store.set_canonical_person_id(first.person_id, second.person_id, "map-first")
            with self.assertRaisesRegex(ValueError, "cycle"):
                store.set_canonical_person_id(second.person_id, first.person_id, "cycle-map")

            self.assertIsNone(store.get_operation("self-map"))
            self.assertIsNone(store.get_operation("dangling-map"))
            self.assertIsNone(store.get_operation("cycle-map"))

    def test_identified_no_face_person_is_valid_but_empty_unidentified_is_not(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))

            person = store.create_person("Context Only Person")

            self.assertEqual(person.identity_status, "IDENTIFIED")
            self.assertEqual(person.biometric_status, "NO_FACE")
            self.assertEqual(store.list_embeddings_for_person(person.person_id), [])
            with self.assertRaisesRegex(ValueError, "meaningful identity"):
                store.create_person("", {}, "")
            with self.assertRaisesRegex(ValueError, "meaningful identity"):
                store.create_person("", {}, "", identity_status="UNIDENTIFIED")

    def test_failed_lifecycle_transaction_rolls_back_person_and_journal(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = self._store(Path(temp))
            person = store.create_person("Rollback Person")

            with patch(
                "sentriface.storage.sqlite_store._transition_journal_operation",
                side_effect=RuntimeError("simulated journal failure"),
            ):
                with self.assertRaisesRegex(RuntimeError, "simulated journal failure"):
                    store.archive_person(person.person_id, "archive-rollback")

            self.assertEqual(store.get_person(person.person_id).lifecycle_status, "ACTIVE")
            self.assertIsNone(store.get_operation("archive-rollback"))
            self.assertIsNone(store.get_person_operation("archive-rollback", "archive-person"))


if __name__ == "__main__":
    unittest.main()
