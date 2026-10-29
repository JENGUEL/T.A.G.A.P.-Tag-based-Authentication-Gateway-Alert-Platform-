"""
T.A.G.A.P. - Custom Exceptions

All application-specific exceptions live here. This allows callers
to catch specific failure types instead of generic Exception.
"""

from __future__ import annotations


class TagapException(Exception):
    """Base class for all T.A.G.A.P. exceptions."""

    def __init__(self, message: str, *, context: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.context = context or {}


# --- Hardware exceptions ---
class HardwareError(TagapException):
    """Base for hardware-related failures (RFID, GSM, serial)."""


class RfidReadError(HardwareError):
    """Raised when the RFID reader cannot read a card."""


class RfidConnectionError(HardwareError):
    """Raised when the RFID serial port is unavailable."""


class GsmConnectionError(HardwareError):
    """Raised when the GSM module serial port is unavailable."""


class GsmSendError(HardwareError):
    """Raised when an SMS fails to send via the GSM module."""


# --- Domain / business exceptions ---
class UnknownCardError(TagapException):
    """Raised when a scanned card UID is not registered."""


class InvalidAdminPinError(TagapException):
    """Raised when the admin PIN is incorrect."""


class DuplicateAlertError(TagapException):
    """Raised when the same card is scanned within the dedup window."""


# --- Persistence exceptions ---
class DatabaseError(TagapException):
    """Raised for database-layer failures."""


class RecordNotFoundError(DatabaseError):
    """Raised when a requested DB record does not exist."""