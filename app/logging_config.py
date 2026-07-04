import logging
import os
from app.config import LOG_DIR, LOG_FILE


def setup_logging() -> logging.Logger:
    os.makedirs(LOG_DIR, exist_ok=True)

    logger = logging.getLogger("claims_api")
    logger.setLevel(logging.INFO)

    if logger.handlers:
        # Avoid duplicate handlers if setup_logging() runs more than once
        # (happens under uvicorn's reloader).
        return logger

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


logger = setup_logging()
