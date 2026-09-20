from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "wipe_clean_this_machine_installation_and_data.py"
SPEC = importlib.util.spec_from_file_location("sentriface_machine_sanitizer", SCRIPT)
assert SPEC and SPEC.loader
sanitizer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = sanitizer
SPEC.loader.exec_module(sanitizer)


def test_default_installation_credentials_require_exact_account_and_service(
    tmp_path: Path,
    monkeypatch,
) -> None:
    data_dir = tmp_path / "SentriFace"
    account = sanitizer._account_for_data_dir(data_dir)
    monkeypatch.setattr(
        sanitizer,
        "_credential_rows",
        lambda: [
            {
                "TargetName": sanitizer.STORAGE_CREDENTIAL_SERVICE,
                "UserName": account,
                "Type": 1,
            },
            {
                "TargetName": (
                    f"{account}@{sanitizer.RECOVERY_CREDENTIAL_SERVICE}"
                ),
                "UserName": account,
                "Type": 1,
            },
            {
                "TargetName": (
                    f"legacy-test@{sanitizer.STORAGE_CREDENTIAL_SERVICE}"
                ),
                "UserName": "legacy-test",
                "Type": 1,
            },
            {
                "TargetName": "unrelated service",
                "UserName": account,
                "Type": 1,
            },
        ],
    )

    resources = sanitizer._credential_resources(data_dir)

    owned = [item for item in resources if item.ownership == "OWNED"]
    ambiguous = [item for item in resources if item.ownership == "AMBIGUOUS"]
    assert len(owned) == 2
    assert {item.key for item in owned} == {
        f"credential:{sanitizer.STORAGE_CREDENTIAL_SERVICE}",
        f"credential:{sanitizer.RECOVERY_CREDENTIAL_SERVICE}",
    }
    assert len(ambiguous) == 1
    assert ambiguous[0].target.startswith("legacy-test@")


def test_same_service_with_another_account_is_ambiguous(
    tmp_path: Path,
    monkeypatch,
) -> None:
    data_dir = tmp_path / "SentriFace"
    monkeypatch.setattr(
        sanitizer,
        "_credential_rows",
        lambda: [
            {
                "TargetName": sanitizer.STORAGE_CREDENTIAL_SERVICE,
                "UserName": "unknown-account",
                "Type": 1,
            }
        ],
    )

    resources = sanitizer._credential_resources(data_dir)

    assert len(resources) == 1
    assert resources[0].ownership == "AMBIGUOUS"


def test_development_inventory_lists_only_exact_discovered_artifacts(
    tmp_path: Path,
) -> None:
    python_root = tmp_path / "Programs" / "Python" / "Python312"
    site_packages = python_root / "Lib" / "site-packages"
    scripts = python_root / "Scripts"
    site_packages.mkdir(parents=True)
    scripts.mkdir(parents=True)
    dist_info = site_packages / "sentriface_edge-2.0.0.dist-info"
    dist_info.mkdir()
    editable = site_packages / "__editable__.sentriface_edge-2.0.0.pth"
    editable.write_text("local source", encoding="utf-8")
    entry_point = scripts / "sentriface.exe"
    entry_point.write_bytes(b"launcher")
    (scripts / "unrelated.exe").write_bytes(b"unrelated")

    resources = sanitizer._development_resources(tmp_path)

    assert {Path(item.target) for item in resources} == {
        dist_info,
        editable,
        entry_point,
    }
    assert all(item.kind == "development-path" for item in resources)
    assert all(item.ownership == "OWNED" for item in resources)

def test_environment_root_is_never_accepted_as_a_deletion_target(
    monkeypatch,
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(Path(Path.cwd().anchor)))

    try:
        sanitizer._known_environment_directory("LOCALAPPDATA")
    except RuntimeError as exc:
        assert "unsafe LOCALAPPDATA" in str(exc)
    else:
        raise AssertionError("filesystem root must be refused")
