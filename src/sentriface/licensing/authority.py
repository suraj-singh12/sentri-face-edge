from __future__ import annotations

import base64
import binascii
import json
import re
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .fingerprint import MachineFingerprintError, windows_machine_fingerprint
from .public_keys import production_public_keys


TOKEN_PREFIX = "SFE2"
MAX_TOKEN_BYTES = 16_384
MAX_REGISTRY_TOKEN_CHARS = MAX_TOKEN_BYTES
REGISTRY_PATH = r"Software\SentriFaceEdge\Licensing\v2"
REGISTRY_VALUE = "LicenseToken"
ALLOWED_FIELDS = frozenset({
    "version", "product", "license_id", "key_id", "machine", "edition",
    "license_type", "issued_at", "expires_at",
})
_B64URL = re.compile(r"^[A-Za-z0-9_-]+$")
_BOUNDED_LABEL = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")


class LicenseStatus(str, Enum):
    LICENSED = "licensed"
    UNLICENSED = "unlicensed"
    INVALID = "invalid"
    EXPIRED = "expired"
    UNAVAILABLE = "unavailable"
    NOT_ENFORCED = "not_enforced"


@dataclass(frozen=True)
class LicenseResult:
    status: LicenseStatus
    code: str
    message: str
    machine_id: str | None = None
    license_id: str | None = None
    edition: str | None = None
    license_type: str | None = None
    issued_at: str | None = None
    expires_at: str | None = None

    @property
    def licensed(self) -> bool:
        return self.status == LicenseStatus.LICENSED

    def as_dict(self, *, enforced: bool) -> dict[str, Any]:
        return {
            "format_version": 2,
            "enforced": bool(enforced),
            "licensed": self.licensed,
            "status": self.status.value,
            "code": self.code,
            "message": self.message,
            "machine_id": self.machine_id,
            "license": None if not self.licensed else {
                "license_id": self.license_id,
                "edition": self.edition,
                "license_type": self.license_type,
                "issued_at": self.issued_at,
                "expires_at": self.expires_at,
            },
        }


class LicenseStoreError(RuntimeError):
    pass


class LicenseStore(Protocol):
    def load(self) -> str | None: ...
    def save(self, token: str) -> None: ...


class MemoryLicenseStore:
    def __init__(self, token: str | None = None) -> None:
        self.token = token

    def load(self) -> str | None:
        return self.token

    def save(self, token: str) -> None:
        self.token = token


class WindowsRegistryLicenseStore:
    def load(self) -> str | None:
        if sys.platform != "win32":
            return None
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_PATH, 0, winreg.KEY_READ) as key:
                value, value_type = winreg.QueryValueEx(key, REGISTRY_VALUE)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise LicenseStoreError("Stored license state could not be read") from exc
        if value_type != winreg.REG_SZ or not isinstance(value, str):
            raise LicenseStoreError("Stored license state has an invalid registry type")
        if not value or len(value) > MAX_REGISTRY_TOKEN_CHARS:
            raise LicenseStoreError("Stored license state is malformed")
        return value

    def save(self, token: str) -> None:
        if sys.platform != "win32":
            raise LicenseStoreError("License persistence is available only on Windows")
        if not isinstance(token, str) or not token or len(token) > MAX_REGISTRY_TOKEN_CHARS:
            raise LicenseStoreError("License token exceeds the persistence boundary")
        import winreg
        try:
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, REGISTRY_PATH, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, REGISTRY_VALUE, 0, winreg.REG_SZ, token)
        except OSError as exc:
            raise LicenseStoreError("Verified license state could not be stored") from exc


class _DuplicateField(ValueError):
    pass


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateField(key)
        result[key] = value
    return result


