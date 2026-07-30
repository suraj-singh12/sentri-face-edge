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
CALIBRATION_FILENAME = "calibration.json"
MODEL_USAGE_FILENAME = "model-usage.json"
MODEL_USAGE_SCHEMA_VERSION = 1
MODEL_TERMS_VERSION = "2026-07-29"
MODEL_USAGE_BASES = (
    "commercial-license",
    "noncommercial-research",
    "permissive-license",
)

MODEL_COMBINATIONS = {
    "research": [
        {
            "id": "buffalo-s-research",
            "name": "InsightFace buffalo_s",
            "detector": "SCRFD-500MF",
            "recognizer": "MobileFaceNet / WebFace600K",
            "detector_file": "det_500m.onnx",
            "recognizer_file": "w600k_mbf.onnx",
            "usage_basis": "noncommercial-research",
            "note": "Smallest supported InsightFace pair for lower-end CPUs.",
        },
        {
            "id": "buffalo-l-research",
            "name": "InsightFace buffalo_l",
            "detector": "SCRFD-10GF",
            "recognizer": "ResNet50 / WebFace600K",
            "detector_file": "det_10g.onnx",
            "recognizer_file": "w600k_r50.onnx",
            "usage_basis": "noncommercial-research",
            "note": "Higher-accuracy supported InsightFace pair with greater CPU cost.",
        },
        {
            "id": "buffalo-m-research",
            "name": "InsightFace buffalo_m",
            "detector": "SCRFD-2.5GF",
            "recognizer": "ResNet50 / WebFace600K",
            "detector_file": "det_2.5g.onnx",
            "recognizer_file": "w600k_r50.onnx",
            "usage_basis": "noncommercial-research",
            "note": "Middle detector size with the buffalo_l recognition model.",
        },
    ],
    "commercial": [
        {
            "id": "insightface-commercial",
            "name": "Commercially licensed InsightFace",
            "detector": "Licensed SCRFD ONNX",
            "recognizer": "Licensed buffalo/antelope ArcFace ONNX",
            "usage_basis": "commercial-license",
            "note": "Requires a commercial model entitlement from InsightFace or its authorized licensor.",
        },
        {
            "id": "compatible-commercial",
            "name": "Other commercially licensed pair",
            "detector": "SCRFD-compatible ONNX",
            "recognizer": "512-dimensional ArcFace-compatible ONNX",
            "usage_basis": "commercial-license",
            "note": "For a supplier-licensed compatible detector and recognizer pair.",
        },
        {
            "id": "compatible-permissive",
            "name": "Permissively licensed compatible pair",
            "detector": "SCRFD-compatible ONNX",
            "recognizer": "512-dimensional ArcFace-compatible ONNX",
            "usage_basis": "permissive-license",
            "note": "Commercial use is allowed only when the supplied model licenses permit it.",
        },
    ],
}


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
        "--calibration-source",
        type=Path,
        help="Optional validation-calibrated threshold file; omit to use SentriFace defaults",
    )
    parser.add_argument(
        "--calibration-sha256",
        help="SHA-256 of --calibration-source; required when that option is used",
    )
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
    if bool(args.calibration_source) != bool(args.calibration_sha256):
        parser.error(
            "--calibration-source and --calibration-sha256 must be supplied together"
        )
    try:
        install_local_model_bundle(
            args.models_dir,
            detector_source=args.detector_source,
            detector_sha256=args.detector_sha256,
            recognizer_source=args.recognizer_source,
            recognizer_sha256=args.recognizer_sha256,
            calibration_source=args.calibration_source,
            calibration_sha256=args.calibration_sha256,
            usage_basis=args.usage_basis,
            authorized_by=args.authorized_by,
            organization=args.organization,
            licensor=args.licensor,
            license_reference=args.license_reference,
            license_name=args.license_name,
            force=args.force,
        )
    except (ModelSetupError, OSError, ValueError) as exc:
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


