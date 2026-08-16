from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


FORBIDDEN_NAMES = re.compile(
    r"(?:private[_-]?key|license[_-]?(?:signing|token)|recovery[_-]?kit|\.pfx$|\.onnx$|detector\.dat$|recognizer\.dat$|\.sfbackup(?:\.enc)?$|\.sqlite(?:3)?$|\.db$|\.tmp$)",
    re.IGNORECASE,
)
REQUIRED_PATTERNS = (
    "SentriFaceEdge.exe",
    "sentriface",
    "onnxruntime",
    "cv2",
    "sqlcipher",
    "keyring",
)


def inspect(distribution: Path, version: str) -> list[str]:
    errors: list[str] = []
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        errors.append("release version is invalid")
    if not distribution.is_dir():
        return ["standalone distribution is missing"]
    files = [path for path in distribution.rglob("*") if path.is_file()]
    relative = [str(path.relative_to(distribution)).replace("\\", "/") for path in files]
    for name in relative:
        if FORBIDDEN_NAMES.search(name):
            errors.append(f"forbidden release content: {Path(name).name}")
    for path in files:
        if path.stat().st_size <= 1_000_000:
            try:
                if b"-----BEGIN PRIVATE KEY-----" in path.read_bytes():
                    errors.append(f"private key material detected: {path.name}")
            except OSError:
                errors.append(f"release content could not be inspected: {path.name}")
    folded = "\n".join(relative).casefold()
    for required in REQUIRED_PATTERNS:
        if required.casefold() not in folded:
            errors.append(f"required packaged component is missing: {required}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--distribution", type=Path, required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    errors = inspect(args.distribution, args.version)
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
