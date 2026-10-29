"""
T.A.G.A.P. - Alert Result DTOs

Plain dataclasses returned by AlertService. UI depends on these, not on ORM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from core.constants import CardType


class AlertOutcome(str, Enum):
    """High-level outcome of a card scan."""

    NEEDS_CONFIRMATION = "NEEDS_CONFIRMATION"   # Status card OK → show countdown
    ADMIN_ACCESS = "ADMIN_ACCESS"               # Admin card → open settings
    REJECTED_UNKNOWN = "REJECTED_UNKNOWN"       # UID not in DB
    REJECTED_DUPLICATE = "REJECTED_DUPLICATE"   # Within dedup window
    REJECTED_INACTIVE = "REJECTED_INACTIVE"     # Card disabled
    ERROR = "ERROR"                             # Hardware/DB error


@dataclass(frozen=True)
class AlertResult:
    """Result returned by AlertService.scan_card() and .execute_alert()."""

    outcome: AlertOutcome
    card_uid: str = ""
    card_type: CardType | None = None
    room_id: int | None = None
    room_name: str = ""
    wing: str = ""
    school_name: str = ""
    school_hotline: str = ""
    alert_id: int | None = None
    sms_queued: int = 0
    scan_ts: datetime | None = None
    error_message: str = ""

    @property
    def is_success(self) -> bool:
        return self.outcome in (AlertOutcome.NEEDS_CONFIRMATION, AlertOutcome.ADMIN_ACCESS)