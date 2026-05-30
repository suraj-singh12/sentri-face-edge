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


if __name__ == "__main__":
    unittest.main()
