from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    packages = []
    for distribution in importlib.metadata.distributions():
        metadata = distribution.metadata
        name = metadata.get("Name")
        if not name:
            continue
        license_expression = metadata.get("License-Expression") or metadata.get("License") or "UNKNOWN"
        packages.append({
            "name": name,
            "version": distribution.version,
            "license": license_expression[:500],
        })
    payload = {
        "contract": "sentriface.release-dependency-inventory",
        "contract_version": 1,
        "packages": sorted(packages, key=lambda item: item["name"].casefold()),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
