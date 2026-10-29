"""
T.A.G.A.P. - Centralized Configuration

Loads environment variables from .env file and exposes a singleton
`settings` object for use across the entire application.

Design notes:
- Uses python-dotenv for 12-factor-app compliance.
- All values have safe defaults so the app can boot in dev mode
  without a .env file present.
- No side effects on import beyond loading .env.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load .env if present (silent if missing)
load_dotenv()

# Project root (config.py lives in the root)
PROJECT_ROOT = Path(__file__).resolve().parent


def _get_bool(key: str, default: bool = False) -> bool:
    """Parse a boolean env var, tolerant of multiple truthy forms."""
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _get_int(key: str, default: int) -> int:
    """Parse an integer env var with a safe fallback."""
    raw = os.getenv(key)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_str(key: str, default: str) -> str:
    """Get a string env var with a safe fallback."""
    raw = os.getenv(key)
    return raw if raw is not None else default


@dataclass(frozen=True)
class Settings:
    """Immutable application settings."""

    # --- Application ---
    ENV: str = field(default_factory=lambda: _get_str("TAGAP_ENV", "development"))
    APP_NAME: str = field(default_factory=lambda: _get_str("TAGAP_APP_NAME", "T.A.G.A.P."))
    VERSION: str = field(default_factory=lambda: _get_str("TAGAP_VERSION", "0.1.0"))

    # --- Hardware Simulation ---
    USE_MOCK_RFID: bool = field(default_factory=lambda: _get_bool("USE_MOCK_RFID", True))
    USE_MOCK_SMS: bool = field(default_factory=lambda: _get_bool("USE_MOCK_SMS", True))

    # --- RFID ---
    RFID_PORT: str = field(default_factory=lambda: _get_str("RFID_PORT", "COM3"))
    RFID_BAUDRATE: int = field(default_factory=lambda: _get_int("RFID_BAUDRATE", 9600))
    RFID_TIMEOUT_SECONDS: int = field(default_factory=lambda: _get_int("RFID_TIMEOUT_SECONDS", 1))

    # --- GSM ---
    GSM_PORT: str = field(default_factory=lambda: _get_str("GSM_PORT", "COM4"))
    GSM_BAUDRATE: int = field(default_factory=lambda: _get_int("GSM_BAUDRATE", 115200))
    GSM_TIMEOUT_SECONDS: int = field(default_factory=lambda: _get_int("GSM_TIMEOUT_SECONDS", 5))

    # --- Database ---
    DATABASE_URL: str = field(
        default_factory=lambda: _get_str("DATABASE_URL", "sqlite:///data/tagap.db")
    )

    # --- System Rules ---
    DEDUPLICATION_WINDOW_SECONDS: int = field(
        default_factory=lambda: _get_int("DEDUPLICATION_WINDOW_SECONDS", 60)
    )
    CONFIRMATION_TIMEOUT_SECONDS: int = field(
        default_factory=lambda: _get_int("CONFIRMATION_TIMEOUT_SECONDS", 3)
    )
    SMS_RETRY_ATTEMPTS: int = field(default_factory=lambda: _get_int("SMS_RETRY_ATTEMPTS", 3))
    SMS_RETRY_BACKOFF_SECONDS: int = field(
        default_factory=lambda: _get_int("SMS_RETRY_BACKOFF_SECONDS", 2)
    )

    # --- Admin ---
    ADMIN_DEFAULT_PIN: str = field(default_factory=lambda: _get_str("ADMIN_DEFAULT_PIN", "1234"))

    # --- Logging ---
    LOG_LEVEL: str = field(default_factory=lambda: _get_str("LOG_LEVEL", "INFO").upper())
    LOG_FILE: str = field(default_factory=lambda: _get_str("LOG_FILE", "logs/tagap.log"))
    LOG_MAX_BYTES: int = field(default_factory=lambda: _get_int("LOG_MAX_BYTES", 5 * 1024 * 1024))
    LOG_BACKUP_COUNT: int = field(default_factory=lambda: _get_int("LOG_BACKUP_COUNT", 3))

    # --- Convenience properties ---
    @property
    def is_production(self) -> bool:
        return self.ENV.lower() == "production"

    @property
    def is_development(self) -> bool:
        return self.ENV.lower() == "development"

    @property
    def log_path(self) -> Path:
        """Absolute path to the log file."""
        p = Path(self.LOG_FILE)
        return p if p.is_absolute() else PROJECT_ROOT / p

    @property
    def db_path(self) -> Path:
        """Absolute path to the SQLite DB (parsed from DATABASE_URL)."""
        url = self.DATABASE_URL
        if url.startswith("sqlite:///"):
            raw = url.replace("sqlite:///", "", 1)
            p = Path(raw)
            return p if p.is_absolute() else PROJECT_ROOT / p
        return PROJECT_ROOT / "data" / "tagap.db"


# Singleton instance used everywhere in the app
settings = Settings()