"""
T.A.G.A.P. - Alert Service (The Orchestrator)

Responsible for the end-to-end alert lifecycle:
1. scan_card(uid)              → classify the card
2. execute_alert(uid, scan_ts) → atomically create alert + SMS queue
3. get_status()                → for UI polling

Design principles:
- Never raises on normal business flow (returns AlertResult).
- Raises only for programming errors (assert / TypeError).
- All DB writes inside a single transaction per call.
- All datetimes are timezone-aware (UTC) in memory; the repository
  layer converts to naive-UTC at the DB boundary.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

from config import settings
from core.constants import (
    EVENT_ADMIN_ACCESS,
    EVENT_ALERT_QUEUED,
    EVENT_CARD_REJECTED_DUPLICATE,
    EVENT_CARD_SCANNED,
    CardType,
)
from core.time_utils import utc_now
from data.database import get_db
from data.repositories import (
    AlertRepository,
    AnalyticsRepository,
    AuditLogRepository,
    CardRepository,
    DeduplicationChecker,
    ParentRepository,
    PoliceStationRepository,
    SmsQueueRepository,
    SmsTemplateRepository,
)
from models import Room
from models.sms_result_dto import AlertOutcome, AlertResult

logger = logging.getLogger(__name__)


class AlertService:
    """
    Stateless service — safe to instantiate per-request or as a singleton.
    All state lives in the DB.
    """

    # ============================================================
    # Phase 1: Scan card (fast, read-only)
    # ============================================================

    @staticmethod
    def scan_card(uid: str) -> AlertResult:
        """
        Classify a card UID.

        Returns:
        - ADMIN_ACCESS        → UI opens settings
        - NEEDS_CONFIRMATION  → UI shows countdown
        - REJECTED_*          → UI shows brief error toast
        - ERROR               → hardware/DB failure
        """
        scan_ts = utc_now()

        if not uid or not uid.strip():
            return AlertResult(
                outcome=AlertOutcome.ERROR,
                error_message="Empty UID",
                scan_ts=scan_ts,
            )

        uid = uid.strip()

        # --- 1. Look up card ---
        try:
            card = CardRepository.get_by_uid(uid)
        except Exception as exc:
            logger.exception("Card lookup failed for %s", uid)
            return AlertResult(
                outcome=AlertOutcome.ERROR,
                card_uid=uid,
                error_message=f"DB error: {exc}",
                scan_ts=scan_ts,
            )

        # --- 2. Unknown or inactive card ---
        if card is None:
            logger.warning("Unknown card scanned: %s", uid)
            _audit(EVENT_CARD_SCANNED, {"uid": uid, "result": "unknown"})
            return AlertResult(
                outcome=AlertOutcome.REJECTED_UNKNOWN,
                card_uid=uid,
                scan_ts=scan_ts,
            )

        card_type = card.card_type
        room: Room = card.room
        school = room.school

        # --- 3. Admin card → bypass everything ---
        if card_type == CardType.ADMIN:
            logger.info("Admin card scanned: %s", uid)
            _audit(EVENT_ADMIN_ACCESS, {"uid": uid})
            return AlertResult(
                outcome=AlertOutcome.ADMIN_ACCESS,
                card_uid=uid,
                card_type=card_type,
                room_id=room.id,
                room_name=room.name,
                school_name=school.name,
                scan_ts=scan_ts,
            )

        # --- 4. Status card: dedup check ---
        try:
            with get_db() as db:
                is_dup = DeduplicationChecker.is_duplicate(
                    db,
                    uid,
                    window_seconds=settings.DEDUPLICATION_WINDOW_SECONDS,
                )
        except Exception as exc:
            logger.exception("Dedup check failed for %s", uid)
            return AlertResult(
                outcome=AlertOutcome.ERROR,
                card_uid=uid,
                error_message=f"DB error: {exc}",
                scan_ts=scan_ts,
            )

        if is_dup:
            logger.info("Duplicate scan rejected: %s", uid)
            _audit(EVENT_CARD_REJECTED_DUPLICATE, {"uid": uid})
            return AlertResult(
                outcome=AlertOutcome.REJECTED_DUPLICATE,
                card_uid=uid,
                card_type=card_type,
                room_id=room.id,
                room_name=room.name,
                scan_ts=scan_ts,
            )

        # --- 5. OK: needs confirmation ---
        _audit(EVENT_CARD_SCANNED, {"uid": uid, "result": "needs_confirmation"})
        logger.info("Card %s (%s) → needs confirmation", uid, card_type.value)
        return AlertResult(
            outcome=AlertOutcome.NEEDS_CONFIRMATION,
            card_uid=uid,
            card_type=card_type,
            room_id=room.id,
            room_name=room.name,
            wing=room.wing,
            school_name=school.name,
            school_hotline=school.hotline,
            scan_ts=scan_ts,
        )

    # ============================================================
    # Phase 2: Execute alert (transactional, writes)
    # ============================================================

    @staticmethod
    def execute_alert(
        uid: str,
        scan_ts: datetime,
        *,
        confirmed_at: Optional[datetime] = None,
    ) -> AlertResult:
        """
        Atomically create:
        - Alert row
        - Parent SMS rows (one per parent)
        - Police SMS rows (one per police station for the school)
        - Analytics row
        - Audit log entry

        Returns AlertResult with alert_id and sms_queued count.
        """
        confirmed_at = confirmed_at or utc_now()
        queued_at = utc_now()

        # --- 1. Re-lookup card (defense against race) ---
        try:
            card = CardRepository.get_by_uid(uid)
        except Exception as exc:
            logger.exception("Card lookup failed at execute: %s", uid)
            return AlertResult(
                outcome=AlertOutcome.ERROR,
                card_uid=uid,
                error_message=f"DB error: {exc}",
            )

        if card is None:
            return AlertResult(
                outcome=AlertOutcome.REJECTED_UNKNOWN,
                card_uid=uid,
            )

        card_type = card.card_type
        room = card.room
        school = room.school

        # --- 2. Atomic transaction ---
        try:
            with get_db() as db:
                # Race guard: dedup again inside the transaction
                if DeduplicationChecker.is_duplicate(
                    db,
                    uid,
                    window_seconds=settings.DEDUPLICATION_WINDOW_SECONDS,
                ):
                    logger.info("Duplicate detected at execute-time: %s", uid)
                    return AlertResult(
                        outcome=AlertOutcome.REJECTED_DUPLICATE,
                        card_uid=uid,
                        card_type=card_type,
                        room_id=room.id,
                    )

                # 2a. Create the Alert
                alert = AlertRepository.create(
                    db,
                    card_uid=uid,
                    card_type=card_type,
                    room_id=room.id,
                    triggered_at=scan_ts,
                )
                alert.confirmed_at = confirmed_at

                # 2b. Fetch recipients
                parents = ParentRepository.get_for_room(db, room.id)
                police_stations = PoliceStationRepository.get_for_school(db, school.id)

                # 2c. Fetch templates
                parent_tpl = SmsTemplateRepository.get(db, card_type, "PARENT")
                police_tpl = SmsTemplateRepository.get(db, card_type, "POLICE")

                if parent_tpl is None:
                    raise RuntimeError(
                        f"Missing PARENT template for {card_type.value}"
                    )
                if police_tpl is None:
                    raise RuntimeError(
                        f"Missing POLICE template for {card_type.value}"
                    )

                # 2d. Build the format context once
                context = {
                    "room_name": room.name,
                    "wing": room.wing,
                    "floor": room.floor,
                    "school_name": school.name,
                    "school_hotline": school.hotline,
                    "timestamp": confirmed_at.strftime("%Y-%m-%d %H:%M"),
                }

                # 2e. Enqueue parent SMS (one per parent)
                queued = 0
                for parent in parents:
                    msg = parent_tpl.template_text.format(**context)
                    SmsQueueRepository.enqueue(
                        db,
                        alert_id=alert.id,
                        recipient_type="PARENT",
                        phone_number=parent.phone_number,
                        message=msg,
                    )
                    queued += 1

                # 2f. Enqueue police SMS (one per station)
                for station in police_stations:
                    msg = police_tpl.template_text.format(**context)
                    SmsQueueRepository.enqueue(
                        db,
                        alert_id=alert.id,
                        recipient_type="POLICE",
                        phone_number=station.phone_number,
                        message=msg,
                    )
                    queued += 1

                # 2g. Analytics
                AnalyticsRepository.create(
                    db,
                    alert_id=alert.id,
                    scan_ts=scan_ts,
                    confirm_ts=confirmed_at,
                    queue_ts=queued_at,
                )

                # 2h. Audit
                AuditLogRepository.log(
                    db,
                    event_type=EVENT_ALERT_QUEUED,
                    payload_json=json.dumps(
                        {
                            "alert_id": alert.id,
                            "card_uid": uid,
                            "card_type": card_type.value,
                            "parents": len(parents),
                            "police": len(police_stations),
                            "sms_queued": queued,
                        }
                    ),
                )

                alert_id = alert.id

            logger.info(
                "Alert executed: id=%s uid=%s type=%s sms_queued=%d",
                alert_id,
                uid,
                card_type.value,
                queued,
            )
            return AlertResult(
                outcome=AlertOutcome.NEEDS_CONFIRMATION,
                card_uid=uid,
                card_type=card_type,
                room_id=room.id,
                room_name=room.name,
                wing=room.wing,
                school_name=school.name,
                school_hotline=school.hotline,
                alert_id=alert_id,
                sms_queued=queued,
                scan_ts=scan_ts,
            )

        except Exception as exc:
            logger.exception("execute_alert failed for %s", uid)
            return AlertResult(
                outcome=AlertOutcome.ERROR,
                card_uid=uid,
                card_type=card_type,
                room_id=room.id,
                error_message=str(exc),
            )


# ============================================================
# Internal helpers
# ============================================================

def _audit(event_type: str, payload: dict) -> None:
    """Best-effort audit logging (never raises)."""
    try:
        with get_db() as db:
            AuditLogRepository.log(
                db,
                event_type=event_type,
                payload_json=json.dumps(payload),
            )
    except Exception:
        logger.exception("Audit log failed for event %s", event_type)