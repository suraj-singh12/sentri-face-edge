from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from sentriface.config import RuntimeConfig
from sentriface.engine import FaceEngine, RecognitionRuntimeSnapshot
from sentriface.errors import ModelSetupError
from sentriface.model_bundle import (
    MODEL_BUNDLE_COMPATIBILITY_VERSION,
    MODEL_BUNDLE_FORMAT_VERSION,
    MODEL_METADATA_LIMIT_BYTES,
    ModelBundle,
    ModelBundleAuthority,
)


MODEL_PREPARATION_VERSION = 1
MODEL_PREPARATION_EXPIRY_SECONDS = 10 * 60
MODEL_ACTIVE_STATE_VERSION = 1
MODEL_RECEIPT_VERSION = 1
_OPERATION_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
_ACTIVE_FIELDS = frozenset({
    "version", "active_bundle_id", "active_fingerprint", "previous_bundle_id",
    "activated_at", "operation_id",
})
_RECEIPT_FIELDS = frozenset({
    "version", "operation_id", "action", "status", "bundle_id",
    "bundle_fingerprint", "previous_bundle_id", "actor_user_id", "actor_username",
    "created_at", "completed_at", "message",
})
_TOKEN_FIELDS = frozenset({
    "version", "action", "bundle_id", "bundle_fingerprint", "active_bundle_id",
    "active_fingerprint", "manifest_version", "compatibility_version",
    "calibration_fingerprint", "usage_fingerprint", "runtime_facts",
    "prepared_at", "expires_at",
})


class ModelActivationRefused(ModelSetupError):
    """A model preparation or activation was stale, unsafe, or conflicting."""


@dataclass(frozen=True)
class PreparedRecognitionRuntime:
    config: RuntimeConfig
    detector: Any
    embedder: Any
    usage: dict[str, object]
    facts: dict[str, object]


@dataclass(frozen=True)
class ActiveModelState:
    active_bundle_id: str
    active_fingerprint: str
    previous_bundle_id: str | None
    activated_at: str
    operation_id: str

    def dto(self) -> dict[str, object]:
        return {
            "active_bundle_id": self.active_bundle_id,
            "active_fingerprint": self.active_fingerprint,
            "previous_bundle_id": self.previous_bundle_id,
            "activated_at": self.activated_at,
        }


