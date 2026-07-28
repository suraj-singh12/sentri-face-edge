from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import urllib.error
import urllib.request
import uuid
import zipfile
from pathlib import Path
from typing import Mapping

from sentriface.paths import default_data_dir, default_model_dir


MODEL_SOURCES: dict[str, dict[str, str | int]] = {
    "det_500m.onnx": {
        "url": "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_s.zip",
        "member": "det_500m.onnx",
        "sha256": "5e4447f50245bbd7966bd6c0fa52938c61474a04ec7def48753668a9d8b4ea3a",
        "size": 2_524_817,
    },
    "w600k_r50.onnx": {
        "url": "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip",
        "member": "w600k_r50.onnx",
        "sha256": "4c06341c33c2ca1f86781dab0e829f88ad5b64be9fba56e56bc9ebdefc619e43",
        "size": 174_383_860,
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download and verify the ONNX models used by SentriFace"
    )
    parser.add_argument("--models-dir", type=Path, default=default_model_dir())
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=default_data_dir() / "model-cache",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    try:
        install_models(args.models_dir, args.cache_dir, force=args.force)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, urllib.error.URLError) as exc:
        print(f"SentriFace model setup failed: {exc}")
        print("No unverified model was installed. Run the command again to retry.")
        return 2
    print(f"SentriFace models are ready in {args.models_dir}")
    return 0


def install_models(
    models_dir: Path,
    cache_dir: Path,
    *,
    force: bool = False,
    sources: Mapping[str, Mapping[str, str | int]] = MODEL_SOURCES,
) -> None:
    models_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    for filename, source in sources.items():
        target = models_dir / filename
        expected_hash = str(source["sha256"]).casefold()
        expected_size = int(source["size"])
        if not force and verify_file(target, expected_hash, expected_size):
            print(f"verified {target}")
            continue
        if target.exists():
            print(f"replace invalid model {target}")

        url = str(source["url"])
        archive = cache_dir / Path(url).name
        if not archive.exists() or force:
            print(f"download {url}")
            _download(url, archive)

        print(f"extract and verify {filename}")
        try:
            _extract_verified(
                archive,
                str(source["member"]),
                target,
                expected_hash,
                expected_size,
            )
        except (zipfile.BadZipFile, KeyError, ValueError):
            archive.unlink(missing_ok=True)
            raise


def verify_file(path: Path, expected_hash: str, expected_size: int) -> bool:
    if not path.is_file() or path.stat().st_size != expected_size:
        return False
    return _sha256(path) == expected_hash.casefold()


def _extract_verified(
    archive: Path,
    member_name: str,
    target: Path,
    expected_hash: str,
    expected_size: int,
) -> None:
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    try:
        with zipfile.ZipFile(archive) as package:
            member = _find_member(package, member_name)
            with package.open(member) as source, temporary.open("xb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
                output.flush()
                os.fsync(output.fileno())
        if not verify_file(temporary, expected_hash, expected_size):
            raise ValueError(
                f"Model verification failed for {target.name}; "
                "the download was not installed"
            )
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _find_member(package: zipfile.ZipFile, filename: str) -> str:
    matches = [
        member
        for member in package.namelist()
        if not member.endswith("/") and Path(member).name == filename
    ]
    if len(matches) != 1:
        raise KeyError(f"Expected exactly one {filename} in {package.filename}")
    return matches[0]


def _download(url: str, target: Path) -> None:
    temporary = target.with_suffix(target.suffix + ".part")
    bytes_seen = temporary.stat().st_size if temporary.exists() else 0
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "SentriFace-Edge/0.1"},
    )
    if bytes_seen:
        request.add_header("Range", f"bytes={bytes_seen}-")
        print(f"resume at {bytes_seen // (1024 * 1024)} MB")

    with urllib.request.urlopen(request, timeout=120) as response:
        if bytes_seen and getattr(response, "status", None) != 206:
            bytes_seen = 0
            temporary.unlink(missing_ok=True)
        mode = "ab" if bytes_seen else "wb"
        with temporary.open(mode) as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
    os.replace(temporary, target)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
