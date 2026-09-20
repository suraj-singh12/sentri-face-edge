from __future__ import annotations

import os
import sys
from pathlib import Path


APP_DIR_NAME = "SentriFace"
DEVELOPMENT_APP_DIR_NAME = "SentriFace-Dev"


def default_data_dir() -> Path:
    """Return a stable per-user data directory independent of the launch folder."""
    override = os.environ.get("SENTRIFACE_DATA_DIR")
    if override:
        return Path(override).expanduser()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return base / APP_DIR_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "sentriface"


def default_model_dir() -> Path:
    """Return the model directory, honoring an explicit environment override."""
    override = os.environ.get("SENTRIFACE_MODEL_DIR")
    if override:
        return Path(override).expanduser()
    return default_data_dir() / "models"


def source_development_data_dir() -> Path:
    """Return the deliberate source-development authority, never product state."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return base / DEVELOPMENT_APP_DIR_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / DEVELOPMENT_APP_DIR_NAME
    base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "sentriface-dev"


def default_log_dir(data_dir: Path | None = None) -> Path:
    return (data_dir or default_data_dir()) / "logs"
