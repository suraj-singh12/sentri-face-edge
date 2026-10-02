from __future__ import annotations

import base64
import hashlib
import os
import secrets
import sqlite3
import stat
import sys
import threading
import uuid
from pathlib import Path
from typing import Any


KEYRING_SERVICE = "SentriFace Edge storage"
SQLITE_HEADER = b"SQLite format 3\x00"
LINUX_SOURCE_KEY_NAME = ".sentriface-linux-source-key"
_LINUX_SOURCE_KEY_MAGIC = b"SENTRIFACE-LINUX-SOURCE-KEY-v1\n"
class _DatabaseLockEntry:
    """Reference-count one serialized SQLCipher path without retaining dead paths."""

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.users = 0


_DATABASE_LOCKS: dict[str, _DatabaseLockEntry] = {}
_DATABASE_LOCKS_GUARD = threading.Lock()


class StorageSecurityError(RuntimeError):
    """Raised when encrypted storage cannot be opened without weakening security."""


def load_linux_source_master_key(data_dir: Path, *, explicit_source_onnx: bool) -> bytes:
    """Persistent local custody only for explicitly admitted Linux source ONNX."""
    checkout = Path(__file__).resolve().parents[2]
    if (
        sys.platform != "linux" or not explicit_source_onnx
        or getattr(sys, "frozen", False) or "__compiled__" in globals()
        or not (checkout / ".git").exists()
    ):
        raise StorageSecurityError("Linux source key custody requires explicit unpackaged source ONNX")
    root = data_dir.expanduser().absolute()
    production = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "sentriface"
    if root.resolve() in {production.resolve(), (Path.home() / "Library" / "Application Support" / "SentriFace").resolve()}:
        raise StorageSecurityError("Linux source key custody cannot use installed-product authority")
    if any(path.is_symlink() for path in (root, *root.parents)):
        raise StorageSecurityError("Linux source key authority cannot contain symbolic links")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root_info = root.stat()
    if root_info.st_uid != os.getuid() or root_info.st_mode & 0o022:
        raise StorageSecurityError("Linux source key authority must be owned and not writable by other users")
    path = root / LINUX_SOURCE_KEY_NAME
    binding = hashlib.sha256(os.fsencode(root.resolve())).digest()
    prefix = _LINUX_SOURCE_KEY_MAGIC + binding
    try:
        if not path.exists() and not path.is_symlink():
            # A lost key is not a fresh authority. Never replace it over history.
            from sentriface.secure_files import is_protected_file
            if any(
                item.is_symlink() or (
                    item.is_file() and item.stat().st_size and (
                        item.suffix in {".db", ".sflog"} or is_protected_file(item)
                    )
                ) for item in root.rglob("*")
            ):
                raise StorageSecurityError("Linux source key is missing for existing authority")
            key = secrets.token_bytes(32)
            try:
                descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            except FileExistsError:
                pass
            else:
                with os.fdopen(descriptor, "wb") as output:
                    output.write(prefix + key)
                    output.flush()
                    os.fsync(output.fileno())
                directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as source:
            info = os.fstat(source.fileno())
            if (
                not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o077 or info.st_nlink != 1
            ):
                raise StorageSecurityError("Linux source key file permissions or ownership are unsafe")
            record = source.read(len(prefix) + 33)
        if len(record) != len(prefix) + 32 or not secrets.compare_digest(record[:len(prefix)], prefix):
            raise StorageSecurityError("Linux source key record is invalid or belongs to another authority")
        key = record[len(prefix):]
        validate_recovered_master_key(root, key)
        for database in root.rglob("*.db"):
            if database_is_encrypted(database):
                _verify_encrypted_database(database, key)
        _validate_source_log_keys(root, key)
        return key
    except StorageSecurityError:
        raise
    except Exception:
        raise StorageSecurityError("Linux source key custody could not be opened safely") from None


def _validate_source_log_keys(data_dir: Path, key: bytes) -> None:
    """Avoid appending with a different key even when only encrypted logs survive."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from sentriface.logging_config import ENCRYPTED_LOG_MAGIC

    for path in data_dir.rglob("*.sflog"):
        with path.open("rb") as source:
            if source.read(len(ENCRYPTED_LOG_MAGIC)) != ENCRYPTED_LOG_MAGIC:
                raise StorageSecurityError("Existing source encrypted log is invalid")
            while nonce := source.read(12):
                size = source.read(4)
                if len(nonce) != 12 or len(size) != 4:
                    raise StorageSecurityError("Existing source encrypted log is truncated")
                length = int.from_bytes(size, "big")
                if not 16 <= length <= 16 * 1024 * 1024:
                    raise StorageSecurityError("Existing source encrypted log frame is invalid")
                ciphertext = source.read(length)
                if len(ciphertext) != length:
                    raise StorageSecurityError("Existing source encrypted log is truncated")
                AESGCM(key).decrypt(nonce, ciphertext, ENCRYPTED_LOG_MAGIC)


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
    database_lock_key, database_lock_entry = _acquire_database_lock(path)
    connection = None
    try:
        driver = _sqlcipher_driver()
        connection = driver.connect(path, timeout=timeout)
        _apply_key(connection, key)
        if row_factory:
            connection.row_factory = driver.Row
        return _SerializedConnection(connection, database_lock_key, database_lock_entry)
    except Exception:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass
        _release_database_lock(database_lock_key, database_lock_entry)
        raise


def _acquire_database_lock(path: Path) -> tuple[str, _DatabaseLockEntry]:
    resolved = str(path.resolve())
    with _DATABASE_LOCKS_GUARD:
        entry = _DATABASE_LOCKS.setdefault(resolved, _DatabaseLockEntry())
        entry.users += 1
    entry.lock.acquire()
    return resolved, entry


def _release_database_lock(resolved: str, entry: _DatabaseLockEntry) -> None:
    entry.lock.release()
    with _DATABASE_LOCKS_GUARD:
        entry.users -= 1
        if entry.users == 0 and _DATABASE_LOCKS.get(resolved) is entry:
            del _DATABASE_LOCKS[resolved]


class _SerializedConnection:
    """Hold one per-database lock for the complete SQLCipher connection lifetime."""

    def __init__(
        self,
        connection: Any,
        lock_key: str,
        lock_entry: _DatabaseLockEntry,
    ) -> None:
        object.__setattr__(self, "_connection", connection)
        object.__setattr__(self, "_lock_key", lock_key)
        object.__setattr__(self, "_lock_entry", lock_entry)
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
            _release_database_lock(self._lock_key, self._lock_entry)


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
