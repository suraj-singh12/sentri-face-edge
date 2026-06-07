from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from sentriface.storage.sqlite_store import SCHEMA_VERSION, SQLiteIdentityStore


class StorageMigrationTest(unittest.TestCase):
    def test_initialize_sets_schema_version(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "sentriface.db"
            store = SQLiteIdentityStore(db_path)

            store.initialize()

            with sqlite3.connect(db_path) as conn:
                version = conn.execute("PRAGMA user_version").fetchone()[0]

            self.assertEqual(version, SCHEMA_VERSION)

    def test_newer_schema_version_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "sentriface.db"
            with sqlite3.connect(db_path) as conn:
                conn.execute("PRAGMA user_version = 999")

            store = SQLiteIdentityStore(db_path)

            with self.assertRaises(RuntimeError):
                store.initialize()

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

            with sqlite3.connect(backup_path) as conn:
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
                decision="duplicate",
                seen_date="2026-06-07",
                seen_time="13:45",
                place_seen="Gate 1",
                individual_count=2,
                event_occasion="Briefing",
            )

            details = store.list_recognition_details_for_embedding(embedding.embedding_id)

            self.assertEqual(len(details), 1)
            self.assertEqual(details[0].detail_id, detail.detail_id)
            self.assertEqual(details[0].embedding_id, embedding.embedding_id)
            self.assertEqual(details[0].image_id, "image-a.jpg")
            self.assertEqual(details[0].name, "Seen Person")
            self.assertEqual(details[0].individual_count, 2)

    def test_v1_database_migrates_to_v2(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / "sentriface.db"
            with sqlite3.connect(db_path) as conn:
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

            with sqlite3.connect(db_path) as conn:
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
            with sqlite3.connect(db_path) as conn:
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

            with sqlite3.connect(db_path) as conn:
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
            with sqlite3.connect(db_path) as conn:
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

            with sqlite3.connect(db_path) as conn:
                version = conn.execute("PRAGMA user_version").fetchone()[0]
                tables = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }

            self.assertEqual(version, SCHEMA_VERSION)
            self.assertIn("recognition_details", tables)


if __name__ == "__main__":
    unittest.main()
