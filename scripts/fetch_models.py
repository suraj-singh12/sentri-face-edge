from __future__ import annotations

import argparse
import shutil
import urllib.request
import zipfile
from pathlib import Path


MODEL_SOURCES = {
    "det_500m.onnx": {
        "url": "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_s.zip",
        "member": "det_500m.onnx",
    },
    "w600k_r50.onnx": {
        "url": "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip",
        "member": "w600k_r50.onnx",
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch SentriFace ONNX models")
    parser.add_argument("--models-dir", type=Path, default=Path("models"))
    parser.add_argument("--cache-dir", type=Path, default=Path(".model-cache"))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    args.models_dir.mkdir(parents=True, exist_ok=True)
    args.cache_dir.mkdir(parents=True, exist_ok=True)

    for filename, source in MODEL_SOURCES.items():
        target = args.models_dir / filename
        if target.exists() and not args.force:
            print(f"exists {target}")
            continue

        archive = args.cache_dir / Path(source["url"]).name
        if not archive.exists() or args.force:
            print(f"download {source['url']}")
            _download(source["url"], archive)

        print(f"extract {filename}")
        with zipfile.ZipFile(archive) as zip_file:
            member = _find_member(zip_file, source["member"])
            with zip_file.open(member) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
        print(f"ready {target}")

    return 0


def _find_member(zip_file: zipfile.ZipFile, filename: str) -> str:
    for member in zip_file.namelist():
        if Path(member).name == filename:
            return member
    raise FileNotFoundError(f"{filename} not found in {zip_file.filename}")


def _download(url: str, target: Path) -> None:
    temp_target = target.with_suffix(target.suffix + ".part")
    bytes_seen = temp_target.stat().st_size if temp_target.exists() else 0
    last_report_mb = -1
    request = urllib.request.Request(url)
    if bytes_seen:
        request.add_header("Range", f"bytes={bytes_seen}-")
        print(f"resume at {bytes_seen // (1024 * 1024)} MB")

    with urllib.request.urlopen(request, timeout=120) as response:
        total = int(response.headers.get("Content-Length") or 0)
        if bytes_seen and getattr(response, "status", None) != 206:
            print("server did not resume; restarting download")
            bytes_seen = 0
            temp_target.unlink(missing_ok=True)
        expected_total = bytes_seen + total if bytes_seen else total
        with temp_target.open("ab" if bytes_seen else "wb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                bytes_seen += len(chunk)
                current_mb = bytes_seen // (1024 * 1024)
                if current_mb != last_report_mb:
                    last_report_mb = current_mb
                    if expected_total:
                        total_mb = expected_total // (1024 * 1024)
                        print(f"  {current_mb}/{total_mb} MB")
                    else:
                        print(f"  {current_mb} MB")

    temp_target.replace(target)


if __name__ == "__main__":
    raise SystemExit(main())
