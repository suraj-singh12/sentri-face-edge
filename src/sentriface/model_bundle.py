from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from sentriface.errors import ModelSetupError
from sentriface.model_setup import (
    CALIBRATION_FILENAME,
    MODEL_FILENAMES,
    MODEL_USAGE_FILENAME,
    install_local_model_bundle,
    load_similarity_calibration,
    require_model_usage_declaration,
    verify_file,
)


MODEL_BUNDLE_FORMAT = "sentriface-model-bundle"
MODEL_BUNDLE_FORMAT_VERSION = 1
MODEL_BUNDLE_COMPATIBILITY_VERSION = 1
MODEL_BUNDLE_ROOT_NAME = ".model-authority"
MODEL_UPLOAD_EXPIRY_SECONDS = 30 * 60
MODEL_STAGING_EXPIRY_SECONDS = 60 * 60
MODEL_COMPONENT_LIMIT_BYTES = 2_000_000_000
CALIBRATION_LIMIT_BYTES = 1_000_000
MODEL_METADATA_LIMIT_BYTES = 1_000_000

_UPLOAD_KINDS = frozenset({"detector", "recognizer", "calibration"})
_UPLOAD_FIELDS = frozenset(
    {"format_version", "upload_id", "kind", "filename", "size", "sha256", "created_at", "expires_at", "consumed_at"}
)
_MANIFEST_FIELDS = frozenset(
    {"format", "format_version", "compatibility_version", "bundle_id", "created_at", "created_by", "components", "fingerprint"}
)
_COMPONENT_FIELDS = frozenset({"name", "size", "sha256"})
_COMPONENTS = {
    "detector": MODEL_FILENAMES[0],
    "recognizer": MODEL_FILENAMES[1],
    "calibration": CALIBRATION_FILENAME,
    "model_usage": MODEL_USAGE_FILENAME,
}


@dataclass(frozen=True)
class UploadTarget:
    upload_id: str
    kind: str
    filename: str
    path: Path
    created_at: str
    expires_at: str


@dataclass(frozen=True)
class UploadReference:
    upload_id: str
    kind: str
    filename: str
    size: int
    sha256: str
    created_at: str
    expires_at: str

    def dto(self) -> dict[str, object]:
        return {
            "upload_id": self.upload_id,
            "kind": self.kind,
            "filename": self.filename,
            "size": self.size,
            "sha256": self.sha256,
            "expires_at": self.expires_at,
        }


@dataclass(frozen=True)
class ModelBundle:
    bundle_id: str
    created_at: str
    created_by: str
    fingerprint: str
    components: dict[str, dict[str, object]]
    directory: Path
    duplicate: bool = False

    def dto(self) -> dict[str, object]:
        return {
            "bundle_id": self.bundle_id,
            "format_version": MODEL_BUNDLE_FORMAT_VERSION,
            "compatibility_version": MODEL_BUNDLE_COMPATIBILITY_VERSION,
            "created_at": self.created_at,
            "created_by": self.created_by,
            "fingerprint": self.fingerprint,
            "components": self.components,
            "duplicate": self.duplicate,
        }


