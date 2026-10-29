"""
T.A.G.A.P. - Hardware Abstraction Interfaces (Ports)

Business logic depends ONLY on these abstract classes.
Concrete adapters (mock/real) implement them.

This is the Ports & Adapters (Hexagonal) pattern.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


# ============================================================
# RFID Service (Port)
# ============================================================

class IRfidService(ABC):
    """
    Port for RFID readers.

    Contract:
    - `read_card()` returns a card UID string, or None if no card.
    - Must NOT raise on normal "no card" flow.
    - Must raise RfidConnectionError if the port is closed.
    - Must be safe to call repeatedly in a loop.
    """

    @abstractmethod
    def open(self) -> None:
        """Open the serial port / attach to hardware."""

    @abstractmethod
    def close(self) -> None:
        """Cleanly release hardware resources."""

    @abstractmethod
    def read_card(self, timeout_seconds: float = 1.0) -> Optional[str]:
        """
        Block up to `timeout_seconds` waiting for a card.

        Returns:
            - Card UID (str) if a card was read.
            - None if the timeout elapsed with no card.
        """

    @abstractmethod
    def is_connected(self) -> bool:
        """Return True if the reader is ready to serve reads."""


# ============================================================
# SMS Service (Port)
# ============================================================

@dataclass(frozen=True)
class SmsResult:
    """Structured result of a single SMS send attempt."""

    success: bool
    phone_number: str
    message: str
    reason: str = ""      # Human-readable failure reason (empty on success)
    raw_response: str = ""  # Raw modem response (for audit)


class ISmsService(ABC):
    """
    Port for GSM/SMS modules.

    Contract:
    - `send_sms()` returns SmsResult. Never raises on normal failures.
    - Raises GsmConnectionError ONLY if the module is not open.
    - Must respect timeout_seconds per send attempt.
    """

    @abstractmethod
    def open(self) -> None:
        """Open the serial port to the GSM module."""

    @abstractmethod
    def close(self) -> None:
        """Cleanly release hardware resources."""

    @abstractmethod
    def send_sms(self, phone_number: str, message: str) -> SmsResult:
        """Attempt to send one SMS. Never raises on normal failure."""

    @abstractmethod
    def is_connected(self) -> bool:
        """Return True if the modem is ready."""

    @abstractmethod
    def signal_strength(self) -> Optional[int]:
        """
        Return signal strength (0-31, or 99 if unknown).
        Returns None if the modem doesn't support CSQ or is offline.
        """