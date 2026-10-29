"""Offline QA primitives. No application/biometric acceptance is implied by these checks."""
from __future__ import annotations
import argparse
import hashlib
import json
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def assert_expected(expected, actual, path="result"):
    """Compare independently supplied truth; never calculate truth from actual output.

    Objects select fields; arrays are exact and ordered. Missing and extra list
    entries fail. Domain adapters must supply full participant/evidence lists.
    """
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            raise AssertionError(f"{path}: expected object, actual {type(actual).__name__}")
        for key, value in expected.items():
            if key not in actual:
                raise AssertionError(f"{path}.{key}: missing; expected {value!r}")
            assert_expected(value, actual[key], f"{path}.{key}")
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(expected) != len(actual):
            raise AssertionError(f"{path}: expected {expected!r}, actual {actual!r}")
        for index, value in enumerate(expected):
            assert_expected(value, actual[index], f"{path}[{index}]")
    elif type(expected) is not type(actual) or expected != actual:
        raise AssertionError(f"{path}: expected {expected!r}, actual {actual!r}")


@contextmanager
def disposable_data():
    # No caller-selected reset target: cannot delete a user's existing authority.
    with tempfile.TemporaryDirectory(prefix="sentriface-qa-") as directory:
        root = Path(directory)
        root.chmod(0o700)
        yield root


def verified_pair(root: Path, actor: str):
    from fetch_marvel_photos import load_manifest, photo_path, image_valid
    manifest = load_manifest(root / "manifest.json")
    rows = []
    for row in manifest["photos"]:
        if row.get("actor") != actor or row.get("reviewed") is not True:
            continue
        if not row.get("reviewer") or not row.get("review_notes"):
            raise ValueError("Verified labels require reviewer and review notes")
        content = photo_path(root, row["file"]).read_bytes()
        if hashlib.sha256(content).hexdigest() != row.get("sha256") or not image_valid(content, Path(row["file"]).suffix):
            raise ValueError("Verified photograph is invalid or changed")
        rows.append(row)
    enrollment = [r for r in rows if r.get("split") == "enrollment"]
    queries = [r for r in rows if r.get("split") == "query"]
    if not enrollment or not queries or enrollment[0]["sha256"] == queries[0]["sha256"]:
        raise ValueError("Need distinct visually verified enrollment and query photographs")
    return enrollment[0], queries[0]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test", default="QA-J01", choices=["QA-J01"])
    parser.add_argument("--fixtures", type=Path, default=ROOT / "qa-fixtures/marvel-actors")
    parser.add_argument("--actor", default="Chris Evans")
    args = parser.parse_args(argv)
    reasons = []
    try:
        pair = verified_pair(args.fixtures, args.actor)
        hashes = [row["sha256"] for row in pair]
    except (ValueError, OSError) as exc:
        reasons.append(str(exc)); hashes = []
    # Until actual browser actions, admission/runtime attestation and domain read
    # adapters exist, preflight must never turn green even with valid fixtures.
    reasons.append("Browser/real-ONNX journey and persisted People/Event/World adapters not implemented")
    report = {
        "test_id": args.test, "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)),
        "outcome": "BLOCKED", "foundation": "PARTIAL", "fixture_hashes": hashes,
        "model_hashes": [], "inference_executed": False, "reasons": reasons,
    }
    print(json.dumps(report, indent=2))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
