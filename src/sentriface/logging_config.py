# sentriface/logging_config.py

from loguru import logger
import sys

def setup_logging(debug: bool = True) -> None:
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

    logger.add(
        "logs/sentriface.log",
        rotation="10 MB",
        retention="7 days",
        level=level,
        backtrace=debug,
        # Loguru's diagnostic mode can serialize local variables from a failing
        # inference frame, including images, tensors, and embeddings.
        diagnose=False,
    )
