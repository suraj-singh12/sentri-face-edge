from __future__ import annotations

import base64
import hashlib
import os
import secrets
import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Any


KEYRING_SERVICE = "SentriFace Edge storage"
SQLITE_HEADER = b"SQLite format 3\x00"
_DATABASE_LOCKS: dict[str, threading.RLock] = {}
_DATABASE_LOCKS_GUARD = threading.Lock()


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


def validate_recovered_master_key(data_dir: Path, key: bytes) -> None:
    """Prove a recovered key against existing authority before replacing vault state."""
    if not isinstance(key, bytes) or len(key) != 32:
        raise StorageSecurityError("Recovered SentriFace storage key is invalid")
    database = data_dir / "sentriface.db"
    if database.exists() and database.stat().st_size:
        _verify_encrypted_database(database, key)
    from sentriface.secure_files import authenticate_protected_file, is_protected_file

    if not data_dir.exists():
        return
    for candidate in data_dir.rglob("*"):
        if candidate.is_symlink():
            raise StorageSecurityError("Managed storage contains an unsafe symbolic link")
        if candidate.is_file() and is_protected_file(candidate):
            try:
                authenticate_protected_file(candidate, key)
            except Exception as exc:
                raise StorageSecurityError(
                    "Recovered key is incompatible with existing managed storage"
                ) from exc

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
    database_lock = _database_lock(path)
    database_lock.acquire()
    connection = None
    try:
        driver = _sqlcipher_driver()
        connection = driver.connect(path, timeout=timeout)
        _apply_key(connection, key)
        if row_factory:
            connection.row_factory = driver.Row
        return _SerializedConnection(connection, database_lock)
    except Exception:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass
        database_lock.release()
        raise


def _database_lock(path: Path) -> threading.RLock:
    resolved = str(path.resolve())
    with _DATABASE_LOCKS_GUARD:
        return _DATABASE_LOCKS.setdefault(resolved, threading.RLock())


class _SerializedConnection:
    """Hold one per-database lock for the complete SQLCipher connection lifetime."""

    def __init__(self, connection: Any, lock: threading.RLock) -> None:
        object.__setattr__(self, "_connection", connection)
        object.__setattr__(self, "_lock", lock)
        object.__setattr__(self, "_closed", False)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            object.__setattr__(self, name, value)
        else:
            setattr(self._connection, name, value)

    def backup(self, destination: Any, *args: Any, **kwargs: Any) -> Any:
        raw_destination = (
            destination._connection
            if isinstance(destination, _SerializedConnection)
            else destination
        )
        return self._connection.backup(raw_destination, *args, **kwargs)

    def close(self) -> None:
        if self._closed:
            return
        try:
            self._connection.close()
        finally:
            object.__setattr__(self, "_closed", True)
            self._lock.release()


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
    for candidate in data_dir.rglob("*"):
        if candidate.is_symlink():
            raise StorageSecurityError("Managed storage contains an unsafe symbolic link")
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
