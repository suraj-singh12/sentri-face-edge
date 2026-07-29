from __future__ import annotations

import secrets
import socket
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock, patch

from sentriface.backup_service import BackupService
from sentriface.offline_guard import OfflineViolationError, install_offline_guard, require_local_path
from sentriface.recovery import RECOVERY_KIT_NAME, RecoveryError, RecoveryService, recover_master_key
from sentriface.secure_files import ProtectedFileError, read_protected_bytes, write_protected_bytes
from sentriface.secure_storage import connect_database, ensure_encrypted_database
from sentriface.storage.sqlite_store import SCHEMA_VERSION, SQLiteIdentityStore


class V1SecurityTest(unittest.TestCase):
    def test_managed_file_is_authenticated_and_not_plaintext(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "face.jpg"
            key = secrets.token_bytes(32)
            plaintext = b"private-face-bytes" * 100
            write_protected_bytes(path, plaintext, key)
            self.assertNotIn(b"private-face-bytes", path.read_bytes())
            self.assertEqual(read_protected_bytes(path, key), plaintext)
            damaged = bytearray(path.read_bytes())
            damaged[-1] ^= 1
            path.write_bytes(damaged)
            with self.assertRaises(ProtectedFileError):
                read_protected_bytes(path, key)

    def test_sqlcipher_database_blocks_standard_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "sentriface.db"
            key = secrets.token_bytes(32)
            store = SQLiteIdentityStore(path, database_key=key)
            store.initialize()
            self.assertEqual(store._schema_version(), SCHEMA_VERSION)
            with closing(sqlite3.connect(path)) as connection:
                with self.assertRaises(sqlite3.DatabaseError):
                    connection.execute("SELECT * FROM persons").fetchone()

    def test_plaintext_database_migrates_without_data_loss(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "legacy.db"
            with closing(sqlite3.connect(path)) as connection, connection:
                connection.execute("CREATE TABLE values_table(value INTEGER)")
                connection.execute("INSERT INTO values_table VALUES (7)")
            key = secrets.token_bytes(32)
            self.assertTrue(ensure_encrypted_database(path, key))
            with closing(connect_database(path, key)) as connection:
                self.assertEqual(connection.execute("SELECT value FROM values_table").fetchone()[0], 7)

    def test_recovery_code_unlocks_external_kit_and_automatic_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data_dir = root / "data"
            destination = root / "external"
            master_key = secrets.token_bytes(32)
            SQLiteIdentityStore(data_dir / "sentriface.db", database_key=master_key).initialize()
            backups = BackupService(
                data_dir / "sentriface.db",
                data_dir / "backups",
                data_dir=data_dir,
                database_key=master_key,
            )
            stored = {}
            with patch("sentriface.recovery._store_recovery_code", lambda _path, code: stored.update(code=code)), patch(
                "sentriface.recovery._load_recovery_code", lambda _path: stored.get("code")
            ):
                recovery = RecoveryService(data_dir, master_key, backups)
                configured = recovery.configure(destination)
                backup = recovery.automatic_backup_if_due()
                self.assertIsNotNone(backup)
                self.assertEqual(
                    recover_master_key(destination / RECOVERY_KIT_NAME, configured["recovery_code"]),
                    master_key,
                )
                self.assertTrue(list(destination.glob("*.sfbackup.enc")))
                for index in range(12):
                    (destination / f"old-{index}.sfbackup.enc").write_bytes(b"old")
                recovery._prune_external_backups(destination)
                self.assertEqual(len(list(destination.glob("*.sfbackup.enc"))), backups.retention_limit)

    def test_recovery_rejects_network_share_before_access(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            service = RecoveryService(root / "data", secrets.token_bytes(32), Mock())
            with self.assertRaises(RecoveryError):
                service.configure(Path(r"\\server\share"))

    def test_offline_guard_rejects_non_loopback_destinations(self) -> None:
        install_offline_guard()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
            with self.assertRaises(OfflineViolationError):
                connection.connect(("8.8.8.8", 443))
        with self.assertRaises(OfflineViolationError):
            socket.getaddrinfo("example.com", 443)
        with self.assertRaises(OfflineViolationError):
            socket.gethostbyname("example.com")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            with self.assertRaises(OfflineViolationError):
                listener.bind(("0.0.0.0", 0))
        with self.assertRaises(OfflineViolationError):
            require_local_path(Path(r"\\server\share"))
        self.assertTrue(socket.getaddrinfo("127.0.0.1", 80))


if __name__ == "__main__":
    unittest.main()
