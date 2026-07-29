from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sentriface.backup_crypto import (
    BackupEncryptionError,
    MAGIC,
    decrypt_file,
    encrypt_file,
)


class BackupCryptoTest(unittest.TestCase):
    def test_round_trip_streams_and_authenticates_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.sfbackup"
            encrypted = root / "export.sfbackup.enc"
            restored = root / "restored.sfbackup"
            content = (b"portable-backup-data" * 100_000) + b"end"
            source.write_bytes(content)

            encrypt_file(source, encrypted, "correct horse battery staple")
            decrypt_file(encrypted, restored, "correct horse battery staple")

            self.assertEqual(restored.read_bytes(), content)
            self.assertTrue(encrypted.read_bytes().startswith(MAGIC))
            self.assertNotIn(b"portable-backup-data", encrypted.read_bytes())

    def test_wrong_passphrase_does_not_publish_plaintext(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.sfbackup"
            encrypted = root / "export.sfbackup.enc"
            destination = root / "restored.sfbackup"
            source.write_bytes(b"sensitive")
            encrypt_file(source, encrypted, "correct horse battery staple")

            with self.assertRaisesRegex(
                BackupEncryptionError, "Incorrect passphrase"
            ):
                decrypt_file(encrypted, destination, "entirely wrong password")

            self.assertFalse(destination.exists())
            self.assertEqual(list(root.glob(".restored.sfbackup.*.tmp")), [])

    def test_tampered_ciphertext_is_rejected_and_cleaned_up(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.sfbackup"
            encrypted = root / "export.sfbackup.enc"
            destination = root / "restored.sfbackup"
            source.write_bytes(b"sensitive" * 100)
            encrypt_file(source, encrypted, "correct horse battery staple")
            damaged = bytearray(encrypted.read_bytes())
            damaged[-17] ^= 1
            encrypted.write_bytes(damaged)

            with self.assertRaisesRegex(BackupEncryptionError, "damaged"):
                decrypt_file(encrypted, destination, "correct horse battery staple")

            self.assertFalse(destination.exists())

    def test_short_passphrase_is_rejected_without_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.sfbackup"
            destination = root / "export.sfbackup.enc"
            source.write_bytes(b"sensitive")

            with self.assertRaisesRegex(BackupEncryptionError, "12"):
                encrypt_file(source, destination, "too short")

            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
