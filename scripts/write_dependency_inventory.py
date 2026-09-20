from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path


BUILD_TOOL_NAMES = {"Nuitka", "pip", "setuptools", "wheel", "zstandard", "ordered-set"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _compiled_top_level_modules(build_dir: Path, distribution: Path) -> set[str]:
    modules: set[str] = set()
    for source in build_dir.glob("module.*.c"):
        module = source.name[len("module.") : -len(".c")]
        top = module.split(".", 1)[0]
        if top and not top.startswith("__"):
            modules.add(top)
    for child in distribution.iterdir():
        if child.name.startswith("_") and child.suffix.casefold() not in {".pyd", ".dll"}:
            continue
        if child.is_dir():
            modules.add(child.name)
        elif child.suffix.casefold() == ".pyd":
            modules.add(child.stem)
    modules.add("sentriface")
    return modules


def _package_record(distribution: importlib.metadata.Distribution) -> dict[str, str]:
    metadata = distribution.metadata
    license_expression = (
        metadata.get("License-Expression")
        or metadata.get("License")
        or "UNKNOWN"
    )
    return {
        "name": metadata.get("Name") or "UNKNOWN",
        "version": distribution.version,
        "license": license_expression[:500],
    }


def build_inventory(
    build_dir: Path,
    distribution_dir: Path,
    lockfile: Path,
) -> dict:
    if not build_dir.is_dir():
        raise FileNotFoundError(f"Nuitka build directory is missing: {build_dir}")
    if not distribution_dir.is_dir():
        raise FileNotFoundError(
            f"Standalone distribution is missing: {distribution_dir}"
        )
    modules = _compiled_top_level_modules(build_dir, distribution_dir)
    package_map = {
        package.casefold(): names
        for package, names in importlib.metadata.packages_distributions().items()
    }
    included_names: set[str] = {"sentriface-edge"}
    evidence: dict[str, list[str]] = {}
    for module in sorted(modules, key=str.casefold):
        names = package_map.get(module.casefold(), [])
        if names:
            evidence[module] = sorted(set(names), key=str.casefold)
            included_names.update(names)

    bundled = []
    for name in sorted(included_names, key=str.casefold):
        try:
            bundled.append(_package_record(importlib.metadata.distribution(name)))
        except importlib.metadata.PackageNotFoundError:
            if name == "sentriface-edge":
                raise RuntimeError(
                    "The release environment must install the local SentriFace package"
                )
            raise

    build_tools = []
    for name in sorted(BUILD_TOOL_NAMES, key=str.casefold):
        try:
            build_tools.append(_package_record(importlib.metadata.distribution(name)))
        except importlib.metadata.PackageNotFoundError:
            continue

    return {
        "contract": "sentriface.release-dependency-inventory",
        "contract_version": 2,
        "scope": (
            "Packages mapped from modules compiled by Nuitka or copied into the "
            "standalone distribution; build tools are reported separately."
        ),
        "release_lock": {
            "filename": lockfile.name,
            "sha256": _sha256(lockfile),
        },
        "bundled_packages": sorted(
            bundled,
            key=lambda item: item["name"].casefold(),
        ),
        "build_tools": sorted(
            build_tools,
            key=lambda item: item["name"].casefold(),
        ),
        "module_distribution_evidence": evidence,
        "compiled_top_level_modules": sorted(modules, key=str.casefold),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--distribution", type=Path, required=True)
    parser.add_argument("--lockfile", type=Path, required=True)
    args = parser.parse_args()
    payload = build_inventory(
        args.build_dir,
        args.distribution,
        args.lockfile,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
