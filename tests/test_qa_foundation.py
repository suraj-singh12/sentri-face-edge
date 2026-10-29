"""QA mechanism tests, explicitly not biometric or browser acceptance."""
import importlib.util
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("qa", ROOT / "scripts/qa_foundation.py")
qa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qa)


def test_qa_o01_correct_and_wrong_expectation():
    actual = {"participants": ["person-a"], "location": "London", "date": "2026-10-29"}
    qa.assert_expected({"participants": ["person-a"], "location": "London"}, actual)
    with pytest.raises(AssertionError, match=r"result.participants\[0\]: expected 'person-b', actual 'person-a'"):
        qa.assert_expected({"participants": ["person-b"]}, actual)
    with pytest.raises(AssertionError, match="participants"):
        qa.assert_expected({"participants": []}, actual)


def test_qa_d01_disposable_repeat():
    paths = []
    for _ in range(2):
        with qa.disposable_data() as root:
            paths.append(root)
            assert not list(root.iterdir())
            (root / "example").write_text("QA only")
        assert not root.exists()
    assert paths[0] != paths[1]


def test_registry_targets_exist():
    registry = json.loads((ROOT / "tests/qa_coverage.json").read_text())
    ids = [row["id"] for row in registry["cases"]]
    assert len(ids) == len(set(ids))
    for row in registry["cases"]:
        assert row["status"] in {"covered", "partial", "untested", "unimplemented"}
        for target in row["tests"]:
            assert (ROOT / target.split("::")[0]).is_file(), target


def test_verified_pair_rejects_search_labels(tmp_path, monkeypatch):
    import sys
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    (tmp_path / "manifest.json").write_text(json.dumps({"version": 1, "photos": [
        {"actor": "Chris Evans", "reviewed": False, "file": "actor/no.jpg"}
    ]}))
    with pytest.raises(ValueError, match="distinct visually verified"):
        qa.verified_pair(tmp_path, "Chris Evans")


def test_verified_pair_rejects_same_photo(tmp_path, monkeypatch):
    import hashlib
    import cv2
    import numpy as np
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    blob = cv2.imencode(".jpg", np.zeros((120, 120, 3), dtype=np.uint8))[1].tobytes()
    (tmp_path / "actor").mkdir()
    (tmp_path / "actor/a.jpg").write_bytes(blob)
    base = dict(license="QA mechanism only", author="test", source_record="synthetic validation bytes, no identity claim", reference_no_context=True, actor="Chris Evans", reviewed=True, reviewer="local operator", review_notes="Visual review", file="actor/a.jpg", sha256=hashlib.sha256(blob).hexdigest())
    (tmp_path / "manifest.json").write_text(json.dumps({"version": 1, "photos": [dict(base, split="enrollment"), dict(base, split="query")]}))
    with pytest.raises(ValueError, match="distinct visually verified"):
        qa.verified_pair(tmp_path, "Chris Evans")
