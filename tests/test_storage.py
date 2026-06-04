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


if __name__ == "__main__":
    unittest.main()
