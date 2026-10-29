"""
T.A.G.A.P. - Logging Setup

Provides a single, pre-configured logger used across the app.
Rotates log files to prevent disk exhaustion on a long-running kiosk.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from config import settings


_LOG_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s"
)
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_logger_initialized = False


def _build_formatter() -> logging.Formatter:
    return logging.Formatter(fmt=_LOG_FORMAT, datefmt=_DATE_FORMAT)


def setup_logger(name: str = "TAGAP") -> logging.Logger:
    """
    Configure and return the application logger.

    Idempotent: calling this multiple times will not add duplicate handlers.
    """
    global _logger_initialized

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, settings.LOG_LEVEL, logging.INFO))

    if _logger_initialized:
        return logger

    # Ensure log directory exists
    settings.log_path.parent.mkdir(parents=True, exist_ok=True)

    formatter = _build_formatter()

    # --- Rotating file handler ---
    file_handler = RotatingFileHandler(
        filename=str(settings.log_path),
        maxBytes=settings.LOG_MAX_BYTES,
        backupCount=settings.LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)

    # --- Console handler ---
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.DEBUG if settings.is_development else logging.INFO)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.propagate = False

    _logger_initialized = True
    logger.info(
        "Logger initialized | env=%s | level=%s | file=%s",
        settings.ENV,
        settings.LOG_LEVEL,
        settings.log_path,
    )
    return logger


# Convenience singleton
log = setup_logger()


def get_logger(name: str) -> logging.Logger:
    """
    Get a child logger that inherits the root handler.
    Use this in modules: `logger = get_logger(__name__)`
    """
    setup_logger()  # ensure root is initialized
    return logging.getLogger(name)