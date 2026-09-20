from __future__ import annotations

import argparse
import importlib.metadata
import platform
import re
import struct
import sys
from pathlib import Path


PIN = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s;]+)$")


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).casefold()


def read_lock(path: Path) -> dict[str, tuple[str, str]]:
    pins: dict[str, tuple[str, str]] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = PIN.fullmatch(line)
        if not match:
            raise ValueError(f"{path}:{number}: release lock entries must be exact pins")
        name, version = match.groups()
        key = normalize(name)
        if key in pins:
            raise ValueError(f"{path}:{number}: duplicate release package {name}")
        pins[key] = (name, version)
    if not pins:
        raise ValueError("release dependency lock is empty")
    return pins


def verify(path: Path) -> list[str]:
    errors: list[str] = []
    if sys.version_info[:2] != (3, 12):
        errors.append(f"release Python must be 3.12, found {platform.python_version()}")
    if struct.calcsize("P") != 8 or platform.machine().casefold() not in {
        "amd64", "x86_64"
    }:
        errors.append(f"release Python must be Windows AMD64, found {platform.machine()}")
    try:
        pins = read_lock(path)
    except ValueError as exc:
        return [str(exc)]
    installed = {
        normalize(dist.metadata["Name"]): dist.version
        for dist in importlib.metadata.distributions()
        if dist.metadata.get("Name")
    }
    for key, (name, expected) in sorted(pins.items()):
        actual = installed.get(key)
        if actual is None:
            errors.append(f"locked package is missing: {name}=={expected}")
        elif actual != expected:
            errors.append(
                f"locked package version mismatch: {name} expected {expected}, found {actual}"
            )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, required=True)
    args = parser.parse_args()
    errors = verify(args.lock)
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    print(f"Verified exact release environment from {args.lock}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
