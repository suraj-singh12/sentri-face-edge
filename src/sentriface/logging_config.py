from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from sentriface.paths import default_log_dir


def setup_logging(debug: bool = True, log_dir: Path | None = None) -> None:
    logger.remove()
    level = "DEBUG" if debug else "INFO"

    logger.add(
        sys.stderr,
        level=level,
        format=(
            "<green>{time:HH:mm:ss}</green> | "
            "<level>{level:8}</level> | "
            "<cyan>{file}:{line}</cyan> | "
            "<cyan>{function}</cyan> | "
            "<level>{message}</level>"
        ),
    )

    resolved_log_dir = log_dir or default_log_dir()
    try:
        resolved_log_dir.mkdir(parents=True, exist_ok=True)
        logger.add(
            resolved_log_dir / "sentriface.log",
            rotation="10 MB",
            retention="7 days",
            level=level,
            backtrace=debug,
            # Never serialize frame locals; they may contain images or embeddings.
            diagnose=False,
        )
    except OSError as exc:
        logger.warning("File logging is unavailable: {}", exc)