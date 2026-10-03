from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import stat
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from sentriface.backup_service import BackupRecord, BackupService


RECOVERY_SERVICE = "SentriFace Edge disaster recovery"
RECOVERY_KIT_NAME = "sentriface-recovery-kit.json"
SETTINGS_NAME = "recovery-settings.json"
LINUX_SOURCE_RECOVERY_NAME = ".sentriface-linux-source-recovery"
SCRYPT_N = 2**15
SCRYPT_R = 8
SCRYPT_P = 1


class RecoveryError(RuntimeError):
    """Raised when disaster recovery cannot proceed safely."""


def available_recovery_destinations() -> list[dict[str, str]]:
    """Return simple local-drive choices without exposing the live data drive."""
    candidates: list[Path] = []
    if os.name == "nt":
        import ctypes

        system_drive = Path(os.environ.get("SystemDrive", "C:")).drive.casefold()
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        for index in range(26):
            if not bitmask & (1 << index):
                continue
            root = Path(f"{chr(65 + index)}:\\")
            drive_type = ctypes.windll.kernel32.GetDriveTypeW(str(root))
            if drive_type in {2, 3} and root.drive.casefold() != system_drive:
                candidates.append(root)
    elif sys.platform == "darwin":
        volume_root = Path("/Volumes")
        candidates.extend(volume_root.iterdir() if volume_root.is_dir() else [])
    else:
        user = os.environ.get("USER", "")
        for root in (Path("/media") / user, Path("/run/media") / user, Path("/mnt")):
            candidates.extend(root.iterdir() if root.is_dir() else [])

    choices: list[dict[str, str]] = []
    seen: set[str] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
            identity = str(resolved).casefold()
            if resolved == Path("/").resolve() or identity in seen or not candidate.is_dir():
                continue
            if not os.access(candidate, os.W_OK):
                continue
        except OSError:
            continue
        seen.add(identity)
        choices.append({
            "label": candidate.name or str(candidate),
            "path": str(candidate / "SentriFace Backup"),
        })
    return sorted(choices, key=lambda item: item["label"].casefold())


def _require_local_destination(destination: Path) -> None:
    """Reject recovery targets that are visibly backed by a network share."""
    raw = str(destination)
    if raw.startswith(("\\\\", "//")):
        raise RecoveryError("Disaster recovery destination must be a local or removable drive")
    if os.name == "nt" and destination.drive:
        import ctypes

        drive_type = ctypes.windll.kernel32.GetDriveTypeW(f"{destination.drive}\\")
        if drive_type == 4:  # DRIVE_REMOTE
            raise RecoveryError("Disaster recovery destination must not be a network drive")


