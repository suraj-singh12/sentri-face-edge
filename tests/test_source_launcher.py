from __future__ import annotations

from pathlib import Path
import os
import sys
import types

import pytest

from scripts.reset_macos_dev_authority import reset
import scripts.reset_macos_dev_authority as reset_module


def test_macos_source_launcher_has_an_explicit_non_product_authority() -> None:
    launcher = (Path(__file__).resolve().parents[1] / "run.sh").read_text(encoding="utf-8")

    assert "SentriFace-Dev" in launcher
    assert "SENTRIFACE_DEV_DATA_DIR" in launcher
    assert 'PRODUCTION_DATA_DIR="$HOME/Library/Application Support/SentriFace"' in launcher
    assert "Refusing to use the installed-product data directory" in launcher
    assert '--data-dir "$DEV_DATA_DIR"' in launcher
    assert "--runtime dev" in launcher
    assert "--runtime onnx --allow-unpackaged-source-onnx" in launcher


def test_source_launcher_bootstraps_only_when_needed_and_has_safe_reset() -> None:
    launcher = (Path(__file__).resolve().parents[1] / "run.sh").read_text(encoding="utf-8")

    assert "python3.12 python3.11" in launcher
    assert ".sentriface-dependencies.sha256" in launcher
    assert 'pip install -e ".[test]"' in launcher
    assert "Type RESET-DEV to continue" in launcher
    assert "reset is available only for the default SentriFace-Dev data directory" in launcher
    assert 'DEFAULT_DEV_DATA_DIR="$HOME/Library/Application Support/SentriFace-Dev"' in launcher
    assert '"$DEV_DATA_DIR:A" != "$DEFAULT_DEV_DATA_DIR:A"' in launcher
    assert 'reset_macos_dev_authority.py" "$DEV_DATA_DIR"' in launcher


@pytest.mark.skipif(os.name == "nt", reason="POSIX UID/ownership reset behavior")
def test_reset_removes_readonly_dev_bundle_and_only_dev_keys(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    support = tmp_path / "Library" / "Application Support"
    dev = support / "SentriFace-Dev"
    production = support / "SentriFace"
    bundle = dev / "models" / ".model-authority" / "bundle"
    bundle.mkdir(parents=True)
    (bundle / "model.onnx").write_bytes(b"model")
    (dev / "accounts.db").write_bytes(b"db")
    production.mkdir(parents=True)
    (production / "keep.db").write_bytes(b"production")
    (dev / "link-to-product").symlink_to(production, target_is_directory=True)
    (bundle / "model.onnx").chmod(0o444)
    bundle.chmod(0o555)
    deleted = []
    fake_keyring = types.ModuleType("keyring")
    fake_errors = types.ModuleType("keyring.errors")
    fake_errors.PasswordDeleteError = type("PasswordDeleteError", (Exception,), {})
    fake_keyring.delete_password = lambda service, account: deleted.append((service, account))
    monkeypatch.setitem(sys.modules, "keyring", fake_keyring)
    monkeypatch.setitem(sys.modules, "keyring.errors", fake_errors)

    reset(dev)
    assert not dev.exists()
    assert (production / "keep.db").read_bytes() == b"production"
    assert len(deleted) == 2
    assert all(account == deleted[0][1] for _, account in deleted)


def test_reset_refuses_other_authorities_and_symlink_root(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    support = tmp_path / "Library" / "Application Support"
    support.mkdir(parents=True)
    production = support / "SentriFace"
    production.mkdir()
    dev = support / "SentriFace-Dev"
    dev.symlink_to(production, target_is_directory=True)
    with pytest.raises(ValueError):
        reset(dev)
    with pytest.raises(ValueError):
        reset(production)
    assert production.exists()


def test_reset_refuses_symlinked_parent(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    real_library = tmp_path / "real-library"
    (real_library / "Application Support" / "SentriFace-Dev").mkdir(parents=True)
    (tmp_path / "Library").symlink_to(real_library, target_is_directory=True)
    with pytest.raises(ValueError):
        reset(tmp_path / "Library" / "Application Support" / "SentriFace-Dev")
    assert (real_library / "Application Support" / "SentriFace-Dev").exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX UID/ownership reset behavior")
def test_reset_keeps_database_key_if_file_removal_fails(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    dev = tmp_path / "Library" / "Application Support" / "SentriFace-Dev"
    dev.mkdir(parents=True)
    (dev / "sentriface.db").write_bytes(b"encrypted database")
    deleted = []
    fake_keyring = types.ModuleType("keyring")
    fake_errors = types.ModuleType("keyring.errors")
    fake_errors.PasswordDeleteError = type("PasswordDeleteError", (Exception,), {})
    fake_keyring.delete_password = lambda *args: deleted.append(args)
    monkeypatch.setitem(sys.modules, "keyring", fake_keyring)
    monkeypatch.setitem(sys.modules, "keyring.errors", fake_errors)
    monkeypatch.setattr(reset_module.shutil, "rmtree", lambda path: (_ for _ in ()).throw(OSError("injected")))

    with pytest.raises(OSError, match="injected"):
        reset(dev)
    assert (dev / "sentriface.db").read_bytes() == b"encrypted database"
    assert deleted == []
