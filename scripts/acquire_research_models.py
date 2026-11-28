"""Acquire and verify the operator-approved InsightFace research model files.

This is release infrastructure only. Downloaded archives and extracted ONNX files
are cache/build artifacts and must never be committed to source control.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

MODELS = {
    "det_500m.onnx": {
        "archive_url": "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_s.zip",
        "archive": "buffalo_s.zip",
        "size": 2_524_817,
        "sha256": "5e4447f50245bbd7966bd6c0fa52938c61474a04ec7def48753668a9d8b4ea3a",
        "description": "InsightFace SCRFD-500MF detector",
    },
    "w600k_r50.onnx": {
        "archive_url": "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip",
        "archive": "buffalo_l.zip",
        "size": 174_383_860,
        "sha256": "4c06341c33c2ca1f86781dab0e829f88ad5b64be9fba56e56bc9ebdefc619e43",
        "description": "InsightFace ResNet50/WebFace600K recognizer",
    },
}

NOTICE = """InsightFace pretrained model notice
===================================

The Research installer contains det_500m.onnx and w600k_r50.onnx obtained from
the official InsightFace v0.7 release archives. InsightFace states that its
pretrained models are available for non-commercial research purposes only.
The operator has confirmed permission for this public Research installer
distribution; retain that approval with release records.

These notices do not grant commercial model rights. The Commercial installer
excludes these weights and uses the normal operator-supplied model onboarding
flow. SentriFace does not grant, sublicense, or independently verify
third-party biometric model rights.
"""

CHUNK = 1024 * 1024


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_stream(source, target: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with target.open("wb") as output:
        for chunk in iter(lambda: source.read(CHUNK), b""):
            output.write(chunk)
            digest.update(chunk)
            size += len(chunk)
    return size, digest.hexdigest()


def _zip_has_member(path: Path, member: str) -> bool:
    try:
        with zipfile.ZipFile(path) as archive:
            return member in archive.namelist()
    except (OSError, zipfile.BadZipFile):
        return False


def _download(url: str, destination: Path, member: str, *, retries: int = 4) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    for attempt in range(retries):
        offset = temporary.stat().st_size if temporary.exists() else 0
        headers = {"Range": f"bytes={offset}-"} if offset else {}
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                if offset and response.status != 206:
                    temporary.unlink(missing_ok=True)
                    offset = 0
                mode = "ab" if offset else "wb"
                with temporary.open(mode) as output:
                    shutil.copyfileobj(response, output, length=CHUNK)
            if not _zip_has_member(temporary, member):
                raise RuntimeError(f"Downloaded archive is incomplete or not a valid zip: {url}")
            os.replace(temporary, destination)
            return
        except (OSError, urllib.error.URLError, TimeoutError, RuntimeError):
            if attempt + 1 == retries:
                raise
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Download did not complete: {url}")


def _ensure_archive(cache_dir: Path, spec: dict[str, object], member: str) -> Path:
    archive = cache_dir / str(spec["archive"])
    if not _zip_has_member(archive, member):
        archive.unlink(missing_ok=True)
        _download(str(spec["archive_url"]), archive, member)
    if not _zip_has_member(archive, member):
        raise RuntimeError(f"{archive.name} does not contain required member {member}")
    return archive


def _extract_verified(archive: Path, member: str, spec: dict[str, object], output_dir: Path) -> dict[str, object]:
    staging = output_dir / ".staging"
    staging.mkdir(parents=True, exist_ok=True)
    target = staging / member
    target.unlink(missing_ok=True)
    try:
        with zipfile.ZipFile(archive) as bundle, bundle.open(member) as source:
            size, digest = _hash_stream(source, target)
        expected_size = int(spec["size"])
        expected_digest = str(spec["sha256"])
        if size != expected_size or digest != expected_digest:
            raise RuntimeError(
                f"{member} integrity mismatch: size {size}, sha256 {digest}; "
                f"expected size {expected_size}, sha256 {expected_digest}"
            )
        final = output_dir / member
        final.unlink(missing_ok=True)
        os.replace(target, final)
        return {
            "filename": member,
            "description": spec["description"],
            "size": size,
            "sha256": digest,
            "source_archive": spec["archive"],
            "source_url": spec["archive_url"],
        }
    finally:
        target.unlink(missing_ok=True)
        try:
            staging.rmdir()
        except OSError:
            pass


def acquire(cache_dir: Path, output_dir: Path) -> dict[str, object]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for member, spec in MODELS.items():
        archive = _ensure_archive(cache_dir, spec, member)
        records.append(_extract_verified(archive, member, spec, output_dir))
    provenance = {
        "contract": "sentriface.research-model-provenance",
        "contract_version": 1,
        "usage_basis": "noncommercial-research",
        "redistribution_permission": "operator-confirmed-for-public-research-installer",
        "supplier_notice": "InsightFace pretrained models are available for non-commercial research purposes only.",
        "models": records,
    }
    (output_dir / "research-model-provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "THIRD-PARTY-MODEL-NOTICE.txt").write_text(NOTICE, encoding="utf-8", newline="\n")
    return provenance


def main() -> int:
    parser = argparse.ArgumentParser(description="Acquire verified InsightFace research installer models")
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    acquire(args.cache_dir, args.output_dir)
    print(f"Verified research model payload in {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