class ModelActivationService:
    """Prepare and atomically publish operational recognition bundles only."""

    def __init__(
        self,
        authority: ModelBundleAuthority,
        engine: FaceEngine,
        runtime_factory: Callable[[ModelBundle, RuntimeConfig], PreparedRecognitionRuntime],
        *,
        token_secret: str | bytes,
        now: Callable[[], datetime] | None = None,
        failure_injector: Callable[[str], None] | None = None,
    ) -> None:
        self.authority = authority
        self.engine = engine
        self.runtime_factory = runtime_factory
        self._secret = (
            token_secret.encode("utf-8") if isinstance(token_secret, str) else token_secret
        )
        if len(self._secret) < 16:
            raise ValueError("Model preparation token secret is too short")
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._failure_injector = failure_injector
        self._lock = threading.RLock()
        self.state_path = authority.root / "active.json"
        self.receipts_dir = authority.root / "receipts"

    def bootstrap_legacy_state(self) -> ActiveModelState | None:
        """Adopt a complete old live layout once; never repairs an invalid layout."""
        with self._lock:
            state = self.active_state()
            if state is not None:
                return state
            bundle = self.authority.adopt_legacy_live_bundle()
            if bundle is None:
                return None
            state = ActiveModelState(
                active_bundle_id=bundle.bundle_id,
                active_fingerprint=bundle.fingerprint,
                previous_bundle_id=None,
                activated_at=_utc(self._now()),
                operation_id="legacy-runtime-adoption",
            )
            self._write_active_state(state)
            return state

    def startup_bundle(self) -> ModelBundle | None:
        state = self.active_state()
        if state is None:
            return None
        bundle = self.authority.read_bundle(state.active_bundle_id)
        if bundle.fingerprint != state.active_fingerprint:
            raise ModelSetupError("Active model state does not match its immutable bundle")
        return bundle

    def active_state(self) -> ActiveModelState | None:
        if not self.state_path.exists():
            return None
        payload = _read_json(self.state_path)
        if set(payload) != _ACTIVE_FIELDS or payload.get("version") != MODEL_ACTIVE_STATE_VERSION:
            raise ModelSetupError("Active model state is malformed")
        bundle_id = _opaque_id(payload.get("active_bundle_id"), "active bundle")
        fingerprint = _sha(payload.get("active_fingerprint"), "active bundle fingerprint")
        previous = payload.get("previous_bundle_id")
        if previous is not None:
            previous = _opaque_id(previous, "previous bundle")
            if previous == bundle_id:
                raise ModelSetupError("Active and previous model bundles cannot be identical")
        state = ActiveModelState(
            active_bundle_id=bundle_id,
            active_fingerprint=fingerprint,
            previous_bundle_id=previous,
            activated_at=_bounded(payload.get("activated_at"), "activation timestamp", 100),
            operation_id=_bounded(payload.get("operation_id"), "activation operation", 100),
        )
        bundle = self.authority.read_bundle(bundle_id)
        if bundle.fingerprint != fingerprint:
            raise ModelSetupError("Active model bundle fingerprint changed")
        if previous is not None:
            self.authority.read_bundle(previous)
        return state

    def prepare_model_activation(
        self,
        bundle_id: str,
        *,
        action: str = "ACTIVATE",
    ) -> dict[str, object]:
        normalized_action = action.strip().upper()
        if normalized_action not in {"ACTIVATE", "ROLLBACK"}:
            raise ModelActivationRefused("Model activation action is unsupported")
        with self._lock:
            bundle = self.authority.read_bundle(bundle_id)
            active = self.active_state()
            if active and active.active_bundle_id == bundle.bundle_id:
                raise ModelActivationRefused("The selected model bundle is already active")
            if normalized_action == "ROLLBACK":
                if active is None or active.previous_bundle_id != bundle.bundle_id:
                    raise ModelActivationRefused("Rollback target is not the retained previous bundle")
            runtime = self.runtime_factory(bundle, self.engine.config)
            facts = _validate_runtime_facts(runtime.facts)
            now = self._now()
            payload = {
                "version": MODEL_PREPARATION_VERSION,
                "action": normalized_action,
                "bundle_id": bundle.bundle_id,
                "bundle_fingerprint": bundle.fingerprint,
                "active_bundle_id": active.active_bundle_id if active else None,
                "active_fingerprint": active.active_fingerprint if active else "none",
                "manifest_version": MODEL_BUNDLE_FORMAT_VERSION,
                "compatibility_version": MODEL_BUNDLE_COMPATIBILITY_VERSION,
                "calibration_fingerprint": bundle.components["calibration"]["sha256"],
                "usage_fingerprint": bundle.components["model_usage"]["sha256"],
                "runtime_facts": facts,
                "prepared_at": _utc(now),
                "expires_at": _utc(now + timedelta(seconds=MODEL_PREPARATION_EXPIRY_SECONDS)),
            }
            return {
                "token": self._encode_token(payload),
                "action": normalized_action,
                "bundle": bundle.dto(),
                "current_active": active.dto() if active else None,
                "runtime_facts": facts,
                "expires_at": payload["expires_at"],
                "confirmation_phrase": "ACTIVATE MODEL" if normalized_action == "ACTIVATE" else "ROLL BACK MODEL",
            }

    def prepare_rollback(self) -> dict[str, object]:
        state = self.active_state()
        if state is None or state.previous_bundle_id is None:
            raise ModelActivationRefused("No previous known-good model bundle is retained")
        return self.prepare_model_activation(state.previous_bundle_id, action="ROLLBACK")

    def execute(
        self,
        token: str,
        operation_id: str,
        *,
        actor: dict[str, object] | None,
        reason: str = "",
    ) -> dict[str, object]:
        operation = _operation_id(operation_id)
        payload = self._decode_token(token, check_expiry=False)
        action = str(payload["action"])
        bundle_id = str(payload["bundle_id"])
        actor_user_id, actor_username = _actor(actor)
        _optional_bounded(reason, "activation reason", 500)
        with self._lock:
            existing = self._read_receipt(operation)
            if existing is not None:
                if existing["bundle_id"] != bundle_id or existing["action"] != action:
                    raise ModelActivationRefused("Model activation operation ID has conflicting intent")
                return _receipt_dto(existing, idempotent=True)
            self._require_not_expired(payload)
            bundle = self.authority.read_bundle(bundle_id)
            self._validate_precondition(payload, bundle)
            old_state = self.active_state()
            created_at = _utc(self._now())
            try:
                self._checkpoint("before_runtime_construct")
                runtime = self.runtime_factory(bundle, self.engine.config)
                if _validate_runtime_facts(runtime.facts) != payload["runtime_facts"]:
                    raise ModelActivationRefused("Prepared runtime compatibility facts changed")
                self._checkpoint("after_runtime_construct")
            except Exception as exc:
                failed = _receipt(
                    operation, action, "FAILED", bundle, old_state,
                    actor_user_id, actor_username, created_at, _utc(self._now()),
                    "Recognition runtime activation refused before publication",
                )
                try:
                    self._write_receipt(failed)
                except Exception:
                    pass
                if isinstance(exc, ModelActivationRefused):
                    raise
                raise ModelActivationRefused(
                    "Model activation failed before publication; the current runtime is unchanged"
                ) from exc
            old_snapshot: RecognitionRuntimeSnapshot | None = None
            published = False
            swapped = False
            try:
                new_state = ActiveModelState(
                    active_bundle_id=bundle.bundle_id,
                    active_fingerprint=bundle.fingerprint,
                    previous_bundle_id=(old_state.active_bundle_id if old_state else None),
                    activated_at=created_at,
                    operation_id=operation,
                )
                self._checkpoint("before_publish")
                self._write_active_state(new_state)
                published = True
                self._checkpoint("after_publish")
                old_snapshot = self.engine.replace_recognition_runtime(
                    config=runtime.config,
                    detector=runtime.detector,
                    embedder=runtime.embedder,
                    model_usage=runtime.usage,
                )
                swapped = True
                self._checkpoint("after_runtime_swap")
                receipt = _receipt(
                    operation, action, "COMMITTED", bundle, old_state,
                    actor_user_id, actor_username, created_at, _utc(self._now()),
                    "Recognition runtime activation committed",
                )
                self._checkpoint("before_receipt")
                self._write_receipt(receipt)
                return _receipt_dto(receipt, idempotent=False)
            except Exception as exc:
                rollback_error: Exception | None = None
                try:
                    if swapped and old_snapshot is not None:
                        self.engine.restore_recognition_runtime(old_snapshot)
                    if published:
                        self._restore_active_state(old_state)
                except Exception as rollback_exc:  # pragma: no cover - reported as unsafe.
                    rollback_error = rollback_exc
                if rollback_error is not None:
                    raise ModelActivationRefused(
                        "Model activation failed and operational rollback could not be proven"
                    ) from rollback_error
                failed = _receipt(
                    operation, action, "FAILED", bundle, old_state,
                    actor_user_id, actor_username, created_at, _utc(self._now()),
                    "Recognition runtime activation rolled back",
                )
                try:
                    self._write_receipt(failed)
                except Exception:
                    pass
                if isinstance(exc, ModelActivationRefused):
                    raise
                raise ModelActivationRefused(
                    "Model activation failed; the previous runtime remains active"
                ) from exc

    def _validate_precondition(self, payload: dict[str, object], bundle: ModelBundle) -> None:
        if payload["bundle_fingerprint"] != bundle.fingerprint:
            raise ModelActivationRefused("Prepared model bundle fingerprint changed")
        if payload["manifest_version"] != MODEL_BUNDLE_FORMAT_VERSION:
            raise ModelActivationRefused("Prepared model manifest version changed")
        if payload["compatibility_version"] != MODEL_BUNDLE_COMPATIBILITY_VERSION:
            raise ModelActivationRefused("Prepared model compatibility version changed")
        if payload["calibration_fingerprint"] != bundle.components["calibration"]["sha256"]:
            raise ModelActivationRefused("Prepared calibration fingerprint changed")
        if payload["usage_fingerprint"] != bundle.components["model_usage"]["sha256"]:
            raise ModelActivationRefused("Prepared usage declaration fingerprint changed")
        active = self.active_state()
        active_id = active.active_bundle_id if active else None
        active_fingerprint = active.active_fingerprint if active else "none"
        if payload["active_bundle_id"] != active_id or payload["active_fingerprint"] != active_fingerprint:
            raise ModelActivationRefused("Prepared active model state is stale")
        if payload["action"] == "ROLLBACK" and (
            active is None or active.previous_bundle_id != bundle.bundle_id
        ):
            raise ModelActivationRefused("Prepared rollback target is stale")

    def _write_active_state(self, state: ActiveModelState) -> None:
        payload = {
            "version": MODEL_ACTIVE_STATE_VERSION,
            "active_bundle_id": state.active_bundle_id,
            "active_fingerprint": state.active_fingerprint,
            "previous_bundle_id": state.previous_bundle_id,
            "activated_at": state.activated_at,
            "operation_id": state.operation_id,
        }
        _replace_json(self.state_path, payload)

    def _restore_active_state(self, state: ActiveModelState | None) -> None:
        if state is None:
            self.state_path.unlink(missing_ok=True)
            _fsync_directory(self.state_path.parent)
        else:
            self._write_active_state(state)

    def _read_receipt(self, operation_id: str) -> dict[str, object] | None:
        path = self.receipts_dir / f"{operation_id}.json"
        if not path.exists():
            return None
        payload = _read_json(path)
        if set(payload) != _RECEIPT_FIELDS or payload.get("version") != MODEL_RECEIPT_VERSION:
            raise ModelActivationRefused("Model activation receipt is malformed")
        return payload

    def _write_receipt(self, payload: dict[str, object]) -> None:
        self.receipts_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = self.receipts_dir / f"{payload['operation_id']}.json"
        if path.exists():
            existing = _read_json(path)
            if existing != payload:
                raise ModelActivationRefused("Model activation receipt conflicts")
            return
        _write_json_exclusive(path, payload)
        _fsync_directory(path.parent)

    def _encode_token(self, payload: dict[str, object]) -> str:
        body = _canonical(payload)
        encoded = base64.urlsafe_b64encode(body).rstrip(b"=").decode("ascii")
        signature = hmac.new(self._secret, body, hashlib.sha256).hexdigest()
        return f"{encoded}.{signature}"

    def _decode_token(self, token: str, *, check_expiry: bool) -> dict[str, object]:
        if not isinstance(token, str) or len(token) > 16_000 or token.count(".") != 1:
            raise ModelActivationRefused("Model preparation token is malformed")
        encoded, supplied_signature = token.split(".", 1)
        try:
            padding = "=" * (-len(encoded) % 4)
            body = base64.urlsafe_b64decode(encoded + padding)
            payload = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ModelActivationRefused("Model preparation token is malformed") from exc
        expected = hmac.new(self._secret, body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, supplied_signature):
            raise ModelActivationRefused("Model preparation token signature is invalid")
        if not isinstance(payload, dict) or set(payload) != _TOKEN_FIELDS:
            raise ModelActivationRefused("Model preparation token fields are unsupported")
        if payload.get("version") != MODEL_PREPARATION_VERSION:
            raise ModelActivationRefused("Model preparation token version is unsupported")
        _opaque_id(payload.get("bundle_id"), "prepared bundle")
        _sha(payload.get("bundle_fingerprint"), "prepared bundle fingerprint")
        _sha(payload.get("calibration_fingerprint"), "prepared calibration fingerprint")
        _sha(payload.get("usage_fingerprint"), "prepared usage fingerprint")
        active_id = payload.get("active_bundle_id")
        if active_id is not None:
            _opaque_id(active_id, "prepared active bundle")
        if payload.get("active_fingerprint") != "none":
            _sha(payload.get("active_fingerprint"), "prepared active fingerprint")
        payload["runtime_facts"] = _validate_runtime_facts(payload.get("runtime_facts"))
        if check_expiry:
            self._require_not_expired(payload)
        return payload

    def _require_not_expired(self, payload: dict[str, object]) -> None:
        try:
            expires = datetime.fromisoformat(str(payload.get("expires_at") or ""))
        except ValueError as exc:
            raise ModelActivationRefused("Model preparation token expiry is malformed") from exc
        if expires <= self._now():
            raise ModelActivationRefused("Model preparation token expired")

    def _checkpoint(self, name: str) -> None:
        if self._failure_injector is not None:
            self._failure_injector(name)


