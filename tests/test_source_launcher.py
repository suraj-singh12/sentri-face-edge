from __future__ import annotations

from pathlib import Path


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
    assert 'rm -rf -- "$DEV_DATA_DIR"' in launcher
