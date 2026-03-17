import logging
import os
from logging.handlers import RotatingFileHandler

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "storage")
LOG_FILE = os.path.join(LOG_DIR, "hh_bot.log")
LOG_FORMAT = "[%(asctime)s] %(levelname)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logger() -> logging.Logger:
    os.makedirs(LOG_DIR, exist_ok=True)

    logger = logging.getLogger("hh_bot")
    logger.setLevel(logging.INFO)

    if logger.handlers:
        return logger

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
    logger.addHandler(console)

    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
    logger.addHandler(file_handler)

    return logger
