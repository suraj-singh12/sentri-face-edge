from __future__ import annotations

import base64
import json
import os
import struct
import uuid
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt


ENCRYPTED_BACKUP_EXTENSION = ".sfbackup.enc"
MAGIC = b"SENTRIFACE-ENCRYPTED-BACKUP\n"
FORMAT_VERSION = 1
HEADER_LIMIT = 4096
TAG_LENGTH = 16
CHUNK_SIZE = 1024 * 1024
SCRYPT_N = 2**15
SCRYPT_R = 8
SCRYPT_P = 1
MIN_PASSPHRASE_LENGTH = 12
MAX_PASSPHRASE_LENGTH = 1024


class BackupEncryptionError(RuntimeError):
    """Raised when an encrypted backup cannot be safely processed."""


def validate_passphrase(passphrase: str) -> bytes:
    if not isinstance(passphrase, str):
        raise BackupEncryptionError("Backup passphrase is required")
    if not MIN_PASSPHRASE_LENGTH <= len(passphrase) <= MAX_PASSPHRASE_LENGTH:
        raise BackupEncryptionError(
            f"Backup passphrase must be {MIN_PASSPHRASE_LENGTH} to "
            f"{MAX_PASSPHRASE_LENGTH} characters"
        )
    encoded = passphrase.encode("utf-8")
    if len(encoded) > 4096:
        raise BackupEncryptionError("Backup passphrase is too long")
    return encoded


def encrypt_file(source: Path, destination: Path, passphrase: str) -> Path:
    password = validate_passphrase(passphrase)
    if not source.is_file():
        raise BackupEncryptionError("Portable backup file was not found")
    salt = os.urandom(16)
    nonce = os.urandom(12)
    header = {
        "cipher": "AES-256-GCM",
        "format": "sentriface-encrypted-backup",
        "kdf": {
            "name": "scrypt",
            "n": SCRYPT_N,
            "p": SCRYPT_P,
            "r": SCRYPT_R,
            "salt": _b64(salt),
        },
        "nonce": _b64(nonce),
        "plaintext_size": source.stat().st_size,
        "tag_length": TAG_LENGTH,
        "version": FORMAT_VERSION,
    }
    header_bytes = json.dumps(
        header, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    prefix = MAGIC + struct.pack(">I", len(header_bytes)) + header_bytes
    key = _derive_key(password, salt)
    encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(prefix)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    try:
        with source.open("rb") as reader, temporary.open("xb") as writer:
            writer.write(prefix)
            for chunk in iter(lambda: reader.read(CHUNK_SIZE), b""):
                writer.write(encryptor.update(chunk))
            writer.write(encryptor.finalize())
            writer.write(encryptor.tag)
            writer.flush()
            os.fsync(writer.fileno())
        os.replace(temporary, destination)
        return destination
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def decrypt_file(source: Path, destination: Path, passphrase: str) -> Path:
    password = validate_passphrase(passphrase)
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    try:
        with source.open("rb") as reader:
            prefix, header = _read_header(reader)
            plaintext_size = int(header["plaintext_size"])
            ciphertext_size = source.stat().st_size - len(prefix) - TAG_LENGTH
            if plaintext_size < 0 or ciphertext_size != plaintext_size:
                raise BackupEncryptionError("Encrypted backup is damaged")
            reader.seek(-TAG_LENGTH, os.SEEK_END)
            tag = reader.read(TAG_LENGTH)
            reader.seek(len(prefix))
            salt = _unb64(header["kdf"]["salt"])
            nonce = _unb64(header["nonce"])
            key = _derive_key(password, salt)
            decryptor = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
            decryptor.authenticate_additional_data(prefix)
            destination.parent.mkdir(parents=True, exist_ok=True)
            remaining = ciphertext_size
            with temporary.open("xb") as writer:
                while remaining:
                    chunk = reader.read(min(CHUNK_SIZE, remaining))
                    if not chunk:
                        raise BackupEncryptionError("Encrypted backup is truncated")
                    remaining -= len(chunk)
                    writer.write(decryptor.update(chunk))
                writer.write(decryptor.finalize())
                writer.flush()
                os.fsync(writer.fileno())
        os.replace(temporary, destination)
        return destination
    except InvalidTag as exc:
        temporary.unlink(missing_ok=True)
        raise BackupEncryptionError(
            "Incorrect passphrase or encrypted backup is damaged"
        ) from exc
    except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as exc:
        temporary.unlink(missing_ok=True)
        if isinstance(exc, BackupEncryptionError):
            raise
        raise BackupEncryptionError("Encrypted backup is invalid or damaged") from exc
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _read_header(reader) -> tuple[bytes, dict]:
    magic = reader.read(len(MAGIC))
    if magic != MAGIC:
        raise BackupEncryptionError("File is not an encrypted SentriFace backup")
    length_bytes = reader.read(4)
    if len(length_bytes) != 4:
        raise BackupEncryptionError("Encrypted backup header is truncated")
    header_length = struct.unpack(">I", length_bytes)[0]
    if header_length <= 0 or header_length > HEADER_LIMIT:
        raise BackupEncryptionError("Encrypted backup header is invalid")
    header_bytes = reader.read(header_length)
    if len(header_bytes) != header_length:
        raise BackupEncryptionError("Encrypted backup header is truncated")
    header = json.loads(header_bytes.decode("utf-8"))
    kdf = header.get("kdf", {})
    expected = (
        header.get("format") == "sentriface-encrypted-backup"
        and header.get("version") == FORMAT_VERSION
        and header.get("cipher") == "AES-256-GCM"
        and header.get("tag_length") == TAG_LENGTH
        and kdf.get("name") == "scrypt"
        and kdf.get("n") == SCRYPT_N
        and kdf.get("r") == SCRYPT_R
        and kdf.get("p") == SCRYPT_P
    )
    if not expected:
        raise BackupEncryptionError("Unsupported encrypted backup format")
    salt = _unb64(kdf["salt"])
    nonce = _unb64(header["nonce"])
    if len(salt) != 16 or len(nonce) != 12:
        raise BackupEncryptionError("Encrypted backup header is invalid")
    return magic + length_bytes + header_bytes, header


def _derive_key(password: bytes, salt: bytes) -> bytes:
    return Scrypt(
        salt=salt,
        length=32,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
    ).derive(password)


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    if not isinstance(value, str):
        raise BackupEncryptionError("Encrypted backup header is invalid")
    return base64.b64decode(
        value + ("=" * (-len(value) % 4)),
        altchars=b"-_",
        validate=True,
    )
