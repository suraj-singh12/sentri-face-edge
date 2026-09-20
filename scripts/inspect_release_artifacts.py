from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import sys
from pathlib import Path
from typing import Any


FORBIDDEN_NAMES = re.compile(
    r"(?:private[_-]?key|license[_-]?(?:signing|token)|recovery[_-]?kit|"
    r"\.pfx$|\.onnx$|detector\.dat$|recognizer\.dat$|\.sfbackup(?:\.enc)?$|"
    r"\.sqlite(?:3)?$|\.db$|\.tmp$)",
    re.IGNORECASE,
)
REQUIRED_PATTERNS = (
    "SentriFaceEdge.exe",
    "sentriface",
    "onnxruntime",
    "cv2",
    "sqlcipher",
)
PE_EXTENSIONS = {".exe", ".dll", ".pyd"}
PE_MACHINES = {
    0x014C: "I386",
    0x8664: "AMD64",
    0xAA64: "ARM64",
}
EXPECTED_MACHINE = "AMD64"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pe_machine(path: Path) -> tuple[int, str]:
    with path.open("rb") as source:
        header = source.read(64)
        if len(header) < 64 or header[:2] != b"MZ":
            raise ValueError("missing DOS/PE header")
        pe_offset = struct.unpack_from("<I", header, 0x3C)[0]
        if pe_offset < 64 or pe_offset > path.stat().st_size - 6:
            raise ValueError("invalid PE header offset")
        source.seek(pe_offset)
        if source.read(4) != b"PE\x00\x00":
            raise ValueError("missing PE signature")
        machine = struct.unpack("<H", source.read(2))[0]
    return machine, PE_MACHINES.get(machine, f"UNKNOWN-0x{machine:04X}")


def _contains_bytes(path: Path, needle: bytes) -> bool:
    if not needle:
        return False
    overlap = max(0, len(needle) - 1)
    tail = b""
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            haystack = tail + chunk
            if needle in haystack:
                return True
            tail = haystack[-overlap:] if overlap else b""
    return False


def inspect_distribution(
    distribution: Path,
    version: str,
    *,
    forbidden_path: str = "",
    installer: Path | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        errors.append("release version is invalid")
    if not distribution.is_dir():
        return {
            "contract": "sentriface.release-artifact-inspection",
            "contract_version": 2,
            "status": "FAIL",
            "version": version,
            "errors": ["standalone distribution is missing"],
            "file_count": 0,
            "native_binaries": [],
        }

    files = sorted(
        (path for path in distribution.rglob("*") if path.is_file()),
        key=lambda path: str(path.relative_to(distribution)).casefold(),
    )
    relative = [
        str(path.relative_to(distribution)).replace("\\", "/")
        for path in files
    ]
    for name in relative:
        if FORBIDDEN_NAMES.search(name):
            errors.append(f"forbidden release content: {Path(name).name}")
    for path in files:
        if path.stat().st_size <= 1_000_000:
            try:
                data = path.read_bytes()
                if b"-----BEGIN PRIVATE KEY-----" in data:
                    errors.append(f"private key material detected: {path.name}")
                if b"SFE2." in data and path.suffix.casefold() in {
                    ".json", ".txt", ".log", ".ini", ".cfg"
                }:
                    errors.append(f"offline license token detected: {path.name}")
            except OSError:
                errors.append(f"release content could not be inspected: {path.name}")
    folded = "\n".join(relative).casefold()
    for required in REQUIRED_PATTERNS:
        if required.casefold() not in folded:
            errors.append(f"required packaged component is missing: {required}")

    native_binaries: list[dict[str, Any]] = []
    for path, name in zip(files, relative):
        if path.suffix.casefold() not in PE_EXTENSIONS:
            continue
        try:
            machine_code, architecture = pe_machine(path)
        except (OSError, ValueError, struct.error) as exc:
            errors.append(f"invalid Windows PE binary {name}: {exc}")
            continue
        native_binaries.append(
            {
                "path": name,
                "architecture": architecture,
                "machine": f"0x{machine_code:04X}",
                "size": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
        if architecture != EXPECTED_MACHINE:
            errors.append(
                f"unexpected Windows PE architecture {architecture}: {name}"
            )

    if not native_binaries:
        errors.append("no Windows PE binaries were found")
    executable = next(
        (item for item in native_binaries if item["path"].casefold() == "sentrifaceedge.exe"),
        None,
    )
    if executable is None:
        errors.append("SentriFaceEdge.exe was not parsed as a Windows PE binary")

    installer_record = None
    if installer is not None:
        if not installer.is_file():
            errors.append("installer executable is missing")
        else:
            try:
                machine_code, architecture = pe_machine(installer)
            except (OSError, ValueError, struct.error) as exc:
                errors.append(f"invalid Windows PE installer {installer.name}: {exc}")
            else:
                installer_record = {
                    "path": installer.name,
                    "architecture": architecture,
                    "machine": f"0x{machine_code:04X}",
                    "size": installer.stat().st_size,
                    "sha256": _sha256(installer),
                }
                if architecture != EXPECTED_MACHINE:
                    errors.append(
                        "unexpected Windows PE installer architecture "
                        f"{architecture}: {installer.name}"
                    )

    if forbidden_path:
        encoded_needles = {
            forbidden_path.encode("utf-8", errors="ignore"),
            forbidden_path.encode("utf-16le", errors="ignore"),
            forbidden_path.replace("\\", "/").encode("utf-8", errors="ignore"),
        }
        for path, name in zip(files, relative):
            try:
                if any(_contains_bytes(path, needle) for needle in encoded_needles if needle):
                    errors.append(f"developer source path embedded in release content: {name}")
            except OSError:
                errors.append(f"release content could not be path-scanned: {name}")

    architectures = {item["architecture"] for item in native_binaries}
    if installer_record is not None:
        architectures.add(installer_record["architecture"])
    return {
        "contract": "sentriface.release-artifact-inspection",
        "contract_version": 2,
        "status": "FAIL" if errors else "PASS",
        "version": version,
        "expected_architecture": EXPECTED_MACHINE,
        "architectures": sorted(architectures),
        "file_count": len(files),
        "installer": installer_record,
        "native_binary_count": len(native_binaries),
        "native_binaries": native_binaries,
        "errors": errors,
    }


def inspect(distribution: Path, version: str) -> list[str]:
    return list(inspect_distribution(distribution, version)["errors"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--distribution", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--forbidden-path", default="")
    parser.add_argument("--installer", type=Path)
    args = parser.parse_args()
    report = inspect_distribution(
        args.distribution,
        args.version,
        forbidden_path=args.forbidden_path,
        installer=args.installer,
    )
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    for error in report["errors"]:
        print(error, file=sys.stderr)
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
