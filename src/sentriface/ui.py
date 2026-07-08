from __future__ import annotations
from sentriface.api_server import main

# Logger setup START
from sentriface.logging_config import setup_logging
from loguru import logger
setup_logging(debug=True)
logger.info("Starting Sentriface CLI")
# Logger setup END

if __name__ == "__main__":
    raise SystemExit(main())