class ModelBundleAuthority:
    """Own opaque uploads and immutable candidate model bundles outside domain state."""

    def __init__(
        self,
        models_dir: Path,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.models_dir = models_dir
        self.root = models_dir / MODEL_BUNDLE_ROOT_NAME
        self.uploads_dir = self.root / "uploads"
        self.bundles_dir = self.root / "bundles"
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._lock = threading.RLock()

    def begin_upload(self, kind: str, filename: str) -> UploadTarget:
        normalized_kind = kind.strip().casefold()
        if normalized_kind not in _UPLOAD_KINDS:
            raise ModelSetupError("Model upload kind is unsupported")
        safe_filename = _validate_metadata_filename(filename, normalized_kind)
        with self._lock:
            self._prepare_roots()
            upload_id = uuid.uuid4().hex
            upload_dir = self.uploads_dir / upload_id
            self._require_owned_path(upload_dir, self.uploads_dir)
            upload_dir.mkdir(mode=0o700)
            created = _utc(self._now())
            expires = _utc(self._now() + timedelta(seconds=MODEL_UPLOAD_EXPIRY_SECONDS))
            return UploadTarget(
                upload_id=upload_id,
                kind=normalized_kind,
                filename=safe_filename,
                path=upload_dir / "content",
                created_at=created,
                expires_at=expires,
            )

    def complete_upload(
        self,
        target: UploadTarget,
        *,
        sha256: str,
        size: int,
    ) -> UploadReference:
        with self._lock:
            expected_dir = self.uploads_dir / target.upload_id
            if target.path.parent != expected_dir:
                raise ModelSetupError("Model upload target is not server-owned")
            self._require_regular_owned_file(target.path, expected_dir)
            maximum = _limit_for_kind(target.kind)
            if size <= 0 or size > maximum:
                raise ModelSetupError("Model upload size is outside the allowed boundary")
            digest = _validated_sha256(sha256)
            if not verify_file(target.path, digest, size):
                raise ModelSetupError("Model upload changed before registration")
            payload = {
                "format_version": 1,
                "upload_id": target.upload_id,
                "kind": target.kind,
                "filename": target.filename,
                "size": size,
                "sha256": digest,
                "created_at": target.created_at,
                "expires_at": target.expires_at,
                "consumed_at": None,
            }
            _write_json_exclusive(expected_dir / "reference.json", payload)
            return _upload_from_payload(payload)

    def abort_upload(self, target: UploadTarget) -> None:
        with self._lock:
            expected = self.uploads_dir / target.upload_id
            if expected.parent == self.uploads_dir and expected.exists() and not expected.is_symlink():
                shutil.rmtree(expected)

    def create_bundle(
        self,
        *,
        detector_upload_id: str,
        recognizer_upload_id: str,
        calibration_upload_id: str | None,
        calibration_profile: str | None,
        usage_basis: str,
        authorized_by: str,
        organization: str = "",
        licensor: str = "",
        license_reference: str = "",
        license_name: str = "",
    ) -> ModelBundle:
        with self._lock:
            self._prepare_roots()
            references = {
                "detector": self._load_upload(detector_upload_id, "detector"),
                "recognizer": self._load_upload(recognizer_upload_id, "recognizer"),
            }
            if calibration_upload_id:
                references["calibration"] = self._load_upload(
                    calibration_upload_id, "calibration"
                )
            if len({item.upload_id for item in references.values()}) != len(references):
                raise ModelSetupError("A model bundle cannot reuse one upload for multiple components")

            bundle_id = uuid.uuid4().hex
            staging = self.bundles_dir / f".staging-{bundle_id}"
            self._require_owned_path(staging, self.bundles_dir)
            staging.mkdir(mode=0o700)
            try:
                calibration = references.get("calibration")
                declaration = install_local_model_bundle(
                    staging,
                    detector_source=self._upload_content(references["detector"]),
                    detector_sha256=references["detector"].sha256,
                    recognizer_source=self._upload_content(references["recognizer"]),
                    recognizer_sha256=references["recognizer"].sha256,
                    calibration_source=(self._upload_content(calibration) if calibration else None),
                    calibration_sha256=(calibration.sha256 if calibration else None),
                    calibration_profile=calibration_profile,
                    usage_basis=usage_basis,
                    authorized_by=authorized_by,
                    organization=organization,
                    licensor=licensor,
                    license_reference=license_reference,
                    license_name=license_name,
                )
                del declaration
                components = _component_records(staging)
                fingerprint = _bundle_fingerprint(components)
                identity = _bundle_identity(staging, components)
                matches = self._bundles_with_identity(identity)
                if len(matches) > 1:
                    raise ModelSetupError("Existing model bundle authority is ambiguous")
                if len(matches) == 1:
                    raise ModelSetupError(
                        f"An identical model bundle already exists: {matches[0].bundle_id}"
                    )

                created_at = _utc(self._now())
                manifest = {
                    "format": MODEL_BUNDLE_FORMAT,
                    "format_version": MODEL_BUNDLE_FORMAT_VERSION,
                    "compatibility_version": MODEL_BUNDLE_COMPATIBILITY_VERSION,
                    "bundle_id": bundle_id,
                    "created_at": created_at,
                    "created_by": _bounded_text(authorized_by, "Model bundle actor", 200),
                    "components": components,
                    "fingerprint": fingerprint,
                }
                _write_json_exclusive(staging / "manifest.json", manifest)
                final = self.bundles_dir / bundle_id
                os.replace(staging, final)
                _make_immutable(final)
                self._consume_uploads(references.values())
                return self.read_bundle(bundle_id)
            except Exception:
                if staging.exists() and not staging.is_symlink():
                    shutil.rmtree(staging)
                raise

    def cleanup_stale_uploads(self) -> dict[str, int]:
        """Remove expired/consumed upload references and abandoned staging only."""
        removed = {"uploads": 0, "staging": 0}
        with self._lock:
            self._prepare_roots()
            now = self._now()
            for item in list(self.uploads_dir.iterdir()):
                if item.is_symlink() or not item.is_dir():
                    raise ModelSetupError("Model upload authority contains an unsafe entry")
                metadata = item / "reference.json"
                remove = False
                if metadata.exists():
                    payload = _read_json_object(metadata)
                    if set(payload) != _UPLOAD_FIELDS:
                        raise ModelSetupError("Model upload reference is malformed")
                    try:
                        expires = datetime.fromisoformat(str(payload.get("expires_at") or ""))
                    except ValueError as exc:
                        raise ModelSetupError("Model upload expiry is malformed") from exc
                    remove = payload.get("consumed_at") is not None or expires <= now
                else:
                    remove = datetime.fromtimestamp(
                        item.stat().st_mtime, tz=timezone.utc,
                    ) <= now - timedelta(seconds=MODEL_UPLOAD_EXPIRY_SECONDS)
                if remove:
                    shutil.rmtree(item)
                    removed["uploads"] += 1
            cutoff = now - timedelta(seconds=MODEL_STAGING_EXPIRY_SECONDS)
            for item in list(self.bundles_dir.glob(".staging-*")):
                if item.is_symlink() or not item.is_dir():
                    raise ModelSetupError("Model bundle staging contains an unsafe entry")
                changed = datetime.fromtimestamp(item.stat().st_mtime, tz=timezone.utc)
                if changed <= cutoff:
                    shutil.rmtree(item)
                    removed["staging"] += 1
        return removed

    def adopt_legacy_live_bundle(self) -> ModelBundle | None:
        """Adopt one complete pre-P13 live layout without trusting external paths."""
        with self._lock:
            self._prepare_roots()
            paths = {kind: self.models_dir / name for kind, name in _COMPONENTS.items()}
            present = [path.exists() for path in paths.values()]
            if not any(present):
                return None
            if not all(present):
                return None
            for path in paths.values():
                self._require_regular_owned_file(path, self.models_dir)
            require_model_usage_declaration(paths["detector"], paths["recognizer"])
            load_similarity_calibration(paths["calibration"], paths["recognizer"])
            bundle_id = uuid.uuid4().hex
            staging = self.bundles_dir / f".staging-{bundle_id}"
            staging.mkdir(mode=0o700)
            try:
                for kind, name in _COMPONENTS.items():
                    source = paths[kind]
                    shutil.copyfile(source, staging / name)
                components = _component_records(staging)
                identity = _bundle_identity(staging, components)
                matches = self._bundles_with_identity(identity)
                if len(matches) > 1:
                    raise ModelSetupError("Existing model bundle authority is ambiguous")
                if len(matches) == 1:
                    shutil.rmtree(staging)
                    return matches[0]
                manifest = {
                    "format": MODEL_BUNDLE_FORMAT,
                    "format_version": MODEL_BUNDLE_FORMAT_VERSION,
                    "compatibility_version": MODEL_BUNDLE_COMPATIBILITY_VERSION,
                    "bundle_id": bundle_id,
                    "created_at": _utc(self._now()),
                    "created_by": "legacy-runtime-adoption",
                    "components": components,
                    "fingerprint": _bundle_fingerprint(components),
                }
                _write_json_exclusive(staging / "manifest.json", manifest)
                final = self.bundles_dir / bundle_id
                os.replace(staging, final)
                _make_immutable(final)
                return self.read_bundle(bundle_id)
            finally:
                if staging.exists() and not staging.is_symlink():
                    shutil.rmtree(staging)

    def read_bundle(self, bundle_id: str) -> ModelBundle:
        normalized = _validate_opaque_id(bundle_id, "bundle")
        with self._lock:
            self._prepare_roots()
            directory = self.bundles_dir / normalized
            self._require_owned_path(directory, self.bundles_dir)
            if directory.is_symlink() or not directory.is_dir():
                raise ModelSetupError("Model bundle was not found")
            expected_entries = {"manifest.json", *_COMPONENTS.values()}
            actual_entries = {item.name for item in directory.iterdir()}
            if actual_entries != expected_entries:
                raise ModelSetupError("Model bundle contains unknown or missing entries")
            manifest_path = directory / "manifest.json"
            self._require_regular_owned_file(manifest_path, directory)
            payload = _read_json_object(manifest_path)
            if set(payload) != _MANIFEST_FIELDS:
                raise ModelSetupError("Model bundle manifest fields are unsupported")
            if payload.get("format") != MODEL_BUNDLE_FORMAT:
                raise ModelSetupError("Model bundle format is unsupported")
            if (
                type(payload.get("format_version")) is not int
                or payload.get("format_version") != MODEL_BUNDLE_FORMAT_VERSION
            ):
                raise ModelSetupError("Model bundle manifest version is unsupported")
            if (
                type(payload.get("compatibility_version")) is not int
                or payload.get("compatibility_version") != MODEL_BUNDLE_COMPATIBILITY_VERSION
            ):
                raise ModelSetupError("Model bundle compatibility version is unsupported")
            if payload.get("bundle_id") != normalized:
                raise ModelSetupError("Model bundle identity is inconsistent")
            components = payload.get("components")
            if not isinstance(components, dict) or set(components) != set(_COMPONENTS):
                raise ModelSetupError("Model bundle components are incomplete")
            normalized_components: dict[str, dict[str, object]] = {}
            for kind, expected_name in _COMPONENTS.items():
                record = components.get(kind)
                if not isinstance(record, dict) or set(record) != _COMPONENT_FIELDS:
                    raise ModelSetupError("Model bundle component fields are unsupported")
                if record.get("name") != expected_name:
                    raise ModelSetupError("Model bundle component name is inconsistent")
                size = record.get("size")
                digest = _validated_sha256(str(record.get("sha256") or ""))
                if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
                    raise ModelSetupError("Model bundle component size is invalid")
                maximum = (
                    MODEL_COMPONENT_LIMIT_BYTES
                    if kind in {"detector", "recognizer"}
                    else MODEL_METADATA_LIMIT_BYTES
                )
                if size > maximum:
                    raise ModelSetupError("Model bundle component exceeds its size boundary")
                path = directory / expected_name
                self._require_regular_owned_file(path, directory)
                if not verify_file(path, digest, size):
                    raise ModelSetupError("Model bundle component verification failed")
                normalized_components[kind] = {"name": expected_name, "size": size, "sha256": digest}
            fingerprint = _bundle_fingerprint(normalized_components)
            if payload.get("fingerprint") != fingerprint:
                raise ModelSetupError("Model bundle fingerprint is inconsistent")
            created_at = _bounded_text(payload.get("created_at"), "Bundle timestamp", 100)
            created_by = _bounded_text(payload.get("created_by"), "Bundle actor", 200)
            return ModelBundle(
                bundle_id=normalized,
                created_at=created_at,
                created_by=created_by,
                fingerprint=fingerprint,
                components=normalized_components,
                directory=directory,
            )

    def list_bundles(self, *, limit: int = 20) -> tuple[ModelBundle, ...]:
        """Return a bounded newest-first view of server-owned candidates."""
        bounded_limit = max(1, min(int(limit), 100))
        with self._lock:
            self._prepare_roots()
            candidates: list[Path] = []
            for item in self.bundles_dir.iterdir():
                if item.name.startswith(".staging-"):
                    continue
                if item.is_symlink() or not item.is_dir():
                    raise ModelSetupError("Model bundle authority contains an unsafe entry")
                candidates.append(item)
            candidates.sort(
                key=lambda item: (item.stat().st_mtime_ns, item.name), reverse=True,
            )
            return tuple(
                self.read_bundle(item.name)
                for item in candidates[:bounded_limit]
            )

    def _prepare_roots(self) -> None:
        self.models_dir.mkdir(parents=True, exist_ok=True)
        if self.models_dir.is_symlink():
            raise ModelSetupError("Model storage root cannot be a symbolic link")
        for directory in (self.root, self.uploads_dir, self.bundles_dir):
            if directory.exists() and directory.is_symlink():
                raise ModelSetupError("Model authority storage cannot use symbolic links")
            directory.mkdir(mode=0o700, exist_ok=True)
            self._require_owned_path(directory, self.models_dir)

    def _load_upload(self, upload_id: str, expected_kind: str) -> UploadReference:
        normalized = _validate_opaque_id(upload_id, "upload")
        directory = self.uploads_dir / normalized
        self._require_owned_path(directory, self.uploads_dir)
        if directory.is_symlink() or not directory.is_dir():
            raise ModelSetupError("Model upload reference is unknown or already consumed")
        metadata = directory / "reference.json"
        self._require_regular_owned_file(metadata, directory)
        payload = _read_json_object(metadata)
        if (
            set(payload) != _UPLOAD_FIELDS
            or type(payload.get("format_version")) is not int
            or payload.get("format_version") != 1
        ):
            raise ModelSetupError("Model upload reference is malformed")
        reference = _upload_from_payload(payload)
        if reference.upload_id != normalized or reference.kind != expected_kind:
            raise ModelSetupError("Model upload reference does not match the required component")
        if payload.get("consumed_at") is not None:
            raise ModelSetupError("Model upload reference was already consumed")
        if reference.size > _limit_for_kind(reference.kind):
            raise ModelSetupError("Model upload exceeds its size boundary")
        try:
            expires = datetime.fromisoformat(reference.expires_at)
        except ValueError as exc:
            raise ModelSetupError("Model upload expiry is malformed") from exc
        if expires <= self._now():
            raise ModelSetupError("Model upload reference expired")
        content = directory / "content"
        self._require_regular_owned_file(content, directory)
        if not verify_file(content, reference.sha256, reference.size):
            raise ModelSetupError("Model upload changed after registration")
        return reference

    def _upload_content(self, reference: UploadReference | None) -> Path:
        if reference is None:
            raise ModelSetupError("Model bundle component is missing")
        return self.uploads_dir / reference.upload_id / "content"

    def _consume_uploads(self, references: object) -> None:
        consumed_at = _utc(self._now())
        for reference in references:
            if not isinstance(reference, UploadReference):
                raise ModelSetupError("Model upload reference is invalid")
            path = self.uploads_dir / reference.upload_id / "reference.json"
            payload = _read_json_object(path)
            if set(payload) != _UPLOAD_FIELDS or payload.get("consumed_at") is not None:
                raise ModelSetupError("Model upload reference cannot be consumed")
            payload["consumed_at"] = consumed_at
            _replace_json(path, payload)

    def _bundles_with_identity(self, identity: str) -> list[ModelBundle]:
        matches: list[ModelBundle] = []
        for item in self.bundles_dir.iterdir():
            if item.name.startswith(".staging-"):
                continue
            if item.is_symlink():
                raise ModelSetupError("Model bundle authority contains a symbolic link")
            if not item.is_dir():
                raise ModelSetupError("Model bundle authority contains an unknown entry")
            bundle = self.read_bundle(item.name)
            if _bundle_identity(bundle.directory, bundle.components) == identity:
                matches.append(bundle)
        return matches

    @staticmethod
    def _require_owned_path(path: Path, root: Path) -> None:
        try:
            path.resolve(strict=False).relative_to(root.resolve(strict=True))
        except (OSError, ValueError) as exc:
            raise ModelSetupError("Model authority path escaped server-owned storage") from exc

    def _require_regular_owned_file(self, path: Path, root: Path) -> None:
        self._require_owned_path(path, root)
        try:
            mode = path.lstat().st_mode
        except OSError as exc:
            raise ModelSetupError("Required model authority file is missing") from exc
        if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
            raise ModelSetupError("Model authority files must be regular files")


def _component_records(directory: Path) -> dict[str, dict[str, object]]:
    records: dict[str, dict[str, object]] = {}
    for kind, name in _COMPONENTS.items():
        path = directory / name
        if path.is_symlink() or not path.is_file():
            raise ModelSetupError("Model bundle components are incomplete")
        records[kind] = {"name": name, "size": path.stat().st_size, "sha256": _sha256(path)}
    return records


def _bundle_fingerprint(components: dict[str, dict[str, object]]) -> str:
    canonical = json.dumps(
        {
            "format_version": MODEL_BUNDLE_FORMAT_VERSION,
            "compatibility_version": MODEL_BUNDLE_COMPATIBILITY_VERSION,
            "components": components,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _bundle_identity(directory: Path, components: dict[str, dict[str, object]]) -> str:
    usage = _read_json_object(directory / MODEL_USAGE_FILENAME)
    semantic_usage = {key: value for key, value in usage.items() if key != "accepted_at"}
    canonical = json.dumps(
        {
            "format_version": MODEL_BUNDLE_FORMAT_VERSION,
            "compatibility_version": MODEL_BUNDLE_COMPATIBILITY_VERSION,
            "components": {
                key: value
                for key, value in components.items()
                if key != "model_usage"
            },
            "model_usage": semantic_usage,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _upload_from_payload(payload: dict[str, object]) -> UploadReference:
    size = payload.get("size")
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        raise ModelSetupError("Model upload size is invalid")
    return UploadReference(
        upload_id=_validate_opaque_id(str(payload.get("upload_id") or ""), "upload"),
        kind=_bounded_choice(payload.get("kind"), _UPLOAD_KINDS, "upload kind"),
        filename=_validate_metadata_filename(str(payload.get("filename") or ""), str(payload.get("kind") or "")),
        size=size,
        sha256=_validated_sha256(str(payload.get("sha256") or "")),
        created_at=_bounded_text(payload.get("created_at"), "Upload timestamp", 100),
        expires_at=_bounded_text(payload.get("expires_at"), "Upload expiry", 100),
    )


def _validate_metadata_filename(filename: str, kind: str) -> str:
    value = filename.strip()
    if (
        not value
        or len(value) > 255
        or value in {".", ".."}
        or Path(value).name != value
        or "/" in value
        or "\\" in value
        or any(ord(char) < 32 for char in value)
    ):
        raise ModelSetupError("Model filename must be bounded metadata, not a path")
    suffix = Path(value).suffix.casefold()
    expected = ".json" if kind == "calibration" else ".onnx"
    if suffix != expected:
        raise ModelSetupError(f"Model {kind} upload must be a {expected} file")
    return value


def _validate_opaque_id(value: str, label: str) -> str:
    normalized = value.strip().casefold()
    if len(normalized) != 32 or any(char not in "0123456789abcdef" for char in normalized):
        raise ModelSetupError(f"Model {label} ID is invalid")
    return normalized


def _validated_sha256(value: str) -> str:
    normalized = value.strip().casefold()
    if len(normalized) != 64 or any(char not in "0123456789abcdef" for char in normalized):
        raise ModelSetupError("Model SHA-256 is invalid")
    return normalized


def _bounded_choice(value: object, choices: frozenset[str], label: str) -> str:
    normalized = str(value or "").strip().casefold()
    if normalized not in choices:
        raise ModelSetupError(f"Model {label} is unsupported")
    return normalized


def _bounded_text(value: object, label: str, maximum: int) -> str:
    text = str(value or "").strip()
    if not text or len(text) > maximum or any(ord(char) < 32 for char in text):
        raise ModelSetupError(f"{label} is invalid")
    return text


def _limit_for_kind(kind: str) -> int:
    return CALIBRATION_LIMIT_BYTES if kind == "calibration" else MODEL_COMPONENT_LIMIT_BYTES


def _utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json_object(path: Path) -> dict[str, object]:
    try:
        if path.stat().st_size > MODEL_METADATA_LIMIT_BYTES:
            raise ModelSetupError("Model authority metadata exceeds its size boundary")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except ModelSetupError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelSetupError("Model authority metadata is malformed") from exc
    if not isinstance(payload, dict):
        raise ModelSetupError("Model authority metadata must be an object")
    return payload


def _write_json_exclusive(path: Path, payload: dict[str, object]) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as output:
        json.dump(payload, output, indent=2, sort_keys=True)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())


def _replace_json(path: Path, payload: dict[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        _write_json_exclusive(temporary, payload)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _make_immutable(directory: Path) -> None:
    for path in directory.iterdir():
        if path.is_symlink():
            raise ModelSetupError("Model bundle cannot contain symbolic links")
        path.chmod(0o444)
    directory.chmod(0o555)
