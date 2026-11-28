"""Automatic provisioning of the approved bundled Research model payload.

The payload is release media, not source authority. Provisioning still passes
through the same immutable bundle, validation, activation and receipt authority
as operator-supplied models.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import uuid
from pathlib import Path

from sentriface.errors import ModelSetupError

RESEARCH_MODELS = {
    "detector": {
        "filename": "det_500m.onnx",
        "size": 2_524_817,
        "sha256": "5e4447f50245bbd7966bd6c0fa52938c61474a04ec7def48753668a9d8b4ea3a",
    },
    "recognizer": {
        "filename": "w600k_r50.onnx",
        "size": 174_383_860,
        "sha256": "4c06341c33c2ca1f86781dab0e829f88ad5b64be9fba56e56bc9ebdefc619e43",
    },
}
RESEARCH_CALIBRATION_PROFILE = "scrfd500m-r50-research"
_CHUNK = 1024 * 1024


def bundled_research_payload_dir() -> Path | None:
    """Return the packaged payload directory when it is present beside the executable."""
    candidate = Path(sys.executable).resolve().parent / "bundled-models"
    return candidate if candidate.is_dir() else None


def _copy_with_hash(source: Path, target: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with source.open("rb") as input_file, target.open("wb") as output_file:
        for chunk in iter(lambda: input_file.read(_CHUNK), b""):
            output_file.write(chunk)
            digest.update(chunk)
            size += len(chunk)
    return size, digest.hexdigest()


def _validated_payload(payload_dir: Path) -> dict[str, Path]:
    if not payload_dir.is_dir() or payload_dir.is_symlink():
        raise ModelSetupError("Bundled Research model payload is missing")
    notice = payload_dir / "THIRD-PARTY-MODEL-NOTICE.txt"
    provenance = payload_dir / "research-model-provenance.json"
    if not notice.is_file() or not provenance.is_file():
        raise ModelSetupError("Bundled Research model provenance or notice is missing")
    try:
        provenance_payload = json.loads(provenance.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelSetupError("Bundled Research model provenance is malformed") from exc
    if provenance_payload.get("contract") != "sentriface.research-model-provenance":
        raise ModelSetupError("Bundled Research model provenance is unsupported")
    paths: dict[str, Path] = {}
    for kind, spec in RESEARCH_MODELS.items():
        path = payload_dir / str(spec["filename"])
        if not path.is_file() or path.is_symlink():
            raise ModelSetupError(f"Bundled Research {kind} model is missing")
        if path.stat().st_size != int(spec["size"]):
            raise ModelSetupError(f"Bundled Research {kind} model size does not match its release identity")
        paths[kind] = path
    return paths


def _upload_payload_file(authority, kind: str, path: Path, spec: dict[str, object]):
    target = authority.begin_upload(kind, str(spec["filename"]))
    try:
        size, digest = _copy_with_hash(path, target.path)
        if size != int(spec["size"]) or digest != str(spec["sha256"]):
            raise ModelSetupError(f"Bundled Research {kind} model hash does not match its release identity")
        return authority.complete_upload(target, sha256=digest, size=size)
    except Exception:
        authority.abort_upload(target)
        raise


def _existing_research_bundle(authority):
    expected = {kind: str(spec["sha256"]) for kind, spec in RESEARCH_MODELS.items()}
    for bundle in authority.list_bundles(limit=100):
        try:
            if all(bundle.components[kind]["sha256"] == expected[kind] for kind in expected):
                return bundle
        except (KeyError, TypeError):
            continue
    return None


def provision_bundled_research_models(server) -> bool:
    """Provision the approved payload when this is a fresh Research installation.

    Returns True only when activation completed. Any existing active model state
    is authoritative and is never replaced. Failures raise ModelSetupError; the
    caller keeps the ordinary fail-closed Model Setup path.
    """
    if server.runtime != "onnx":
        return False
    payload_dir = bundled_research_payload_dir()
    if payload_dir is None:
        return False
    if server.model_activation.active_state() is not None:
        return False
    paths = _validated_payload(payload_dir)
    authority = server.model_bundles
    bundle = _existing_research_bundle(authority)
    if bundle is None:
        uploads = {}
        try:
            for kind, spec in RESEARCH_MODELS.items():
                uploads[kind] = _upload_payload_file(authority, kind, paths[kind], spec)
            bundle = authority.create_bundle(
                detector_upload_id=uploads["detector"].upload_id,
                recognizer_upload_id=uploads["recognizer"].upload_id,
                calibration_upload_id=None,
                calibration_profile=RESEARCH_CALIBRATION_PROFILE,
                usage_basis="noncommercial-research",
                authorized_by="SentriFace Research installer automatic provisioning",
                organization="SentriFace",
                licensor="InsightFace",
                license_reference="Operator-confirmed public Research installer redistribution; non-commercial research use only",
                license_name="",
                operator_declaration=(
                    "The approved Research installer supplied these exact pinned model files for "
                    "non-commercial research use under operator-confirmed redistribution permission. "
                    "The operator retains responsibility for lawful biometric use; SentriFace does "
                    "not grant broader model rights."
                ),
            )
        except ModelSetupError as exc:
            if "identical model bundle already exists" not in str(exc):
                raise
            bundle = _existing_research_bundle(authority)
            if bundle is None:
                raise
    preparation = server.model_activation.prepare_model_activation(bundle.bundle_id)
    server.model_activation.execute(
        preparation["token"],
        str(uuid.uuid4()),
        actor={"user_id": "system", "username": "research-installer"},
        reason="Automatic first-start provisioning of the approved bundled Research model payload",
    )
    server.sync_model_runtime_state()
    server.log_event(
        "bundled-research-models-provisioned",
        bundle_id=bundle.bundle_id,
        detector_sha256=RESEARCH_MODELS["detector"]["sha256"],
        recognizer_sha256=RESEARCH_MODELS["recognizer"]["sha256"],
    )
    return True
