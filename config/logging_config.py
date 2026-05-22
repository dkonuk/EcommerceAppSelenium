"""
Logging configuration for test framework.

Sets up structured logging with console and file handlers.
Suppresses noisy third-party library logs (Selenium, urllib3, etc.)

Usage:
    from config.logging_config import setup_logging

# Basic setup
setup_logging()

# Custom configuration
setup_logging(log_level="DEBUG", log_file="logs/debug.log")
"""

import logging
import sys
from pathlib import Path

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

NOISY_LOGGERS = [
    "selenium",
    "urllib3",
    "selenium.webdriver.remote.remote_connection",
]

def setup_logging(log_level="INFO", log_file=None, console_output=True):

    root_logger = logging.getLogger()

    root_logger.handlers.clear()
    # Set log level
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    root_logger.setLevel(numeric_level)

    # Create formatter
    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    # Console handler
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    if log_file:
        # Ensure log directory exists
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # Create file handler
        file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    for logg_name in NOISY_LOGGERS:
        logging.getLogger(logg_name).setLevel(logging.WARNING)

    logger = logging.getLogger(__name__)
    logger.debug(f"Logging configured: level={log_level}"
                 f" file={log_file}"
                 f" console={console_output}")



__all__ = ["setup_logging"]