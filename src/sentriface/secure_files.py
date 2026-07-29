from __future__ import annotations

import json
import os
import struct
import uuid
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


MAGIC = b"SENTRIFACE-PROTECTED-FILE\n"
FORMAT_VERSION = 1
HEADER_LIMIT = 2048
TAG_LENGTH = 16
CHUNK_SIZE = 1024 * 1024


class ProtectedFileError(RuntimeError):
    """Raised when a managed encrypted file is invalid or cannot be authenticated."""


def is_protected_file(path: Path) -> bool:
    try:
        with path.open("rb") as source:
            return source.read(len(MAGIC)) == MAGIC
    except OSError:
        return False


def write_protected_bytes(path: Path, data: bytes, key: bytes | None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if key is None:
        _atomic_write(path, data)
        return path
    nonce = os.urandom(12)
    header = _header(nonce, len(data))
    prefix = MAGIC + struct.pack(">I", len(header)) + header
    encryptor = Cipher(algorithms.AES(_validate_key(key)), modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(prefix)
    ciphertext = encryptor.update(data) + encryptor.finalize()
    _atomic_write(path, prefix + ciphertext + encryptor.tag)
    return path


def read_protected_bytes(path: Path, key: bytes | None) -> bytes:
    if not is_protected_file(path):
        return path.read_bytes()
    if key is None:
        raise ProtectedFileError("This managed file requires the SentriFace storage key")
    with path.open("rb") as source:
        prefix, header = _read_header(source)
        plaintext_size = int(header["plaintext_size"])
        ciphertext_size = path.stat().st_size - len(prefix) - TAG_LENGTH
        if plaintext_size < 0 or ciphertext_size != plaintext_size:
            raise ProtectedFileError("Managed encrypted file has an invalid size")
        source.seek(-TAG_LENGTH, os.SEEK_END)
        tag = source.read(TAG_LENGTH)
        source.seek(len(prefix))
        ciphertext = source.read(ciphertext_size)
    try:
        decryptor = Cipher(
            algorithms.AES(_validate_key(key)),
            modes.GCM(_decode_hex(header["nonce"], 12), tag),
        ).decryptor()
        decryptor.authenticate_additional_data(prefix)
        plaintext = decryptor.update(ciphertext) + decryptor.finalize()
    except InvalidTag as exc:
        raise ProtectedFileError("Managed encrypted file failed authentication") from exc
    if len(plaintext) != plaintext_size:
        raise ProtectedFileError("Managed encrypted file is truncated")
    return plaintext


def copy_into_protected_storage(source: Path, destination: Path, key: bytes | None) -> Path:
    """Copy a file, encrypting plaintext when a storage key is configured."""
    if key is None or is_protected_file(source):
        _atomic_copy(source, destination)
        return destination
    nonce = os.urandom(12)
    plaintext_size = source.stat().st_size
    header = _header(nonce, plaintext_size)
    prefix = MAGIC + struct.pack(">I", len(header)) + header
    encryptor = Cipher(algorithms.AES(_validate_key(key)), modes.GCM(nonce)).encryptor()
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


def _header(nonce: bytes, plaintext_size: int) -> bytes:
    return json.dumps({
        "cipher": "AES-256-GCM",
        "format": "sentriface-protected-file",
        "nonce": nonce.hex(),
        "plaintext_size": plaintext_size,
        "tag_length": TAG_LENGTH,
        "version": FORMAT_VERSION,
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _read_header(source) -> tuple[bytes, dict]:
    magic = source.read(len(MAGIC))
    if magic != MAGIC:
        raise ProtectedFileError("File is not a managed encrypted file")
    length_bytes = source.read(4)
    if len(length_bytes) != 4:
        raise ProtectedFileError("Managed encrypted file header is truncated")
    header_length = struct.unpack(">I", length_bytes)[0]
    if not 0 < header_length <= HEADER_LIMIT:
        raise ProtectedFileError("Managed encrypted file header is invalid")
    header_bytes = source.read(header_length)
    if len(header_bytes) != header_length:
        raise ProtectedFileError("Managed encrypted file header is truncated")
    try:
        header = json.loads(header_bytes.decode("utf-8"))
        valid = (
            header.get("format") == "sentriface-protected-file"
            and header.get("version") == FORMAT_VERSION
            and header.get("cipher") == "AES-256-GCM"
            and header.get("tag_length") == TAG_LENGTH
        )
        if not valid:
            raise ProtectedFileError("Unsupported managed encrypted file format")
        _decode_hex(header["nonce"], 12)
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtectedFileError("Managed encrypted file header is invalid") from exc
    return magic + length_bytes + header_bytes, header


def _atomic_write(path: Path, data: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    try:
        with source.open("rb") as reader, temporary.open("xb") as writer:
            for chunk in iter(lambda: reader.read(CHUNK_SIZE), b""):
                writer.write(chunk)
            writer.flush()
            os.fsync(writer.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _validate_key(key: bytes) -> bytes:
    if not isinstance(key, bytes) or len(key) != 32:
        raise ProtectedFileError("SentriFace file keys must be 256 bits")
    return key


def _decode_hex(value: str, expected_length: int) -> bytes:
    decoded = bytes.fromhex(value)
    if len(decoded) != expected_length:
        raise ValueError("invalid encoded length")
    return decoded