def resolve_startup_model_bundle(
    authority: ModelBundleAuthority,
    *,
    now: Callable[[], datetime] | None = None,
) -> ModelBundle | None:
    """Resolve or adopt active operational model state before engine construction."""
    clock = now or (lambda: datetime.now(timezone.utc))
    state_path = authority.root / "active.json"
    if not state_path.exists():
        bundle = authority.adopt_legacy_live_bundle()
        if bundle is None:
            return None
        _replace_json(state_path, {
            "version": MODEL_ACTIVE_STATE_VERSION,
            "active_bundle_id": bundle.bundle_id,
            "active_fingerprint": bundle.fingerprint,
            "previous_bundle_id": None,
            "activated_at": _utc(clock()),
            "operation_id": "legacy-runtime-adoption",
        })
        return bundle
    payload = _read_json(state_path)
    if set(payload) != _ACTIVE_FIELDS or payload.get("version") != MODEL_ACTIVE_STATE_VERSION:
        raise ModelSetupError("Active model state is malformed")
    bundle_id = _opaque_id(payload.get("active_bundle_id"), "active bundle")
    fingerprint = _sha(payload.get("active_fingerprint"), "active bundle fingerprint")
    previous = payload.get("previous_bundle_id")
    if previous is not None:
        previous = _opaque_id(previous, "previous bundle")
        if previous == bundle_id:
            raise ModelSetupError("Active and previous model bundles cannot be identical")
        authority.read_bundle(previous)
    bundle = authority.read_bundle(bundle_id)
    if bundle.fingerprint != fingerprint:
        raise ModelSetupError("Active model bundle fingerprint changed")
    return bundle


