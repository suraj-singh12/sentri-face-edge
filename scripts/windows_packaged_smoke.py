from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def _clean_environment() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("PYTHON")
        and key not in {"SENTRIFACE_DATA_DIR", "SENTRIFACE_MODEL_DIR"}
    }


def _run(command: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=_clean_environment(),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--distribution", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--detector-model", type=Path)
    parser.add_argument("--recognizer-model", type=Path)
    args = parser.parse_args()
    if sys.platform != "win32":
        print("Windows packaged smoke is unavailable on this platform", file=sys.stderr)
        return 2
    if bool(args.detector_model) != bool(args.recognizer_model):
        print("Both detector and recognizer test models are required", file=sys.stderr)
        return 2
    executable = args.distribution / "SentriFaceEdge.exe"
    if not executable.is_file():
        print("Packaged executable is missing", file=sys.stderr)
        return 1

    version = _run([str(executable), "--version"], timeout=30)
    output = (version.stdout + version.stderr).strip()
    if version.returncode != 0 or args.version not in output:
        print("Packaged version smoke failed", file=sys.stderr)
        return 1

    temporary = Path(
        tempfile.mkdtemp(prefix="sentriface-release-self-test-")
    ).resolve()
    internal_report = temporary / "packaged-runtime.json"
    command = [
        str(executable),
        "--release-self-test",
        "--data-dir",
        str(temporary / "data"),
        "--self-test-report",
        str(internal_report),
    ]
    if args.detector_model and args.recognizer_model:
        command.extend(
            [
                "--self-test-detector",
                str(args.detector_model.resolve(strict=True)),
                "--self-test-recognizer",
                str(args.recognizer_model.resolve(strict=True)),
            ]
        )
    try:
        result = _run(command, timeout=180)
        if result.returncode != 0:
            diagnostic = (result.stdout + result.stderr).strip()[-4000:]
            print(
                f"Packaged runtime self-test failed ({result.returncode}): {diagnostic}",
                file=sys.stderr,
            )
            return 1
        if not internal_report.is_file():
            print("Packaged runtime self-test did not produce evidence", file=sys.stderr)
            return 1
        report = json.loads(internal_report.read_text(encoding="utf-8"))
        if report.get("status") != "PASS":
            print("Packaged runtime self-test evidence is not PASS", file=sys.stderr)
            return 1
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    finally:
        shutil.rmtree(temporary, ignore_errors=False)
    if temporary.exists():
        print("Packaged runtime self-test temporary state remains", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
