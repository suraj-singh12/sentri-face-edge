from __future__ import annotations

import os
import re
import struct
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from loguru import logger

from sentriface.paths import default_log_dir
from sentriface.secure_files import copy_into_protected_storage


ENCRYPTED_LOG_MAGIC = b"SENTRIFACE-ENCRYPTED-LOG\n"
DEFAULT_LOG_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_LOG_RETENTION = 7
MAX_LOG_VALUE_CHARS = 1000
_SENSITIVE_KEYS = (
    "authorization", "cookie", "credential", "database_path", "db_path",
    "directory", "embedding", "key", "note", "passphrase", "password",
    "path", "payload", "recovery_code", "secret", "session", "sql", "token",
)
_ABSOLUTE_PATH = re.compile(r"(?<![A-Za-z0-9])(?:[A-Za-z]:[\\/][^\s,;]+|/(?:[^\s,;]+/?)+)")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(password|passphrase|token|secret|recovery[_ -]?code|authorization)\b\s*[:=]\s*[^\s,;]+"
)


class EncryptedLogSink:
    """Append individually authenticated log records without plaintext log files."""

    def __init__(
        self,
        path: Path,
        key: bytes,
        *,
        max_bytes: int = DEFAULT_LOG_MAX_BYTES,
        retention: int = DEFAULT_LOG_RETENTION,
    ) -> None:
        self.path = path
        self.key = key
        self.max_bytes = max(1024, int(max_bytes))
        self.retention = max(1, int(retention))
        self.lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._create_if_missing()

    def write(self, message) -> None:
        plaintext = str(message).encode("utf-8", errors="replace")
        nonce = os.urandom(12)
        ciphertext = AESGCM(self.key).encrypt(nonce, plaintext, ENCRYPTED_LOG_MAGIC)
        frame = nonce + struct.pack(">I", len(ciphertext)) + ciphertext
        with self.lock:
            if self.path.stat().st_size + len(frame) > self.max_bytes:
                self._rotate()
            with self.path.open("ab") as output:
                output.write(frame)
                output.flush()
                os.fsync(output.fileno())

    def _create_if_missing(self) -> None:
        if self.path.exists():
            if self.path.is_symlink():
                raise OSError("Encrypted log location is unsafe")
            with self.path.open("rb") as source:
                if source.read(len(ENCRYPTED_LOG_MAGIC)) != ENCRYPTED_LOG_MAGIC:
                    raise OSError("Encrypted log format is invalid")
            return
        with self.path.open("xb") as output:
            output.write(ENCRYPTED_LOG_MAGIC)
            output.flush()
            os.fsync(output.fileno())

    def _rotate(self) -> None:
        rotated = self.path.with_name(
            f"sentriface-{int(time.time())}-{uuid.uuid4().hex[:8]}.sflog"
        )
        os.replace(self.path, rotated)
        self._create_if_missing()
        archives = sorted(
            self.path.parent.glob("sentriface-*-*.sflog"),
            key=lambda item: item.stat().st_mtime_ns,
            reverse=True,
        )
        for expired in archives[self.retention:]:
            expired.unlink(missing_ok=True)


def setup_logging(
    debug: bool = False,
    log_dir: Path | None = None,
    storage_key: bytes | None = None,
    *,
    require_persistent: bool = False,
) -> None:
    logger.remove()
    logger.configure(patcher=lambda record: record.update(message=redact_log_text(record["message"])))
    level = "DEBUG" if debug else "INFO"

    logger.add(
        sys.stderr,
        level=level,
        format=(
            "<green>{time:HH:mm:ss}</green> | "
            "<level>{level:8}</level> | "
            "<cyan>{file}:{line}</cyan> | "
            "<cyan>{function}</cyan> | "
            "<level>{message}</level>"
        ),
    )

    resolved_log_dir = log_dir or default_log_dir()
    try:
        resolved_log_dir.mkdir(parents=True, exist_ok=True)
        if storage_key is not None:
            _protect_legacy_log(resolved_log_dir, storage_key)
            logger.add(
                EncryptedLogSink(resolved_log_dir / "sentriface.sflog", storage_key).write,
                level=level,
                backtrace=False,
                diagnose=False,
            )
        else:
            logger.add(
                resolved_log_dir / "sentriface.log",
                rotation="10 MB",
                retention="7 days",
                level=level,
                backtrace=debug,
                diagnose=False,
            )
    except OSError as exc:
        if require_persistent:
            raise OSError("Persistent encrypted logging is unavailable") from exc
        logger.warning("File logging is unavailable")


def redact_log_text(value: object) -> str:
    text = str(value)
    text = _SECRET_ASSIGNMENT.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)
    text = _ABSOLUTE_PATH.sub("[REDACTED_PATH]", text)
    if len(text) > MAX_LOG_VALUE_CHARS:
        text = text[:MAX_LOG_VALUE_CHARS] + "…"
    return text


def sanitize_log_details(value: object, *, key: str = "") -> object:
    lowered = key.casefold()
    if any(fragment in lowered for fragment in _SENSITIVE_KEYS):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {
            str(item_key)[:80]: sanitize_log_details(item_value, key=str(item_key))
            for item_key, item_value in list(value.items())[:40]
        }
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"<binary omitted; {len(value)} bytes>"
    if isinstance(value, (list, tuple, set, frozenset)):
        return f"<sequence omitted; {len(value)} items>"
    if isinstance(value, str):
        if lowered == "endpoint" and value.startswith("/api/") and ".." not in value:
            return value[:160]
        return redact_log_text(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return redact_log_text(value)


def _protect_legacy_log(log_dir: Path, key: bytes) -> None:
    legacy = log_dir / "sentriface.log"
    if not legacy.exists() or not legacy.is_file():
        return
    protected = log_dir / "sentriface-legacy.log.protected"
    copy_into_protected_storage(legacy, protected, key)
    legacy.unlink()
