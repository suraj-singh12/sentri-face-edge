from __future__ import annotations

import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sentriface.backup_service import BackupError, BackupService
from sentriface.storage.sqlite_store import (
    SCHEMA_VERSION,
    SQLiteIdentityStore,
    SchemaMigrationError,
    _schema_migrations,
)


class StorageMigrationTest(unittest.TestCase):
    def test_migration_registry_is_contiguous_through_current_schema(self) -> None:
        migrations = _schema_migrations()

        self.assertEqual(migrations[0].from_version, 0)
        self.assertEqual(migrations[-1].to_version, SCHEMA_VERSION)
        self.assertEqual(
            [(item.from_version, item.to_version) for item in migrations],
            [(version, version + 1) for version in range(SCHEMA_VERSION)],
        )

    def test_v13_migration_adds_person_associations_without_changing_people(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "sentriface.db"
            with closing(sqlite3.connect(db_path)) as conn, conn:
                conn.executescript(
                    """
                    CREATE TABLE persons (
                        person_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        metadata TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL,
                        deleted_at TEXT,
                        enrollment_status TEXT NOT NULL DEFAULT 'enrolled'
                    );
                    INSERT INTO persons(
                        person_id, name, metadata, created_at, enrollment_status
                    ) VALUES (
                        'existing', 'Existing Person', '{}',
                        '2026-08-01T00:00:00+00:00', 'enrolled'
                    );
                    PRAGMA user_version = 13;
                    """
                )

            store = SQLiteIdentityStore(db_path)
            store.initialize()

            self.assertEqual(store.get_person("existing").name, "Existing Person")
            with closing(sqlite3.connect(db_path)) as conn:
                table = conn.execute(
                    """
                    SELECT name FROM sqlite_master
                    WHERE type = 'table' AND name = 'person_associations'
                    """
                ).fetchone()
                foreign_keys = conn.execute(
                    "PRAGMA foreign_key_list(person_associations)"
                ).fetchall()
            self.assertEqual(table[0], "person_associations")
            self.assertEqual({row[6] for row in foreign_keys}, {"RESTRICT"})

    def test_v12_migration_preserves_existing_people_as_enrolled(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "sentriface.db"
            with closing(sqlite3.connect(db_path)) as conn, conn:
                conn.executescript(
                    """
                    CREATE TABLE persons (
                        person_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        metadata TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL,
                        deleted_at TEXT
                    );
                    CREATE TABLE person_change_history (
                        change_id TEXT PRIMARY KEY,
                        person_id TEXT NOT NULL,
                        previous_name TEXT NOT NULL,
                        new_name TEXT NOT NULL,
                        previous_rank TEXT,
                        new_rank TEXT,
                        previous_country TEXT,
                        new_country TEXT,
                        previous_importance TEXT,
                        new_importance TEXT,
                        editor_name TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    INSERT INTO persons(person_id, name, metadata, created_at)
                    VALUES ('existing', 'Existing Person', '{}', '2026-08-01T00:00:00+00:00');
                    PRAGMA user_version = 12;
                    """
                )

            store = SQLiteIdentityStore(db_path)
            store.initialize()

            person = store.get_person("existing")
            self.assertEqual(person.enrollment_status, "enrolled")
            with closing(sqlite3.connect(db_path)) as conn:
                history_columns = {
                    row[1] for row in conn.execute("PRAGMA table_info(person_change_history)")
                }
            self.assertIn("previous_status", history_columns)
            self.assertIn("new_status", history_columns)

    def test_initialize_sets_schema_version(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "sentriface.db"
            store = SQLiteIdentityStore(db_path)

            store.initialize()

            with closing(sqlite3.connect(db_path)) as conn, conn:
                version = conn.execute("PRAGMA user_version").fetchone()[0]

            self.assertEqual(version, SCHEMA_VERSION)

    def test_current_database_repeated_startup_is_a_no_op(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "sentriface.db"
            store = SQLiteIdentityStore(db_path)
            store.initialize()
            person = store.create_person("Current Schema Person")

            with closing(sqlite3.connect(db_path)) as conn, conn:
                before_schema = conn.execute(
                    "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name"
                ).fetchall()
                before_person = conn.execute(
                    "SELECT person_id, name, metadata, created_at, deleted_at, enrollment_status, notes "
                    "FROM persons WHERE person_id = ?",
                    (person.person_id,),
                ).fetchone()

            with patch.object(store, "_create_pre_migration_backup") as create_backup, patch(
                "sentriface.storage.sqlite_store._migrate_15_to_16",
                side_effect=AssertionError("current schema must not run migrations"),
            ):
                store.initialize()
                store.initialize()

            with closing(sqlite3.connect(db_path)) as conn, conn:
                after_schema = conn.execute(
                    "SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name"
                ).fetchall()
                after_person = conn.execute(
                    "SELECT person_id, name, metadata, created_at, deleted_at, enrollment_status, notes "
                    "FROM persons WHERE person_id = ?",
                    (person.person_id,),
                ).fetchone()
                version = conn.execute("PRAGMA user_version").fetchone()[0]

            create_backup.assert_not_called()
            self.assertEqual(version, SCHEMA_VERSION)
            self.assertEqual(after_schema, before_schema)
            self.assertEqual(after_person, before_person)
            self.assertEqual(BackupService(db_path, root / "backups").list_backups(), [])

    def test_newer_schema_version_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "sentriface.db"
            with closing(sqlite3.connect(db_path)) as conn, conn:
                conn.execute("PRAGMA user_version = 999")

            store = SQLiteIdentityStore(db_path)

            with self.assertRaises(RuntimeError):
                store.initialize()

    def test_v8_database_adds_idempotent_people_operations(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "sentriface.db"
            with closing(sqlite3.connect(db_path)) as conn, conn:
                conn.execute("PRAGMA user_version = 8")

            store = SQLiteIdentityStore(db_path)
            store.initialize()

            with closing(sqlite3.connect(db_path)) as conn, conn:
                version = conn.execute("PRAGMA user_version").fetchone()[0]
                table = conn.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'table' AND name = 'person_operations'
                    """
                ).fetchone()

            self.assertEqual(version, SCHEMA_VERSION)
            self.assertEqual(table[0], "person_operations")
            backups = BackupService(db_path, root / "backups").list_backups()
            self.assertEqual(len(backups), 1)
            self.assertTrue(backups[0].verified)
            self.assertEqual(backups[0].database_version, 8)
            self.assertEqual(backups[0].reason, f"before-schema-migration-v8-to-v{SCHEMA_VERSION}")
            self.assertEqual(backups[0].operation_id, f"schema-migration-v8-to-v{SCHEMA_VERSION}")
            backup_path = (
                root / "backups" / backups[0].backup_id / db_path.name
            )
            with closing(sqlite3.connect(backup_path)) as conn, conn:
                self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 8)

            store.initialize()
            self.assertEqual(
                len(BackupService(db_path, root / "backups").list_backups()),
                1,
            )

    def test_pre_migration_backup_failure_prevents_schema_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "sentriface.db"
            with closing(sqlite3.connect(db_path)) as conn, conn:
                conn.execute("PRAGMA user_version = 9")

            with patch(
                "sentriface.storage.sqlite_store.BackupService.create_backup",
                side_effect=BackupError("simulated backup failure"),
            ):
                with self.assertRaisesRegex(BackupError, "simulated backup failure"):
                    SQLiteIdentityStore(db_path).initialize()

            with closing(sqlite3.connect(db_path)) as conn, conn:
                self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 9)

    def test_failed_migration_reuses_and_reverifies_pre_migration_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "sentriface.db"
            with closing(sqlite3.connect(db_path)) as conn, conn:
                conn.execute("PRAGMA user_version = 9")
            store = SQLiteIdentityStore(db_path)

            with patch(
                "sentriface.storage.sqlite_store._migrate_9_to_10",
                side_effect=RuntimeError("simulated migration failure"),
            ):
                with self.assertRaisesRegex(RuntimeError, "simulated migration failure"):
                    store.initialize()

            backups = BackupService(db_path, root / "backups").list_backups()
            self.assertEqual(len(backups), 1)
            with closing(sqlite3.connect(db_path)) as conn, conn:
                self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 9)

            with patch(
                "sentriface.storage.sqlite_store.BackupService.verify_backup",
                return_value=False,
            ):
                with self.assertRaisesRegex(BackupError, "failed verification"):
                    store.initialize()
            with closing(sqlite3.connect(db_path)) as conn, conn:
                self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 9)

            store.initialize()
            with closing(sqlite3.connect(db_path)) as conn, conn:
                self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
            self.assertEqual(
                len(BackupService(db_path, root / "backups").list_backups()),
                1,
            )

    def test_failure_after_partial_migration_rolls_back_version_schema_and_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "sentriface.db"
            with closing(sqlite3.connect(db_path)) as conn, conn:
                conn.executescript(
                    """
                    CREATE TABLE persons (
                        person_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        metadata TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL,
                        deleted_at TEXT
                    );
                    CREATE TABLE embeddings (
                        embedding_id TEXT PRIMARY KEY,
                        person_id TEXT NOT NULL,
                        vector BLOB NOT NULL,
                        quality_score REAL NOT NULL,
                        source_image TEXT,
                        crop_path TEXT,
                        created_at TEXT NOT NULL
                    );
                    CREATE TABLE person_operations (
                        operation_id TEXT PRIMARY KEY,
                        operation_type TEXT NOT NULL,
                        result TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    INSERT INTO persons(person_id, name, metadata, created_at)
                    VALUES ('person-1', 'Recoverable Person', '{}', '2026-08-08T00:00:00+00:00');
                    INSERT INTO embeddings(
                        embedding_id, person_id, vector, quality_score, created_at
                    ) VALUES (
                        'embedding-1', 'person-1', X'00000000', 0.9,
                        '2026-08-08T00:00:00+00:00'
                    );
                    PRAGMA user_version = 9;
                    """
                )

            with patch(
                "sentriface.storage.sqlite_store._migrate_10_to_11",
                side_effect=RuntimeError("simulated second-step failure"),
            ):
                with self.assertRaisesRegex(
                    SchemaMigrationError,
                    "migration v10 to v11 failed.*simulated second-step failure",
                ):
                    SQLiteIdentityStore(db_path, embedding_dim=1).initialize()

            with closing(sqlite3.connect(db_path)) as conn, conn:
                version = conn.execute("PRAGMA user_version").fetchone()[0]
                embedding_columns = {
                    row[1] for row in conn.execute("PRAGMA table_info(embeddings)")
                }
                person = conn.execute(
                    "SELECT person_id, name FROM persons WHERE person_id = 'person-1'"
                ).fetchone()
                embedding = conn.execute(
                    "SELECT embedding_id, person_id FROM embeddings WHERE embedding_id = 'embedding-1'"
                ).fetchone()
                integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]

            self.assertEqual(version, 9)
            self.assertNotIn("purge_after", embedding_columns)
            self.assertNotIn("deleted_at", embedding_columns)
            self.assertEqual(person, ("person-1", "Recoverable Person"))
            self.assertEqual(embedding, ("embedding-1", "person-1"))
            self.assertEqual(integrity, "ok")
            backups = BackupService(db_path, root / "backups").list_backups()
            self.assertEqual(len(backups), 1)
            self.assertTrue(backups[0].verified)
            self.assertEqual(backups[0].database_version, 9)

    def test_v9_database_adds_deleted_face_retention_columns_without_deleting_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "sentriface.db"
            with closing(sqlite3.connect(db_path)) as conn, conn:
                conn.executescript(
                    """
                    CREATE TABLE persons (
                        person_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        metadata TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL,
                        deleted_at TEXT
                    );
                    CREATE TABLE embeddings (
                        embedding_id TEXT PRIMARY KEY,
                        person_id TEXT NOT NULL,
                        vector BLOB NOT NULL,
                        quality_score REAL NOT NULL,
                        source_image TEXT,
                        crop_path TEXT,
                        created_at TEXT NOT NULL
                    );
                    CREATE TABLE person_operations (
                        operation_id TEXT PRIMARY KEY,
                        operation_type TEXT NOT NULL,
                        result TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    INSERT INTO persons(person_id, name, metadata, created_at)
                    VALUES ('person-1', 'Retained Person', '{}', '2026-07-26T00:00:00+00:00');
                    INSERT INTO embeddings(
                        embedding_id, person_id, vector, quality_score, created_at
                    )
                    VALUES ('embedding-1', 'person-1', X'00000000', 0.9, '2026-07-26T00:00:00+00:00');
                    PRAGMA user_version = 9;
                    """
                )

            store = SQLiteIdentityStore(db_path, embedding_dim=1)
            store.initialize()

            with closing(sqlite3.connect(db_path)) as conn, conn:
                columns = {
                    row[1]
                    for row in conn.execute("PRAGMA table_info(embeddings)").fetchall()
                }
                version = conn.execute("PRAGMA user_version").fetchone()[0]
                count = conn.execute(
                    "SELECT COUNT(*) FROM embeddings WHERE embedding_id = ?",
                    ("embedding-1",),
                ).fetchone()[0]
            self.assertEqual(version, SCHEMA_VERSION)
            self.assertIn("deleted_at", columns)
            self.assertIn("purge_after", columns)
            self.assertEqual(count, 1)

    def test_backup_to_copies_database_contents(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            db_path = temp_path / "sentriface.db"
            backup_path = temp_path / "backups" / "sentriface-copy.db"
            store = SQLiteIdentityStore(db_path, embedding_dim=4)
            store.initialize()
            person = store.create_person("Backup Person")
            store.add_embedding(person.person_id, [0.1, 0.2, 0.3, 0.4], quality_score=0.9)

            store.backup_to(backup_path)

            with closing(sqlite3.connect(backup_path)) as conn, conn:
                persons = conn.execute("SELECT COUNT(*) FROM persons").fetchone()[0]
                embeddings = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]

            self.assertEqual(persons, 1)
            self.assertEqual(embeddings, 1)

    def test_recognition_details_are_saved_for_embedding(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "sentriface.db"
            store = SQLiteIdentityStore(db_path, embedding_dim=4)
            store.initialize()
            person = store.create_person("Seen Person")
            embedding = store.add_embedding(
                person.person_id,
                [0.1, 0.2, 0.3, 0.4],
                quality_score=0.9,
                source_image="uploads/image-a.jpg",
            )

            detail = store.add_recognition_detail(
                embedding_id=embedding.embedding_id,
                person_id=person.person_id,
                image_id="image-a.jpg",
                image_path="uploads/image-a.jpg",
                name=person.name,
                decision="new",
                seen_date="2026-06-07",
                seen_time="13:45",
                place_seen="Gate 1",
                individual_count=2,
                event_occasion="Briefing",
                rank="Maj",
                country="India",
                importance="Important",
                added_by="Analyst A",
            )

            details = store.list_recognition_details_for_embedding(embedding.embedding_id)

            self.assertEqual(len(details), 1)
            self.assertEqual(details[0].detail_id, detail.detail_id)
            self.assertEqual(details[0].embedding_id, embedding.embedding_id)
            self.assertEqual(details[0].image_id, "image-a.jpg")
            self.assertEqual(details[0].name, "Seen Person")
            self.assertEqual(details[0].individual_count, 2)
            self.assertEqual(details[0].rank, "Maj")
            self.assertEqual(details[0].country, "India")
            self.assertEqual(details[0].importance, "Important")
            self.assertEqual(details[0].added_by, "Analyst A")
            self.assertEqual(store.get_person(person.person_id).metadata["added_by"], "Analyst A")
            summary = store.list_persons()[0]
            self.assertEqual(summary.sighting_count, 1)
            self.assertEqual(summary.last_seen_at, "2026-06-07T13:45")

    def test_person_profile_update_keeps_change_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "sentriface.db"
            store = SQLiteIdentityStore(db_path, embedding_dim=4)
            store.initialize()
            person = store.create_person(
                "Original Name",
                metadata={"rank": "abc", "country": "India", "importance": "Regular"},
            )

            change = store.update_person_profile(
                person_id=person.person_id,
                name="Updated Name",
                rank="pqr",
                country="Nepal",
                importance="Important",
                editor_name="Editor One",
                operation_id="profile-update-history",
            )
            updated = store.get_person(person.person_id)
            changes = store.list_person_changes(person.person_id)

            self.assertEqual(updated.name, "Updated Name")
            self.assertEqual(updated.metadata["rank"], "pqr")
            self.assertEqual(updated.metadata["country"], "Nepal")
            self.assertEqual(updated.metadata["importance"], "Important")
            self.assertEqual(len(changes), 1)
            self.assertEqual(changes[0].change_id, change.change_id)
            self.assertEqual(changes[0].previous_rank, "abc")
            self.assertEqual(changes[0].new_rank, "pqr")
            self.assertEqual(changes[0].editor_name, "Editor One")

    def test_v1_database_migrates_to_v2(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "sentriface.db"
            with closing(sqlite3.connect(db_path)) as conn, conn:
                conn.executescript(
                    """
                    CREATE TABLE persons (
                        person_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        metadata TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL
                    );
                    CREATE TABLE pending_additions (
                        pending_id TEXT PRIMARY KEY,
                        source_image TEXT NOT NULL,
                        box_x INTEGER NOT NULL,
                        box_y INTEGER NOT NULL,
                        box_width INTEGER NOT NULL,
                        box_height INTEGER NOT NULL,
                        box_confidence REAL NOT NULL,
                        quality_score REAL NOT NULL,
                        landmarks TEXT,
                        crop_path TEXT,
                        vector BLOB NOT NULL,
                        matches TEXT NOT NULL,
                        decision TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    PRAGMA user_version = 1;
                    """
                )

            SQLiteIdentityStore(db_path).initialize()

            with closing(sqlite3.connect(db_path)) as conn, conn:
                version = conn.execute("PRAGMA user_version").fetchone()[0]
                columns = {
                    row[1]
                    for row in conn.execute("PRAGMA table_info(pending_additions)").fetchall()
                }

            self.assertEqual(version, SCHEMA_VERSION)
            self.assertIn("quality_status", columns)
            self.assertIn("pending_quality_score", columns)
            self.assertIn("quality_reasons", columns)

    def test_v3_database_migrates_to_v4(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "sentriface.db"
            with closing(sqlite3.connect(db_path)) as conn, conn:
                conn.executescript(
                    """
                    CREATE TABLE persons (
                        person_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        metadata TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL
                    );
                    PRAGMA user_version = 3;
                    """
                )

            SQLiteIdentityStore(db_path).initialize()

            with closing(sqlite3.connect(db_path)) as conn, conn:
                version = conn.execute("PRAGMA user_version").fetchone()[0]
                columns = {
                    row[1]
                    for row in conn.execute("PRAGMA table_info(persons)").fetchall()
                }

            self.assertEqual(version, SCHEMA_VERSION)
            self.assertIn("deleted_at", columns)

    def test_v4_database_migrates_to_v5(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "sentriface.db"
            with closing(sqlite3.connect(db_path)) as conn, conn:
                conn.executescript(
                    """
                    CREATE TABLE persons (
                        person_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        metadata TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL,
                        deleted_at TEXT
                    );
                    CREATE TABLE embeddings (
                        embedding_id TEXT PRIMARY KEY,
                        person_id TEXT NOT NULL,
                        vector BLOB NOT NULL,
                        quality_score REAL NOT NULL,
                        source_image TEXT,
                        crop_path TEXT,
                        created_at TEXT NOT NULL
                    );
                    PRAGMA user_version = 4;
                    """
                )

            SQLiteIdentityStore(db_path).initialize()

            with closing(sqlite3.connect(db_path)) as conn, conn:
                version = conn.execute("PRAGMA user_version").fetchone()[0]
                tables = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }

            self.assertEqual(version, SCHEMA_VERSION)
            self.assertIn("recognition_details", tables)

    def test_v5_database_migrates_to_v6(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "sentriface.db"
            with closing(sqlite3.connect(db_path)) as conn, conn:
                conn.executescript(
                    """
                    CREATE TABLE persons (
                        person_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        metadata TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL,
                        deleted_at TEXT
                    );
                    CREATE TABLE embeddings (
                        embedding_id TEXT PRIMARY KEY,
                        person_id TEXT NOT NULL,
                        vector BLOB NOT NULL,
                        quality_score REAL NOT NULL,
                        source_image TEXT,
                        crop_path TEXT,
                        created_at TEXT NOT NULL
                    );
                    CREATE TABLE recognition_details (
                        detail_id TEXT PRIMARY KEY,
                        embedding_id TEXT NOT NULL,
                        person_id TEXT NOT NULL,
                        image_id TEXT NOT NULL,
                        image_path TEXT,
                        name TEXT NOT NULL,
                        decision TEXT NOT NULL,
                        seen_date TEXT NOT NULL,
                        seen_time TEXT NOT NULL,
                        place_seen TEXT NOT NULL,
                        individual_count INTEGER NOT NULL,
                        event_occasion TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    PRAGMA user_version = 5;
                    """
                )

            SQLiteIdentityStore(db_path).initialize()

            with closing(sqlite3.connect(db_path)) as conn, conn:
                version = conn.execute("PRAGMA user_version").fetchone()[0]
                columns = {
                    row[1]
                    for row in conn.execute("PRAGMA table_info(recognition_details)").fetchall()
                }

            self.assertEqual(version, SCHEMA_VERSION)
            self.assertIn("rank", columns)
            self.assertIn("country", columns)
            self.assertIn("importance", columns)
            self.assertIn("added_by", columns)

    def test_v6_database_migrates_to_v7(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "sentriface.db"
            with closing(sqlite3.connect(db_path)) as conn, conn:
                conn.executescript(
                    """
                    CREATE TABLE persons (
                        person_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        metadata TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL,
                        deleted_at TEXT
                    );
                    CREATE TABLE embeddings (
                        embedding_id TEXT PRIMARY KEY,
                        person_id TEXT NOT NULL,
                        vector BLOB NOT NULL,
                        quality_score REAL NOT NULL,
                        source_image TEXT,
                        crop_path TEXT,
                        created_at TEXT NOT NULL
                    );
                    CREATE TABLE recognition_details (
                        detail_id TEXT PRIMARY KEY,
                        embedding_id TEXT NOT NULL,
                        person_id TEXT NOT NULL,
                        image_id TEXT NOT NULL,
                        image_path TEXT,
                        name TEXT NOT NULL,
                        decision TEXT NOT NULL,
                        seen_date TEXT NOT NULL,
                        seen_time TEXT NOT NULL,
                        place_seen TEXT NOT NULL,
                        individual_count INTEGER NOT NULL,
                        event_occasion TEXT NOT NULL,
                        rank TEXT,
                        country TEXT,
                        importance TEXT,
                        added_by TEXT,
                        created_at TEXT NOT NULL
                    );
                    PRAGMA user_version = 6;
                    """
                )

            SQLiteIdentityStore(db_path).initialize()

            with closing(sqlite3.connect(db_path)) as conn, conn:
                version = conn.execute("PRAGMA user_version").fetchone()[0]
                tables = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }

            self.assertEqual(version, SCHEMA_VERSION)
            self.assertIn("person_change_history", tables)


if __name__ == "__main__":
    unittest.main()
