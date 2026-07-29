from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from sentriface.errors import ModelSetupError
from sentriface.paths import default_model_dir

MODEL_FILENAMES = ("detector.onnx", "recognizer.onnx")
MODEL_USAGE_FILENAME = "model-usage.json"
MODEL_USAGE_SCHEMA_VERSION = 1
MODEL_TERMS_VERSION = "2026-07-29"
MODEL_USAGE_BASES = (
    "commercial-license",
    "noncommercial-research",
    "permissive-license",
)



def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install operator-supplied ONNX models without granting model rights"
    )
    parser.add_argument("--models-dir", type=Path, default=default_model_dir())
    parser.add_argument("--detector-source", type=Path, required=True)
    parser.add_argument("--detector-sha256", required=True)
    parser.add_argument("--recognizer-source", type=Path, required=True)
    parser.add_argument("--recognizer-sha256", required=True)
    parser.add_argument(
        "--accept-model-responsibility",
        action="store_true",
        help="Confirm that the operator is responsible for model and biometric-use rights",
    )
    parser.add_argument(
        "--usage-basis",
        choices=MODEL_USAGE_BASES,
        required=True,
        help="Legal basis asserted by the operator for using both supplied weights",
    )
    parser.add_argument(
        "--authorized-by",
        required=True,
        help="Name of the operator or customer administrator making the declaration",
    )
    parser.add_argument("--organization", default="")
    parser.add_argument(
        "--licensor",
        default="",
        help="Required for commercial-license (for example, InsightFace)",
    )
    parser.add_argument(
        "--license-reference",
        default="",
        help="Required for commercial-license; agreement, invoice, or entitlement reference",
    )
    parser.add_argument(
        "--license-name",
        default="",
        help="Required for permissive-license (for example, Apache-2.0)",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if not args.accept_model_responsibility:
        parser.error(
            "--accept-model-responsibility is required; SentriFace does not "
            "provide, verify, or grant rights to third-party model weights"
        )
    try:
        install_local_models(
            args.models_dir,
            detector_source=args.detector_source,
            detector_sha256=args.detector_sha256,
            recognizer_source=args.recognizer_source,
            recognizer_sha256=args.recognizer_sha256,
            usage_basis=args.usage_basis,
            authorized_by=args.authorized_by,
            organization=args.organization,
            licensor=args.licensor,
            license_reference=args.license_reference,
            license_name=args.license_name,
            force=args.force,
        )
    except (OSError, ValueError) as exc:
        print(f"SentriFace model setup failed: {exc}")
        print("Model setup was not activated; ONNX startup remains blocked.")
        return 2
    print(f"Operator-supplied models are ready in {args.models_dir}")
    if args.usage_basis == "noncommercial-research":
        print("NON-COMMERCIAL RESEARCH-ONLY MODEL STATUS IS ACTIVE.")
    return 0


def install_local_models(
    models_dir: Path,
    *,
    detector_source: Path,
    detector_sha256: str,
    recognizer_source: Path,
    recognizer_sha256: str,
    usage_basis: str,
    authorized_by: str,
    organization: str = "",
    licensor: str = "",
    license_reference: str = "",
    license_name: str = "",
    force: bool = False,
) -> dict[str, object]:
    declaration = _validated_declaration_fields(
        usage_basis=usage_basis,
        authorized_by=authorized_by,
        organization=organization,
        licensor=licensor,
        license_reference=license_reference,
        license_name=license_name,
    )

    sources = {
        MODEL_FILENAMES[0]: {"path": detector_source, "sha256": detector_sha256},
        MODEL_FILENAMES[1]: {"path": recognizer_source, "sha256": recognizer_sha256},
    }
    install_models(models_dir, sources=sources, force=force)
    declaration["models"] = {
        MODEL_FILENAMES[0]: {"sha256": _sha256(models_dir / MODEL_FILENAMES[0])},
        MODEL_FILENAMES[1]: {"sha256": _sha256(models_dir / MODEL_FILENAMES[1])},
    }
    _write_usage_declaration(models_dir / MODEL_USAGE_FILENAME, declaration)
    return declaration


def _validated_declaration_fields(
    *,
    usage_basis: str,
    authorized_by: str,
    organization: str = "",
    licensor: str = "",
    license_reference: str = "",
    license_name: str = "",
) -> dict[str, object]:
    basis = usage_basis.strip().casefold()
    operator = authorized_by.strip()
    organization = organization.strip()
    licensor = licensor.strip()
    license_reference = license_reference.strip()
    license_name = license_name.strip()
    if basis not in MODEL_USAGE_BASES:
        raise ValueError(f"Usage basis must be one of: {', '.join(MODEL_USAGE_BASES)}")
    if not operator:
        raise ValueError("Authorized operator name is required")
    if basis == "commercial-license" and (not licensor or not license_reference):
        raise ValueError(
            "Commercial use requires both --licensor and --license-reference"
        )
    if basis == "permissive-license" and not license_name:
        raise ValueError("Permissive use requires --license-name")
    return {
        "schema_version": MODEL_USAGE_SCHEMA_VERSION,
        "terms_version": MODEL_TERMS_VERSION,
        "usage_basis": basis,
        "authorized_by": operator,
        "organization": organization,
        "licensor": licensor,
        "license_reference": license_reference,
        "license_name": license_name,
        "accepted_at": datetime.now(timezone.utc).isoformat(),
        "operator_declaration": (
            "The operator supplied these third-party model files and accepts sole "
            "responsibility for model licensing, biometric-data permissions, and use. "
            "SentriFace supplies no model rights and does not verify this assertion."
        ),
    }


def _write_usage_declaration(path: Path, declaration: dict[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as output:
            json.dump(declaration, output, indent=2, sort_keys=True)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def require_model_usage_declaration(
    detector_model: Path,
    recognizer_model: Path,
) -> dict[str, object]:
    """Fail closed unless the operator declaration covers these exact model files."""
    if recognizer_model.parent != detector_model.parent:
        raise ModelSetupError(
            "Detector and recognizer must share a directory with model-usage.json"
        )
    declaration_path = detector_model.parent / MODEL_USAGE_FILENAME
    try:
        declaration = json.loads(declaration_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelSetupError(
            "A valid model-usage.json declaration is required beside operator-supplied models"
        ) from exc
    if not isinstance(declaration, dict):
        raise ModelSetupError("Model usage declaration must be a JSON object")
    if declaration.get("schema_version") != MODEL_USAGE_SCHEMA_VERSION:
        raise ModelSetupError("Model usage declaration schema is unsupported")
    if declaration.get("terms_version") != MODEL_TERMS_VERSION:
        raise ModelSetupError(
            "Model responsibility terms changed; run sentriface-models to accept them again"
        )
    if not str(declaration.get("accepted_at") or "").strip():
        raise ModelSetupError("Model usage declaration has no acceptance timestamp")
    try:
        _validated_declaration_fields(
            usage_basis=str(declaration.get("usage_basis") or ""),
            authorized_by=str(declaration.get("authorized_by") or ""),
            organization=str(declaration.get("organization") or ""),
            licensor=str(declaration.get("licensor") or ""),
            license_reference=str(declaration.get("license_reference") or ""),
            license_name=str(declaration.get("license_name") or ""),
        )
    except ValueError as exc:
        raise ModelSetupError(f"Model usage declaration is incomplete: {exc}") from exc
    models = declaration.get("models")
    if not isinstance(models, dict):
        raise ModelSetupError("Model usage declaration has no model hashes")
    for filename, path in (
        (MODEL_FILENAMES[0], detector_model),
        (MODEL_FILENAMES[1], recognizer_model),
    ):
        record = models.get(filename)
        if not isinstance(record, dict):
            raise ModelSetupError(f"Model usage declaration does not cover {filename}")
        try:
            expected = _validated_digest(str(record.get("sha256") or ""))
            actual = _sha256(path)
        except (OSError, ValueError) as exc:
            raise ModelSetupError(f"Could not verify declared model: {filename}") from exc
        if actual != expected:
            raise ModelSetupError(
                f"{filename} changed after model rights were declared; "
                "run sentriface-models again"
            )
    return declaration


def install_models(
    models_dir: Path,
    cache_dir: Path | None = None,
    *,
    force: bool = False,
    sources: Mapping[str, Mapping[str, str | int | Path]],
) -> None:
    """Install only caller-supplied local files; network model sources are forbidden."""
    del cache_dir
    models_dir.mkdir(parents=True, exist_ok=True)
    for filename, source in sources.items():
        target = models_dir / filename
        expected_hash = _validated_digest(str(source["sha256"]))
        expected_size = int(source.get("size", -1))
        if expected_size >= 0 and not force and verify_file(target, expected_hash, expected_size):
            continue
        raw_source = source.get("path")
        if raw_source is None:
            raise ValueError(
                "Automatic model downloads are disabled. Supply locally licensed model files."
            )
        local_source = Path(raw_source)
        if not local_source.is_file():
            raise ValueError(f"Model source was not found: {local_source}")
        actual_size = local_source.stat().st_size
        if expected_size < 0:
            expected_size = actual_size
        if not verify_file(local_source, expected_hash, expected_size):
            raise ValueError(f"Model checksum verification failed: {local_source.name}")
        _copy_verified(local_source, target, expected_hash, expected_size)


def verify_file(path: Path, expected_hash: str, expected_size: int) -> bool:
    return (
        path.is_file()
        and path.stat().st_size == expected_size
        and _sha256(path) == expected_hash.casefold()
    )


def _copy_verified(
    source: Path,
    target: Path,
    expected_hash: str,
    expected_size: int,
) -> None:
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    try:
        with source.open("rb") as input_file, temporary.open("xb") as output:
            shutil.copyfileobj(input_file, output, length=1024 * 1024)
            output.flush()
            os.fsync(output.fileno())
        if not verify_file(temporary, expected_hash, expected_size):
            raise ValueError(f"Model verification failed for {target.name}")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _extract_verified(
    archive: Path,
    member_name: str,
    target: Path,
    expected_hash: str,
    expected_size: int,
) -> None:
    """Compatibility helper for installing from a caller-owned local archive."""
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    try:
        with zipfile.ZipFile(archive) as package:
            matches = [
                name for name in package.namelist()
                if not name.endswith("/") and Path(name).name == member_name
            ]
            if len(matches) != 1:
                raise KeyError(f"Expected exactly one {member_name} in {archive}")
            with package.open(matches[0]) as source, temporary.open("xb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
                output.flush()
                os.fsync(output.fileno())
        if not verify_file(temporary, expected_hash, expected_size):
            raise ValueError(f"Model verification failed for {target.name}")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _validated_digest(value: str) -> str:
    normalized = value.strip().casefold()
    if len(normalized) != 64 or any(char not in "0123456789abcdef" for char in normalized):
        raise ValueError("Model SHA-256 must be exactly 64 hexadecimal characters")
    return normalized


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
