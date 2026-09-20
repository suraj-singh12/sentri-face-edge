from __future__ import annotations

import json
from pathlib import Path

import pytest

from sentriface.release_self_test import run_release_self_test
from sentriface.secure_storage import KEYRING_SERVICE, _keyring_account


def test_release_self_test_exercises_runtime_and_cleans_owned_credential(
    tmp_path: Path,
    test_keyring,
) -> None:
    pytest.importorskip("sqlcipher3")
    pytest.importorskip("cv2")
    pytest.importorskip("onnxruntime")
    data_dir = tmp_path / "sentriface-release-self-test-unit" / "data"
    report_path = tmp_path / "runtime-report.json"

    report = run_release_self_test(data_dir, report_path)

    assert report["status"] == "PASS"
    assert report["external_model_session_acceptance"] == "PENDING_NO_INPUTS"
    assert report["model_onboarding_acceptance"] == "PENDING_NOT_EXERCISED"
    names = {item["name"] for item in report["checks"]}
    assert {
        "windows-keyring-create-retrieve",
        "sqlcipher-encrypted-database",
        "secure-file-round-trip",
        "opencv-native-operation",
        "onnxruntime-cpu-provider",
        "loopback-http-and-frontend",
        "clean-shutdown-and-instance-lock-release",
        "windows-keyring-owned-cleanup",
    } <= names
    assert (
        test_keyring.get_password(KEYRING_SERVICE, _keyring_account(data_dir))
        is None
    )
    assert json.loads(report_path.read_text(encoding="utf-8"))["status"] == "PASS"


def test_release_self_test_refuses_an_unowned_data_root(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="explicitly test-owned"):
        run_release_self_test(tmp_path / "ordinary", tmp_path / "report.json")
