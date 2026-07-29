from __future__ import annotations

import os
import struct
import sys
import threading
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from loguru import logger

from sentriface.paths import default_log_dir
from sentriface.secure_files import copy_into_protected_storage


ENCRYPTED_LOG_MAGIC = b"SENTRIFACE-ENCRYPTED-LOG\n"


class EncryptedLogSink:
    """Append individually authenticated log records without plaintext log files."""

    def __init__(self, path: Path, key: bytes) -> None:
        self.path = path
        self.key = key
        self.lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            with path.open("xb") as output:
                output.write(ENCRYPTED_LOG_MAGIC)
                output.flush()
                os.fsync(output.fileno())

    def write(self, message) -> None:
        plaintext = str(message).encode("utf-8", errors="replace")
        nonce = os.urandom(12)
        ciphertext = AESGCM(self.key).encrypt(nonce, plaintext, ENCRYPTED_LOG_MAGIC)
        frame = nonce + struct.pack(">I", len(ciphertext)) + ciphertext
        with self.lock, self.path.open("ab") as output:
            output.write(frame)
            output.flush()


def setup_logging(
    debug: bool = True,
    log_dir: Path | None = None,
    storage_key: bytes | None = None,
) -> None:
    logger.remove()
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
        logger.warning("File logging is unavailable: {}", exc)


def _protect_legacy_log(log_dir: Path, key: bytes) -> None:
    legacy = log_dir / "sentriface.log"
    if not legacy.exists() or not legacy.is_file():
        return
    protected = log_dir / "sentriface-legacy.log.protected"
    copy_into_protected_storage(legacy, protected, key)
    legacy.unlink()
