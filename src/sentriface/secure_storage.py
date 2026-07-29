from __future__ import annotations

import base64
import hashlib
import os
import secrets
import sqlite3
import uuid
from pathlib import Path
from typing import Any


KEYRING_SERVICE = "SentriFace Edge storage"
SQLITE_HEADER = b"SQLite format 3\x00"


class StorageSecurityError(RuntimeError):
    """Raised when encrypted storage cannot be opened without weakening security."""


def load_or_create_master_key(data_dir: Path) -> bytes:
    """Load a per-installation key from the OS vault, creating it when absent."""
    try:
        import keyring
        from keyring.errors import KeyringError
    except ImportError as exc:
        raise StorageSecurityError("OS keyring support is required for encrypted storage") from exc

    account = _keyring_account(data_dir)
    try:
        encoded = keyring.get_password(KEYRING_SERVICE, account)
        if encoded:
            key = base64.urlsafe_b64decode(encoded.encode("ascii"))
            if len(key) != 32:
                raise StorageSecurityError("The stored SentriFace encryption key is invalid")
            return key
        key = secrets.token_bytes(32)
        encoded = base64.urlsafe_b64encode(key).decode("ascii")
        keyring.set_password(KEYRING_SERVICE, account, encoded)
        if keyring.get_password(KEYRING_SERVICE, account) != encoded:
            raise StorageSecurityError("The operating-system key vault did not retain the storage key")
        return key
    except KeyringError as exc:
        raise StorageSecurityError(f"The operating-system key vault is unavailable: {exc}") from exc


def store_master_key(data_dir: Path, key: bytes) -> None:
    """Store a recovered installation key in the current machine's OS vault."""
    if not isinstance(key, bytes) or len(key) != 32:
        raise StorageSecurityError("Recovered SentriFace storage key is invalid")
    try:
        import keyring
        from keyring.errors import KeyringError
        encoded = base64.urlsafe_b64encode(key).decode("ascii")
        keyring.set_password(KEYRING_SERVICE, _keyring_account(data_dir), encoded)
    except (ImportError, KeyringError) as exc:
        raise StorageSecurityError(f"Recovered key could not be stored in the OS vault: {exc}") from exc

def connect_database(
    path: Path,
    key: bytes | None = None,
    *,
    timeout: float = 30,
    row_factory: bool = False,
):
    if key is None:
        connection = sqlite3.connect(path, timeout=timeout)
        if row_factory:
            connection.row_factory = sqlite3.Row
        return connection
    driver = _sqlcipher_driver()
    connection = driver.connect(path, timeout=timeout)
    _apply_key(connection, key)
    if row_factory:
        connection.row_factory = driver.Row
    return connection


def ensure_encrypted_database(path: Path, key: bytes) -> bool:
    """Encrypt a legacy plaintext SQLite database atomically; return True if migrated."""
    if not path.exists() or path.stat().st_size == 0:
        return False
    with path.open("rb") as source:
        header = source.read(len(SQLITE_HEADER))
    if header != SQLITE_HEADER:
        _verify_encrypted_database(path, key)
        return False

    driver = _sqlcipher_driver()
    encrypted = path.with_name(f".{path.name}.{uuid.uuid4().hex}.encrypted")
    previous = path.with_name(f".{path.name}.{uuid.uuid4().hex}.plaintext-migration")
    connection = driver.connect(path, timeout=30)
    try:
        escaped = str(encrypted).replace("'", "''")
        connection.execute(f"ATTACH DATABASE '{escaped}' AS encrypted KEY \"x'{key.hex()}'\"")
        connection.execute("SELECT sqlcipher_export('encrypted')")
        connection.execute("DETACH DATABASE encrypted")
        connection.close()
        _verify_encrypted_database(encrypted, key)
        os.replace(path, previous)
        try:
            os.replace(encrypted, path)
        except Exception:
            os.replace(previous, path)
            raise
        previous.unlink(missing_ok=True)
        return True
    except Exception as exc:
        try:
            connection.close()
        except Exception:
            pass
        encrypted.unlink(missing_ok=True)
        if isinstance(exc, StorageSecurityError):
            raise
        raise StorageSecurityError(f"Existing database could not be encrypted safely: {exc}") from exc


def database_is_encrypted(path: Path) -> bool:
    if not path.exists() or path.stat().st_size <= 0:
        return False
    with path.open("rb") as source:
        return source.read(len(SQLITE_HEADER)) != SQLITE_HEADER


def protect_existing_managed_data(data_dir: Path, key: bytes) -> dict[str, int]:
    """Migrate legacy managed databases and biometric files to encrypted storage."""
    from sentriface.secure_files import copy_into_protected_storage, is_protected_file

    migrated = {"databases": 0, "files": 0}
    if not data_dir.exists():
        return migrated
    for database in data_dir.rglob("*.db"):
        if database.is_file() and ensure_encrypted_database(database, key):
            migrated["databases"] += 1
    image_suffixes = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    for image in data_dir.rglob("*"):
        if not image.is_file() or image.suffix.lower() not in image_suffixes or is_protected_file(image):
            continue
        temporary = image.with_name(f".{image.name}.{uuid.uuid4().hex}.protected")
        try:
            copy_into_protected_storage(image, temporary, key)
            os.replace(temporary, image)
            migrated["files"] += 1
        finally:
            temporary.unlink(missing_ok=True)
    return migrated

def _verify_encrypted_database(path: Path, key: bytes) -> None:
    try:
        connection = connect_database(path, key)
        try:
            result = connection.execute("PRAGMA integrity_check").fetchone()
            if not result or result[0] != "ok":
                raise StorageSecurityError("Encrypted database integrity verification failed")
        finally:
            connection.close()
    except StorageSecurityError:
        raise
    except Exception as exc:
        raise StorageSecurityError("Encrypted database could not be opened with this machine's key") from exc


def _sqlcipher_driver() -> Any:
    try:
        from sqlcipher3 import dbapi2
    except ImportError as exc:
        raise StorageSecurityError("SQLCipher is required for encrypted live database storage") from exc
    return dbapi2


def _apply_key(connection: Any, key: bytes) -> None:
    if len(key) != 32:
        raise StorageSecurityError("SentriFace database keys must be 256 bits")
    connection.execute(f"PRAGMA key = \"x'{key.hex()}'\"")
    cipher_version = connection.execute("PRAGMA cipher_version").fetchone()
    if not cipher_version or not cipher_version[0]:
        connection.close()
        raise StorageSecurityError("The active SQLite library does not provide SQLCipher")


def _keyring_account(data_dir: Path) -> str:
    normalized = str(data_dir.resolve()).casefold().encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()
