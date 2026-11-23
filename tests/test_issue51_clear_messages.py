from __future__ import annotations

import secrets
import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path

from sentriface.secure_storage import DATABASE_ERRORS, INTEGRITY_ERRORS
from sentriface.storage.sqlite_helpers import PlaceholderNameConflict
from sentriface.storage.sqlite_store import SQLiteIdentityStore


class EncryptedStoreConflictTest(unittest.TestCase):
    def test_error_tuples_cover_both_drivers(self) -> None:
        from sqlcipher3 import dbapi2

        self.assertIn(sqlite3.IntegrityError, INTEGRITY_ERRORS)
        self.assertIn(dbapi2.IntegrityError, INTEGRITY_ERRORS)
        self.assertIn(dbapi2.DatabaseError, DATABASE_ERRORS)

    def test_placeholder_rename_conflict_is_actionable_on_encrypted_store(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = SQLiteIdentityStore(Path(temp) / "sentriface.db", database_key=secrets.token_bytes(32))
            store.initialize()
            store._legacy_create_placeholder_person("Unknown visitor 3", {}, "Operator", str(uuid.uuid4()))
            second = store._legacy_create_placeholder_person("Unknown visitor 4", {}, "Operator", str(uuid.uuid4()))
            with self.assertRaises(PlaceholderNameConflict) as caught:
                store.update_person_profile(
                    second.person_id,
                    "unknown visitor 3",
                    None,
                    None,
                    None,
                    "Operator",
                    operation_id=str(uuid.uuid4()),
                )
            self.assertEqual(caught.exception.reason, "placeholder_name_taken")
            self.assertIn("Another unknown person is already called “unknown visitor 3”", str(caught.exception))
            self.assertNotIn("UNIQUE", str(caught.exception))
            self.assertEqual(store.get_person(second.person_id).name, "Unknown visitor 4")


if __name__ == "__main__":
    unittest.main()
