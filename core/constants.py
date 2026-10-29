"""
T.A.G.A.P. - Application Constants

Central place for enums and magic strings. NEVER hardcode these
values elsewhere in the codebase.
"""

from __future__ import annotations

from enum import Enum


class CardType(str, Enum):
    """The 4 card types in the T.A.G.A.P. system."""

    SAFE = "SAFE"
    ASSIST = "ASSIST"
    DANGER = "DANGER"
    ADMIN = "ADMIN"


class AlertStatus(str, Enum):
    """Status of an alert record."""

    PENDING = "PENDING"
    QUEUED = "QUEUED"
    SENT = "SENT"
    PARTIAL = "PARTIAL"  # some SMS sent, some failed
    FAILED = "FAILED"


class SmsStatus(str, Enum):
    """Status of a single SMS message in the queue."""

    PENDING = "PENDING"
    SENDING = "SENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class AppState(str, Enum):
    """High-level UI state for the state machine."""

    STANDBY = "STANDBY"
    IDENTIFYING = "IDENTIFYING"
    CONFIRMING = "CONFIRMING"
    QUEUING = "QUEUING"
    SETTINGS = "SETTINGS"


# --- Hardware / Adapter constants ---
RFID_READ_TIMEOUT_MS = 1000
SMS_MAX_LENGTH = 160
SMS_NEWLINE = "\r\n"

# --- Audit event names (used in analytics) ---
EVENT_CARD_SCANNED = "CARD_SCANNED"
EVENT_CARD_REJECTED_DUPLICATE = "CARD_REJECTED_DUPLICATE"
EVENT_ALERT_CONFIRMED = "ALERT_CONFIRMED"
EVENT_ALERT_CANCELLED = "ALERT_CANCELLED"
EVENT_ALERT_QUEUED = "ALERT_QUEUED"
EVENT_SMS_SENT = "SMS_SENT"
EVENT_SMS_FAILED = "SMS_FAILED"
EVENT_ADMIN_ACCESS = "ADMIN_ACCESS"
EVENT_SYSTEM_BOOT = "SYSTEM_BOOT"
EVENT_SYSTEM_SHUTDOWN = "SYSTEM_SHUTDOWN"