from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--installer", type=Path, required=True)
    parser.add_argument("--development", action="store_true")
    args = parser.parse_args()
    installer = args.installer.resolve(strict=True)
    digest = hashlib.sha256(installer.read_bytes()).hexdigest()
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True,
    ).stdout.strip()
    payload = {
        "contract": "sentriface.release-provenance",
        "contract_version": 1,
        "version": args.version,
        "commit": commit,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "builder_platform": platform.platform(),
        "development_build": bool(args.development),
        "artifact": installer.name,
        "sha256": digest,
        "models_bundled": False,
        "private_license_key_bundled": False,
    }
    output = installer.with_suffix(installer.suffix + ".provenance.json")
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