def canonical_payload(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _decode_segment(value: str, *, maximum: int) -> bytes:
    if not value or len(value) > maximum or not _B64URL.fullmatch(value) or "=" in value:
        raise ValueError("invalid_base64url")
    try:
        raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("invalid_base64url") from exc
    if base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii") != value:
        raise ValueError("noncanonical_base64url")
    return raw


def _timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or len(value) > 40 or not value.endswith("Z"):
        raise ValueError(f"invalid_{field}")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(f"invalid_{field}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"invalid_{field}")
    return parsed.astimezone(timezone.utc)


class LicenseAuthority:
    def __init__(
        self,
        *,
        public_keys: dict[str, bytes] | None = None,
        store: LicenseStore | None = None,
        machine_id_provider=windows_machine_fingerprint,
        enforced: bool = True,
        clock=lambda: datetime.now(timezone.utc),
    ) -> None:
        self.public_keys = dict(public_keys or production_public_keys())
        self.store = store or WindowsRegistryLicenseStore()
        self.machine_id_provider = machine_id_provider
        self.enforced = bool(enforced)
        self.clock = clock

    def status(self) -> LicenseResult:
        if not self.enforced:
            return LicenseResult(LicenseStatus.NOT_ENFORCED, "license_not_enforced", "Licensing is not enforced in this source runtime")
        machine = self._machine_result()
        if isinstance(machine, LicenseResult):
            return machine
        try:
            token = self.store.load()
        except LicenseStoreError:
            return LicenseResult(LicenseStatus.INVALID, "stored_license_invalid", "Stored license state is invalid", machine_id=machine)
        if token is None:
            return LicenseResult(LicenseStatus.UNLICENSED, "license_required", "SentriFace Edge is not activated", machine_id=machine)
        return self.verify(token, machine_id=machine)

    def activate(self, token: str) -> LicenseResult:
        machine = self._machine_result()
        if isinstance(machine, LicenseResult):
            return machine
        result = self.verify(token, machine_id=machine)
        if not result.licensed:
            return result
        try:
            self.store.save(token)
        except LicenseStoreError:
            return LicenseResult(LicenseStatus.INVALID, "license_persistence_failed", "The verified license could not be stored", machine_id=machine)
        return result

    def verify(self, token: str, *, machine_id: str | None = None) -> LicenseResult:
        machine = machine_id
        if machine is None:
            resolved = self._machine_result()
            if isinstance(resolved, LicenseResult):
                return resolved
            machine = resolved
        if not isinstance(token, str) or not token or len(token.encode("utf-8", "ignore")) > MAX_TOKEN_BYTES:
            return self._refusal("license_token_oversized" if isinstance(token, str) and token else "license_token_malformed", machine)
        parts = token.split(".")
        if len(parts) != 3 or parts[0] != TOKEN_PREFIX:
            return self._refusal("license_token_malformed", machine)
        try:
            payload_bytes = _decode_segment(parts[1], maximum=MAX_TOKEN_BYTES)
            signature = _decode_segment(parts[2], maximum=128)
            if len(signature) != 64:
                raise ValueError("invalid_signature_length")
            payload = json.loads(payload_bytes.decode("ascii"), object_pairs_hook=_strict_object)
            if not isinstance(payload, dict) or canonical_payload(payload) != payload_bytes:
                raise ValueError("noncanonical_payload")
        except (_DuplicateField, UnicodeError, json.JSONDecodeError, ValueError):
            return self._refusal("license_token_malformed", machine)
        if set(payload) != ALLOWED_FIELDS:
            return self._refusal("license_claims_invalid", machine)
        key_id = payload.get("key_id")
        if not isinstance(key_id, str) or key_id not in self.public_keys:
            return self._refusal("license_key_unknown", machine)
        try:
            Ed25519PublicKey.from_public_bytes(self.public_keys[key_id]).verify(signature, payload_bytes)
        except (InvalidSignature, ValueError):
            return self._refusal("license_signature_invalid", machine)
        try:
            if type(payload["version"]) is not int or payload["version"] != 2:
                return self._refusal("license_version_unsupported", machine)
            if payload["product"] != "SentriFaceEdge":
                return self._refusal("license_product_mismatch", machine)
            license_id = str(uuid.UUID(payload["license_id"]))
            if license_id != payload["license_id"]:
                raise ValueError("invalid_license_id")
            if payload["machine"] != machine:
                return self._refusal("license_machine_mismatch", machine)
            edition = payload["edition"]
            license_type = payload["license_type"]
            if not isinstance(edition, str) or not _BOUNDED_LABEL.fullmatch(edition):
                raise ValueError("invalid_edition")
            if license_type not in {"perpetual", "subscription", "evaluation"}:
                raise ValueError("invalid_license_type")
            issued = _timestamp(payload["issued_at"], "issued_at")
            expires_raw = payload["expires_at"]
            expires = None if expires_raw is None else _timestamp(expires_raw, "expires_at")
            if license_type == "perpetual" and expires is not None:
                raise ValueError("invalid_expiry")
            if license_type != "perpetual" and expires is None:
                raise ValueError("missing_expiry")
            now = self.clock().astimezone(timezone.utc)
            if issued > now:
                return self._refusal("license_not_yet_valid", machine)
            if expires is not None and expires <= max(now, issued):
                return LicenseResult(LicenseStatus.EXPIRED, "license_expired", "The license has expired", machine_id=machine)
        except (KeyError, TypeError, ValueError, AttributeError):
            return self._refusal("license_claims_invalid", machine)
        return LicenseResult(
            LicenseStatus.LICENSED, "licensed", "SentriFace Edge is activated",
            machine_id=machine, license_id=license_id, edition=edition,
            license_type=license_type, issued_at=payload["issued_at"], expires_at=expires_raw,
        )

    def _machine_result(self) -> str | LicenseResult:
        try:
            return self.machine_id_provider()
        except MachineFingerprintError:
            return LicenseResult(LicenseStatus.UNAVAILABLE, "machine_identity_unavailable", "Windows machine identity is unavailable")

    @staticmethod
    def _refusal(code: str, machine: str) -> LicenseResult:
        messages = {
            "license_machine_mismatch": "The license was issued for a different Windows installation",
            "license_key_unknown": "The license uses an unknown verification key",
            "license_signature_invalid": "The license signature is invalid",
            "license_not_yet_valid": "The license is not yet valid",
            "license_product_mismatch": "The license was issued for a different product",
            "license_version_unsupported": "The license format version is unsupported",
        }
        return LicenseResult(LicenseStatus.INVALID, code, messages.get(code, "The license is invalid"), machine_id=machine)


def packaged_windows_license_enforced() -> bool:
    return sys.platform == "win32" and (bool(getattr(sys, "frozen", False)) or "__compiled__" in globals())