class RecoveryService:
    def __init__(self, data_dir: Path, master_key: bytes, backups: BackupService, *, linux_source_onnx: bool = False) -> None:
        self.data_dir = data_dir
        self.master_key = master_key
        self.backups = backups
        self.settings_path = data_dir / SETTINGS_NAME
        self.linux_source_onnx = linux_source_onnx
        if linux_source_onnx:
            self._source_root()

    def _source_root(self) -> Path:
        from sentriface.secure_storage import _linux_source_authority, load_linux_source_master_key, StorageSecurityError
        root = _linux_source_authority(self.data_dir, explicit_source_onnx=self.linux_source_onnx)
        try:
            key = load_linux_source_master_key(root, explicit_source_onnx=True)
        except StorageSecurityError:
            raise RecoveryError("Source recovery authority could not be authenticated") from None
        if not secrets.compare_digest(key, self.master_key):
            raise RecoveryError("Source recovery custody does not match authority")
        return root

    def _load_code(self) -> str | None:
        if not self.linux_source_onnx:
            return _load_recovery_code(self.data_dir)
        from sentriface.secure_files import is_protected_file, read_protected_bytes
        root = self._source_root()
        path = root / LINUX_SOURCE_RECOVERY_NAME
        if not path.exists() and not path.is_symlink():
            if self._read_settings().get("destination"):
                raise RecoveryError("Source recovery secret is missing for configured authority")
            return None
        try:
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_nlink != 1:
                raise ValueError("unsafe custody")
            if not is_protected_file(path):
                raise ValueError("unprotected custody")
            record = json.loads(read_protected_bytes(path, self.master_key))
            code = record["code"]
            if record.get("authority") != _account(root) or not isinstance(code, str) or (not code.startswith("SF1-") or len(code) != 47):
                raise ValueError("invalid custody")
            return code
        except Exception:
            raise RecoveryError("Source recovery custody is invalid or belongs to another authority") from None

    def _store_code(self, code: str) -> None:
        if not self.linux_source_onnx:
            _store_recovery_code(self.data_dir, code)
            return
        from sentriface.secure_files import write_protected_bytes
        root = self._source_root()
        path = root / LINUX_SOURCE_RECOVERY_NAME
        # Secure staging keeps even temporary encrypted custody owner-only.
        temporary = root / f".{LINUX_SOURCE_RECOVERY_NAME}.{uuid.uuid4().hex}"
        try:
            fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            os.close(fd)
            write_protected_bytes(temporary, json.dumps({"authority": _account(root), "code": code}).encode(), self.master_key, mode=0o600)
            temporary.chmod(0o600)
            os.replace(temporary, path)
            directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            temporary.unlink(missing_ok=True)

    def configure(self, destination: Path) -> dict[str, object]:
        _require_local_destination(destination)
        destination = destination.expanduser().resolve()
        data_root = self.data_dir.resolve()
        if destination == data_root or data_root in destination.parents:
            raise RecoveryError("Disaster recovery destination must be outside the SentriFace data directory")
        destination.mkdir(parents=True, exist_ok=True)
        # A configured but missing/corrupt secret is a recovery failure, not
        # permission to silently rotate it and orphan the existing recovery kit.
        if self.linux_source_onnx:
            self._read_settings()
            self._load_code()
        code = _new_recovery_code()
        self._store_code(code)
        _write_recovery_kit(destination / RECOVERY_KIT_NAME, self.master_key, code)
        self._write_settings({
            "destination": str(destination),
            "configured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
        return {**self.status(), "recovery_code": code}

    def status(self) -> dict[str, object]:
        settings = self._read_settings()
        destination_value = str(settings.get("destination") or "")
        destination = Path(destination_value) if destination_value else None
        exports = sorted(destination.glob("*.sfbackup.enc"), key=lambda path: path.stat().st_mtime, reverse=True) if destination and destination.is_dir() else []
        return {
            "configured": bool(destination_value and self._load_code()),
            "destination": destination_value,
            "destination_available": bool(destination and destination.is_dir()),
            "recovery_kit_present": bool(destination and (destination / RECOVERY_KIT_NAME).is_file()),
            "last_external_backup": datetime.fromtimestamp(exports[0].stat().st_mtime, timezone.utc).isoformat(timespec="seconds") if exports else "",
            "last_external_backup_path": str(exports[0]) if exports else "",
            "external_backup_count": len(exports),
            "external_retention_limit": self.backups.retention_limit,
        }

    def automatic_backup_if_due(self, interval_hours: int = 24) -> BackupRecord | None:
        status = self.status()
        if not status["configured"] or not status["destination_available"] or not status["recovery_kit_present"]:
            return None
        last = str(status["last_external_backup"] or "")
        if last:
            created = datetime.fromisoformat(last)
            if datetime.now(timezone.utc) - created < timedelta(hours=max(1, interval_hours)):
                return None
        destination = Path(str(status["destination"]))
        code = self._load_code()
        if not code:
            raise RecoveryError("Automatic recovery backup key is unavailable from the OS vault")
        backup = self.backups.create_backup(reason="automatic-recovery")
        target = destination / f"{backup.backup_id}.sfbackup.enc"
        self.backups.export_encrypted_backup(backup.backup_id, target, code)
        self._prune_external_backups(destination)
        return backup

    def _prune_external_backups(self, destination: Path) -> None:
        exports = sorted(
            destination.glob("*.sfbackup.enc"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for obsolete in exports[max(1, self.backups.retention_limit):]:
            obsolete.unlink(missing_ok=True)

    def _read_settings(self) -> dict[str, object]:
        try:
            payload = json.loads(self.settings_path.read_text(encoding="utf-8"))
            if self.linux_source_onnx and (not isinstance(payload, dict) or not isinstance(payload.get("destination"), str) or not payload["destination"]):
                raise RecoveryError("Source recovery settings are invalid")
            return payload if isinstance(payload, dict) else {}
        except FileNotFoundError:
            return {}
        except (OSError, json.JSONDecodeError):
            if self.linux_source_onnx:
                raise RecoveryError("Source recovery settings could not be read safely") from None
            return {}

    def _write_settings(self, payload: dict[str, object]) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.settings_path.with_name(f".{SETTINGS_NAME}.{uuid.uuid4().hex}.tmp")
        try:
            with temporary.open("x", encoding="utf-8") as output:
                json.dump(payload, output, indent=2, sort_keys=True)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.settings_path)
        finally:
            temporary.unlink(missing_ok=True)


def recover_master_key(kit_path: Path, recovery_code: str) -> bytes:
    try:
        payload = json.loads(kit_path.read_text(encoding="utf-8"))
        salt = _unb64(payload["salt"])
        nonce = _unb64(payload["nonce"])
        wrapped = _unb64(payload["wrapped_master_key"])
        key = AESGCM(_derive_recovery_key(recovery_code, salt)).decrypt(nonce, wrapped, b"sentriface-recovery-kit-v1")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError, InvalidTag) as exc:
        raise RecoveryError("Recovery code is incorrect or the recovery kit is damaged") from exc
    if len(key) != 32:
        raise RecoveryError("Recovery kit contains an invalid storage key")
    return key


def _write_recovery_kit(path: Path, master_key: bytes, recovery_code: str) -> None:
    salt = os.urandom(16)
    nonce = os.urandom(12)
    wrapped = AESGCM(_derive_recovery_key(recovery_code, salt)).encrypt(nonce, master_key, b"sentriface-recovery-kit-v1")
    payload = {
        "format": "sentriface-recovery-kit",
        "version": 1,
        "kdf": "scrypt",
        "n": SCRYPT_N,
        "r": SCRYPT_R,
        "p": SCRYPT_P,
        "salt": _b64(salt),
        "nonce": _b64(nonce),
        "wrapped_master_key": _b64(wrapped),
    }
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as output:
            json.dump(payload, output, indent=2, sort_keys=True)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _derive_recovery_key(code: str, salt: bytes) -> bytes:
    if not isinstance(code, str) or len(code) < 32:
        raise RecoveryError("Recovery code is invalid")
    return Scrypt(salt=salt, length=32, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P).derive(code.encode("utf-8"))


def _new_recovery_code() -> str:
    return "SF1-" + secrets.token_urlsafe(32)


def _account(data_dir: Path) -> str:
    return hashlib.sha256(str(data_dir.resolve()).casefold().encode("utf-8")).hexdigest()


def _store_recovery_code(data_dir: Path, code: str) -> None:
    try:
        import keyring
        keyring.set_password(RECOVERY_SERVICE, _account(data_dir), code)
    except Exception as exc:
        raise RecoveryError(f"Recovery code could not be stored in the OS vault: {exc}") from exc


def _load_recovery_code(data_dir: Path) -> str | None:
    try:
        import keyring
        return keyring.get_password(RECOVERY_SERVICE, _account(data_dir))
    except Exception as exc:
        raise RecoveryError(f"Recovery code could not be read from the OS vault: {exc}") from exc


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + ("=" * (-len(value) % 4)))