def _validate_runtime_facts(value: object) -> dict[str, object]:
    required = {
        "runtime", "provider", "detector_input", "detector_outputs",
        "recognizer_input", "embedding_dimension", "calibration_valid",
        "usage_valid", "compatible",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ModelActivationRefused("Runtime compatibility facts are incomplete")
    facts = dict(value)
    if facts["runtime"] != "onnxruntime-cpu" or facts["provider"] != "CPUExecutionProvider":
        raise ModelActivationRefused("Model runtime provider is unsupported")
    if facts["embedding_dimension"] != 512:
        raise ModelActivationRefused("Recognizer must produce 512-dimensional embeddings")
    if any(facts[key] is not True for key in ("calibration_valid", "usage_valid", "compatible")):
        raise ModelActivationRefused("Model runtime compatibility validation failed")
    for key in ("detector_input", "recognizer_input"):
        shape = facts[key]
        if not isinstance(shape, list) or len(shape) != 4 or len(json.dumps(shape)) > 200:
            raise ModelActivationRefused("Model input contract is unsupported")
    if not isinstance(facts["detector_outputs"], int) or facts["detector_outputs"] <= 0:
        raise ModelActivationRefused("Detector output contract is unsupported")
    return facts


def _receipt(
    operation_id: str,
    action: str,
    status: str,
    bundle: ModelBundle,
    old_state: ActiveModelState | None,
    actor_user_id: str,
    actor_username: str,
    created_at: str,
    completed_at: str,
    message: str,
) -> dict[str, object]:
    return {
        "version": MODEL_RECEIPT_VERSION,
        "operation_id": operation_id,
        "action": action,
        "status": status,
        "bundle_id": bundle.bundle_id,
        "bundle_fingerprint": bundle.fingerprint,
        "previous_bundle_id": old_state.active_bundle_id if old_state else None,
        "actor_user_id": actor_user_id,
        "actor_username": actor_username,
        "created_at": created_at,
        "completed_at": completed_at,
        "message": message,
    }


def _receipt_dto(payload: dict[str, object], *, idempotent: bool) -> dict[str, object]:
    return {
        "operation_id": payload["operation_id"],
        "action": payload["action"],
        "status": payload["status"],
        "committed": payload["status"] == "COMMITTED",
        "bundle_id": payload["bundle_id"],
        "bundle_fingerprint": payload["bundle_fingerprint"],
        "previous_bundle_id": payload["previous_bundle_id"],
        "completed_at": payload["completed_at"],
        "message": payload["message"],
        "idempotent": idempotent,
    }


def _actor(actor: dict[str, object] | None) -> tuple[str, str]:
    if not isinstance(actor, dict):
        raise ModelActivationRefused("Authenticated administrator actor is required")
    try:
        return (
            _bounded(actor.get("user_id"), "actor user ID", 200),
            _bounded(actor.get("username"), "actor username", 100),
        )
    except ModelSetupError as exc:
        raise ModelActivationRefused(
            "Authenticated administrator actor is invalid"
        ) from exc


def _operation_id(value: str) -> str:
    normalized = str(value or "").strip().casefold()
    if not _OPERATION_ID.fullmatch(normalized):
        raise ModelActivationRefused("Model activation operation ID must be a UUID")
    return normalized


def _opaque_id(value: object, label: str) -> str:
    normalized = str(value or "").strip().casefold()
    if len(normalized) != 32 or any(char not in "0123456789abcdef" for char in normalized):
        raise ModelSetupError(f"Model {label} ID is invalid")
    return normalized


def _sha(value: object, label: str) -> str:
    normalized = str(value or "").strip().casefold()
    if len(normalized) != 64 or any(char not in "0123456789abcdef" for char in normalized):
        raise ModelSetupError(f"Model {label} is invalid")
    return normalized


def _bounded(value: object, label: str, maximum: int) -> str:
    text = str(value or "").strip()
    if not text or len(text) > maximum or any(ord(char) < 32 for char in text):
        raise ModelSetupError(f"Model {label} is invalid")
    return text


def _optional_bounded(value: object, label: str, maximum: int) -> str:
    text = str(value or "").strip()
    if len(text) > maximum or any(ord(char) < 32 for char in text):
        raise ModelSetupError(f"Model {label} is invalid")
    return text


def _read_json(path: Path) -> dict[str, object]:
    try:
        if path.is_symlink() or path.stat().st_size > MODEL_METADATA_LIMIT_BYTES:
            raise ModelSetupError("Model operational metadata is unsafe")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except ModelSetupError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelSetupError("Model operational metadata is malformed") from exc
    if not isinstance(payload, dict):
        raise ModelSetupError("Model operational metadata must be an object")
    return payload


def _replace_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        _write_json_exclusive(temporary, payload)
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _write_json_exclusive(path: Path, payload: dict[str, object]) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as output:
        json.dump(payload, output, indent=2, sort_keys=True)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _canonical(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()