def install_local_model_bundle(
    models_dir: Path,
    *,
    detector_source: Path,
    detector_sha256: str,
    recognizer_source: Path,
    recognizer_sha256: str,
    calibration_source: Path | None = None,
    calibration_sha256: str | None = None,
    usage_basis: str,
    authorized_by: str,
    organization: str = "",
    licensor: str = "",
    license_reference: str = "",
    license_name: str = "",
    force: bool = False,
) -> dict[str, object]:
    """Install a local model pair with custom or built-in similarity thresholds."""
    detector_digest = _validated_digest(detector_sha256)
    recognizer_digest = _validated_digest(recognizer_sha256)
    for label, source, digest in (
        ("Detector", detector_source, detector_digest),
        ("Recognizer", recognizer_source, recognizer_digest),
    ):
        if not source.is_file():
            raise ValueError(f"{label} source was not found: {source}")
        if not verify_file(source, digest, source.stat().st_size):
            raise ValueError(f"{label} checksum verification failed: {source.name}")
    if bool(calibration_source) != bool(calibration_sha256):
        raise ValueError(
            "Calibration source and checksum must be supplied together or both omitted"
        )
    calibration_digest = (
        _validated_digest(calibration_sha256)
        if calibration_sha256 is not None
        else None
    )
    if calibration_source is not None and calibration_digest is not None:
        if not calibration_source.is_file():
            raise ValueError(f"Calibration source was not found: {calibration_source}")
        if not verify_file(
            calibration_source,
            calibration_digest,
            calibration_source.stat().st_size,
        ):
            raise ValueError(
                f"Calibration checksum verification failed: {calibration_source.name}"
            )
        load_similarity_calibration(
            calibration_source,
            recognizer_source,
            recognizer_digest,
        )
    declaration = install_local_models(
        models_dir,
        detector_source=detector_source,
        detector_sha256=detector_digest,
        recognizer_source=recognizer_source,
        recognizer_sha256=recognizer_digest,
        usage_basis=usage_basis,
        authorized_by=authorized_by,
        organization=organization,
        licensor=licensor,
        license_reference=license_reference,
        license_name=license_name,
        force=force,
    )
    calibration_target = models_dir / CALIBRATION_FILENAME
    if calibration_source is not None and calibration_digest is not None:
        _copy_verified(
            calibration_source,
            calibration_target,
            calibration_digest,
            calibration_source.stat().st_size,
        )
    else:
        _write_default_similarity_thresholds(calibration_target, recognizer_digest)
    return declaration


def _write_default_similarity_thresholds(
    calibration_path: Path,
    recognizer_sha256: str,
) -> None:
    """Write hash-bound legacy thresholds without claiming dataset calibration."""
    payload = {
        "schema_version": 1,
        "recognizer_sha256": recognizer_sha256,
        "calibration_method": "sentriface-default",
        "calibration_status": "not-validation-calibrated",
        "note": (
            "Built-in similarity thresholds. Validate and replace these thresholds "
            "for the deployment population and target false-match rate."
        ),
        "thresholds": {
            "possible": 0.40,
            "likely": 0.50,
            "strong": 0.60,
        },
    }
    calibration_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = calibration_path.with_name(
        f".{calibration_path.name}.{uuid.uuid4().hex}.tmp"
    )
    try:
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, calibration_path)
    finally:
        temporary.unlink(missing_ok=True)

def load_similarity_calibration(
    calibration_path: Path,
    recognizer_path: Path,
    recognizer_sha256: str | None = None,
) -> dict[str, object]:
    """Load calibration provenance and thresholds for one exact recognizer."""
    try:
        payload = json.loads(calibration_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelSetupError("A valid calibration.json is required beside the recognizer model") from exc
    if not isinstance(payload, dict):
        raise ModelSetupError("Similarity calibration must be a JSON object")
    expected_digest = str(payload.get("recognizer_sha256") or "").casefold()
    try:
        actual_digest = recognizer_sha256 or _sha256(recognizer_path)
        expected_digest = _validated_digest(expected_digest)
    except (ModelSetupError, OSError, ValueError) as exc:
        raise ModelSetupError("Similarity calibration has an invalid recognizer digest") from exc
    if expected_digest != actual_digest.casefold():
        raise ModelSetupError("Similarity calibration does not match the recognizer model")
    method = str(payload.get("calibration_method") or "validation").strip()
    dataset = str(payload.get("representative_dataset") or "").strip()
    target_fmr: float | None = None
    if method != "sentriface-default":
        try:
            target_fmr = float(payload.get("target_false_match_rate", 0))
        except (TypeError, ValueError) as exc:
            raise ModelSetupError(
                "Similarity calibration target false-match rate is invalid"
            ) from exc
    thresholds = payload.get("thresholds")
    if (
        method != "sentriface-default"
        and (not dataset or target_fmr is None or not 0 < target_fmr <= 1)
    ):
        raise ModelSetupError("Similarity calibration provenance is incomplete")
    if not isinstance(thresholds, dict):
        raise ModelSetupError("Similarity calibration thresholds are invalid")
    try:
        possible = float(thresholds.get("possible", -1))
        likely = float(thresholds.get("likely", -1))
        strong = float(thresholds.get("strong", -1))
    except (TypeError, ValueError) as exc:
        raise ModelSetupError("Similarity calibration thresholds are invalid") from exc
    if not 0 <= possible <= likely <= strong <= 1:
        raise ModelSetupError("Similarity calibration thresholds are invalid")
    return {
        **payload,
        "representative_dataset": dataset or None,
        "target_false_match_rate": target_fmr,
        "thresholds": {"possible": possible, "likely": likely, "strong": strong},
    }


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
        except (ModelSetupError, OSError, ValueError) as exc:
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
