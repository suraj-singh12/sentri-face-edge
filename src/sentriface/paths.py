from __future__ import annotations

import os
import sys
from pathlib import Path


APP_DIR_NAME = "SentriFace"
WINDOWS_PRODUCT_DIR = "SentriFace Edge"


def packaged_windows() -> bool:
    """Return True when running as a compiled Windows application."""
    return sys.platform == "win32" and (
        "__compiled__" in globals()
        or bool(getattr(sys, "frozen", False))
    )


def install_dir() -> Path:
    """Return the immutable application installation directory."""

    override = os.environ.get("SENTRIFACE_INSTALL_DIR")
    if override:
        return Path(override).expanduser()

    if packaged_windows():
        return Path(sys.executable).resolve().parent

    # Development/source checkout.
    return Path(__file__).resolve().parents[2]


def default_data_dir() -> Path:
    """
    Return the root directory for mutable SentriFace data.

    Packaged Windows:
        C:\\ProgramData\\SentriFace Edge

    Development Windows:
        %LOCALAPPDATA%\\SentriFace
    """

    override = os.environ.get("SENTRIFACE_DATA_DIR")
    if override:
        return Path(override).expanduser()

    if sys.platform == "win32":
        if packaged_windows():
            base = Path(
                os.environ.get("PROGRAMDATA")
                or r"C:\ProgramData"
            )
            return base / WINDOWS_PRODUCT_DIR

        base = Path(
            os.environ.get("LOCALAPPDATA")
            or Path.home() / "AppData" / "Local"
        )
        return base / APP_DIR_NAME

    if sys.platform == "darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / APP_DIR_NAME
        )

    base = Path(
        os.environ.get("XDG_DATA_HOME")
        or Path.home() / ".local" / "share"
    )
    return base / "sentriface"


def database_dir(data_dir: Path | None = None) -> Path:
    """
    Return the database directory.

    Packaged Windows:
        C:\\ProgramData\\SentriFace Edge\\database

    Development:
        existing data root, preserving current behaviour
    """

    root = data_dir or default_data_dir()

    if packaged_windows():
        return root / "database"

    return root


def managed_data_dir(data_dir: Path | None = None) -> Path:
    """
    Return the directory for mutable managed application data.

    Packaged Windows:
        C:\\ProgramData\\SentriFace Edge\\data

    Development:
        existing data root
    """

    root = data_dir or default_data_dir()

    if packaged_windows():
        return root / "data"

    return root


def default_log_dir(data_dir: Path | None = None) -> Path:
    """Return the application log directory."""

    return (data_dir or default_data_dir()) / "logs"


def default_model_dir() -> Path:
    """
    Return the model/runtime resource directory.

    Packaged Windows:
        <install>\\runtime\\core

    Development:
        <data-dir>\\models

    SENTRIFACE_MODEL_DIR always overrides the default.
    """

    override = os.environ.get("SENTRIFACE_MODEL_DIR")
    if override:
        return Path(override).expanduser()

    if packaged_windows():
        return install_dir() / "runtime" / "core"

    return default_data_dir() / "models"


def default_detector_model() -> Path:
    """Return the detector model resource."""

    if packaged_windows():
        return default_model_dir() / "c01.dat"

    return default_model_dir() / "detector.onnx"


def default_recognizer_model() -> Path:
    """Return the recognizer model resource."""

    if packaged_windows():
        return default_model_dir() / "c02.dat"

    return default_model_dir() / "recognizer.onnx"