from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from sentriface.backup_service import BackupError, BackupService
from sentriface.storage.sqlite_store import SCHEMA_VERSION, SQLiteIdentityStore


class BackupServiceTest(unittest.TestCase):
    def test_successful_backup_creation_writes_verified_snapshot_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "sentriface.db"
            self._seed_database(db_path)
            service = self._service(db_path, root / "backups")

            record = service.create_backup()

            backup_dir = root / "backups" / record.backup_id
            backup_db = backup_dir / "sentriface.db"
            metadata = json.loads((backup_dir / "backup.json").read_text(encoding="utf-8"))
            self.assertTrue(backup_db.exists())
            self.assertTrue(record.verified)
            self.assertEqual(record.people_count, 1)
            self.assertEqual(record.embedding_count, 1)
            self.assertEqual(record.database_version, SCHEMA_VERSION)
            self.assertEqual(metadata["backup_id"], record.backup_id)
            self.assertEqual(metadata["people_count"], 1)
            self.assertEqual(metadata["embedding_count"], 1)
            self.assertEqual(metadata["database_size_bytes"], backup_db.stat().st_size)
            self.assertTrue(service.verify_backup(record.backup_id))

    def test_duplicate_timestamp_gets_unique_backup_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "sentriface.db"
            self._seed_database(db_path)
            service = self._service(db_path, root / "backups")

            first = service.create_backup()
            second = service.create_backup()

            self.assertEqual(first.backup_id, "backup_2026-07-15_22-14-08")
            self.assertEqual(second.backup_id, "backup_2026-07-15_22-14-08_01")

    def test_incomplete_backup_directory_is_removed_when_verification_fails(self) -> None:
        class FailingVerifyBackupService(BackupService):
            def verify_backup(self, backup_id: str) -> bool:
                return False

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "sentriface.db"
            self._seed_database(db_path)
            service = FailingVerifyBackupService(db_path, root / "backups", now=self._fixed_now)

            with self.assertRaises(BackupError):
                service.create_backup()

            self.assertFalse((root / "backups" / "backup_2026-07-15_22-14-08").exists())

    def test_listing_backups_returns_newest_first(self) -> None:
        times = iter([
            datetime(2026, 7, 12, 18, 30, 41, tzinfo=timezone.utc),
            datetime(2026, 7, 15, 22, 14, 8, tzinfo=timezone.utc),
        ])

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "sentriface.db"
            self._seed_database(db_path)
            service = BackupService(db_path, root / "backups", now=lambda: next(times))
            older = service.create_backup()
            newer = service.create_backup()

            backups = service.list_backups()

            self.assertEqual([item.backup_id for item in backups], [newer.backup_id, older.backup_id])

    def test_retention_keeps_latest_ten_backups(self) -> None:
        counter = {"value": 0}

        def next_time() -> datetime:
            counter["value"] += 1
            return datetime(2026, 7, 15, 22, 0, counter["value"], tzinfo=timezone.utc)

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "sentriface.db"
            self._seed_database(db_path)
            service = BackupService(db_path, root / "backups", retention_limit=10, now=next_time)

            created = [service.create_backup().backup_id for _ in range(12)]

            remaining = [item.backup_id for item in service.list_backups()]
            self.assertEqual(len(remaining), 10)
            self.assertNotIn(created[0], remaining)
            self.assertNotIn(created[1], remaining)
            self.assertIn(created[-1], remaining)

    def test_invalid_backup_ids_and_traversal_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "sentriface.db"
            self._seed_database(db_path)
            service = self._service(db_path, root / "backups")

            for backup_id in ["../../database.db", "backup_2026-07-15_22-14-08/../../x", "sentriface.db"]:
                with self.subTest(backup_id=backup_id):
                    with self.assertRaises(BackupError):
                        service.delete_backup(backup_id)

    def test_delete_backup_removes_only_managed_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            db_path = root / "sentriface.db"
            self._seed_database(db_path)
            service = self._service(db_path, root / "backups")
            record = service.create_backup()

            service.delete_backup(record.backup_id)

            self.assertFalse((root / "backups" / record.backup_id).exists())
            self.assertTrue(db_path.exists())

    def _seed_database(self, db_path: Path) -> None:
        store = SQLiteIdentityStore(db_path, embedding_dim=4)
        store.initialize()
        person = store.create_person("Backup Person")
        store.add_embedding(person.person_id, [0.1, 0.2, 0.3, 0.4], quality_score=0.9)

    def _service(self, db_path: Path, backup_dir: Path) -> BackupService:
        return BackupService(db_path, backup_dir, now=self._fixed_now)

    def _fixed_now(self) -> datetime:
        return datetime(2026, 7, 15, 22, 14, 8, tzinfo=timezone.utc)


if __name__ == "__main__":
    unittest.main()
