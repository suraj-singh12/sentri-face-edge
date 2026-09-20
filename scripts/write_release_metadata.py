from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--installer", type=Path, required=True)
    parser.add_argument("--application", type=Path, required=True)
    parser.add_argument("--inspection", type=Path, required=True)
    parser.add_argument("--runtime-report", type=Path, required=True)
    parser.add_argument("--dependencies", type=Path, required=True)
    parser.add_argument("--lockfile", type=Path, required=True)
    parser.add_argument("--development", action="store_true")
    parser.add_argument("--signed", action="store_true")
    args = parser.parse_args()

    installer = args.installer.resolve(strict=True)
    application = args.application.resolve(strict=True)
    evidence_paths = {
        "artifact_inspection": args.inspection.resolve(strict=True),
        "packaged_runtime": args.runtime_report.resolve(strict=True),
        "dependency_inventory": args.dependencies.resolve(strict=True),
        "release_lock": args.lockfile.resolve(strict=True),
    }
    inspection = json.loads(evidence_paths["artifact_inspection"].read_text(encoding="utf-8"))
    runtime = json.loads(evidence_paths["packaged_runtime"].read_text(encoding="utf-8"))
    if inspection.get("status") != "PASS":
        raise RuntimeError("Artifact inspection evidence is not PASS")
    if runtime.get("status") != "PASS":
        raise RuntimeError("Packaged runtime evidence is not PASS")

    payload = {
        "contract": "sentriface.release-provenance",
        "contract_version": 2,
        "version": args.version,
        "commit": _git("rev-parse", "HEAD"),
        "branch": _git("branch", "--show-current"),
        "tags_at_commit": sorted(filter(None, _git("tag", "--points-at", "HEAD").splitlines())),
        "working_tree_clean": not bool(_git("status", "--porcelain")),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "builder_platform": platform.platform(),
        "builder_python": platform.python_version(),
        "development_build": bool(args.development),
        "authenticode_signed": bool(args.signed),
        "production_accepted": bool(args.signed and not args.development),
        "models_bundled": False,
        "private_license_key_bundled": False,
        "target_architecture": inspection.get("expected_architecture"),
        "observed_architectures": inspection.get("architectures", []),
        "external_model_session_acceptance": runtime.get(
            "external_model_session_acceptance"
        ),
        "model_onboarding_acceptance": runtime.get("model_onboarding_acceptance"),
        "artifacts": [
            {
                "name": installer.name,
                "kind": "installer",
                "size": installer.stat().st_size,
                "sha256": _sha256(installer),
            },
            {
                "name": application.name,
                "kind": "standalone-application",
                "size": application.stat().st_size,
                "sha256": _sha256(application),
            },
        ],
        "evidence": {
            name: {
                "filename": path.name,
                "sha256": _sha256(path),
            }
            for name, path in evidence_paths.items()
        },
    }
    output = installer.with_suffix(installer.suffix + ".provenance.json")
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
