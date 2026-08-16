from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--distribution", type=Path, required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    if sys.platform != "win32":
        print("Windows packaged smoke is unavailable on this platform", file=sys.stderr)
        return 2
    executable = args.distribution / "SentriFaceEdge.exe"
    if not executable.is_file():
        print("Packaged executable is missing", file=sys.stderr)
        return 1
    result = subprocess.run(
        [str(executable), "--version"],
        capture_output=True,
        text=True,
        timeout=30,
        env={key: value for key, value in os.environ.items() if not key.startswith("PYTHON")},
    )
    output = (result.stdout + result.stderr).strip()
    if result.returncode != 0 or args.version not in output:
        print("Packaged version smoke failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
