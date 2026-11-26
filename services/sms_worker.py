"""
T.A.G.A.P. - SMS Worker (Background Thread)

Continuously polls the sms_queue table and sends pending messages via the
configured ISmsService. Handles retries with exponential backoff.

Design:
- One worker thread per process.
- Graceful shutdown via threading.Event.
- Never crashes: catches all exceptions per-message.
- Retries scheduled via `next_attempt_at` column (durable across restarts).
"""

from __future__ import annotations

import logging
import json
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Callable

from config import settings
from core.constants import (
    EVENT_SMS_DISPATCH_STARTED,
    EVENT_SMS_FAILED,
    EVENT_SMS_SENT,
    SmsStatus,
)
from data.database import get_db
from data.repositories import AuditLogRepository, SmsQueueRepository
from models import Analytics, SmsQueue
from services import get_sms_service
from services.interfaces import ISmsService
from core.time_utils import safe_diff_ms, to_db, utc_now

logger = logging.getLogger(__name__)


class SmsWorker:
    """Background worker that delivers queued SMS messages."""

    POLL_INTERVAL_SECONDS = 2
    DEVICE_DETECTION_INTERVAL_SECONDS = 3

    def __init__(
        self,
        sms_service: ISmsService | None = None,
        *,
        wait_for_device_reconnect: bool = False,
        on_connection_changed: Callable[[bool], None] | None = None,
    ) -> None:
        self._sms = sms_service or get_sms_service()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._next_device_check_at = 0.0
        self._wait_for_device_reconnect = wait_for_device_reconnect
        self._on_connection_changed = on_connection_changed

    # ============================================================
    # Lifecycle
    # ============================================================

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            logger.warning("SmsWorker already running")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name="SmsWorker", daemon=True
        )
        self._thread.start()
        logger.info("SmsWorker started")

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=timeout)
        logger.info("SmsWorker stopped")

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    # ============================================================
    # Main loop
    # ============================================================

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._process_batch()
            except Exception:
                logger.exception("SmsWorker batch failed (continuing)")
            self._stop_event.wait(self.POLL_INTERVAL_SECONDS)

    def _process_batch(self) -> None:
        """Fetch and process one batch of due messages."""
        if not self._ensure_sms_connected():
            return

        with get_db() as db:
            rows = self._fetch_due(db, limit=10)

        for row in rows:
            if self._stop_event.is_set():
                return
            self._send_one(row)

    def _ensure_sms_connected(self) -> bool:
        now = time.monotonic()
        if now < self._next_device_check_at:
            return self._sms.is_connected()
        self._next_device_check_at = now + self.DEVICE_DETECTION_INTERVAL_SECONDS

        device_present = self._sms.is_device_present()
        if self._sms.is_connected():
            if device_present:
                return True
            try:
                self._sms.close()
            except Exception:
                logger.exception("Could not close disconnected GSM modem")
            self._report_sms_disconnected(
                "GSM modem disconnected; queued SMS remain pending"
            )
            return False

        if self._wait_for_device_reconnect:
            if not device_present:
                self._wait_for_device_reconnect = False
                logger.info("GSM device removed; waiting for it to reconnect")
            return False
        if not device_present:
            return False

        try:
            self._sms.open()
        except Exception as exc:
            self._wait_for_device_reconnect = True
            logger.warning(
                "GSM connection failed; queued SMS remain pending until the modem "
                "is disconnected and reconnected: %s",
                exc,
            )
            return False

        if not self._sms.is_connected():
            self._wait_for_device_reconnect = True
            logger.warning(
                "GSM open returned without a connection; queued SMS remain pending "
                "until the modem is disconnected and reconnected"
            )
            return False

        logger.info("GSM connection restored; resuming queued SMS delivery")
        if self._on_connection_changed is not None:
            self._on_connection_changed(True)
        return True

    def _fetch_due(self, db, limit: int) -> list[SmsQueue]:
        """Fetch messages where status is pending/failed AND next_attempt_at <= now."""
        now_naive = to_db(utc_now())  # compare with naive column
        return (
            db.query(SmsQueue)
            .filter(SmsQueue.status.in_([SmsStatus.PENDING.value, SmsStatus.FAILED.value]))
            .filter(SmsQueue.next_attempt_at <= now_naive)
            .filter(SmsQueue.attempts < settings.SMS_RETRY_ATTEMPTS)
            .order_by(SmsQueue.next_attempt_at.asc())
            .limit(limit)
            .all()
        )

    # ============================================================
    # Single message processing
    # ============================================================

    def _send_one(self, row: SmsQueue) -> None:
        dispatch_started_at = utc_now()
        attempt = row.attempts + 1
        try:
            with get_db() as db:
                AuditLogRepository.log(
                    db,
                    event_type=EVENT_SMS_DISPATCH_STARTED,
                    payload_json=json.dumps(
                        {
                            "alert_id": row.alert_id,
                            "sms_id": row.id,
                            "attempt": attempt,
                            "started_at_utc": dispatch_started_at.isoformat(),
                        }
                    ),
                )
        except Exception:
            logger.exception(
                "Could not record SMS dispatch start for queue item id=%s",
                row.id,
            )

        send_started_at = utc_now()
        try:
            result = self._sms.send_sms(row.phone_number, row.message)
        except Exception as exc:
            response_time_ms = max(
                0,
                int((utc_now() - send_started_at).total_seconds() * 1000),
            )
            logger.exception("SMS send raised for id=%s", row.id)
            self._mark_failed(
                row,
                reason=f"exception: {exc}",
                response_time_ms=response_time_ms,
                send_started_at=send_started_at,
            )
            if not self._sms.is_connected():
                self._report_sms_disconnected(
                    "GSM modem connection was lost during SMS delivery"
                )
            return

        response_time_ms = max(
            0,
            int((utc_now() - send_started_at).total_seconds() * 1000),
        )
        if result.success:
            self._mark_sent(
                row,
                raw=result.raw_response,
                response_time_ms=response_time_ms,
                send_started_at=send_started_at,
            )
        else:
            self._mark_failed(
                row,
                reason=result.reason or "unknown",
                response_time_ms=response_time_ms,
                send_started_at=send_started_at,
            )
        if not self._sms.is_connected():
            self._report_sms_disconnected(
                "GSM modem connection was lost during SMS delivery"
            )

    def _report_sms_disconnected(self, message: str) -> None:
        if self._wait_for_device_reconnect:
            return
        self._wait_for_device_reconnect = True
        logger.warning(message)
        if self._on_connection_changed is not None:
            self._on_connection_changed(False)

    def _mark_sent(
        self,
        row: SmsQueue,
        *,
        raw: str = "",
        response_time_ms: int,
        send_started_at: datetime,
    ) -> None:
        now = utc_now()  # aware
        try:
            with get_db() as db:
                fresh = db.get(SmsQueue, row.id)
                if fresh is None:
                    return
                SmsQueueRepository.mark_sent(db, fresh, sent_at=to_db(now))
                _update_analytics_sent_ts(db, fresh.alert_id, now)
                AuditLogRepository.log(
                    db,
                    event_type=EVENT_SMS_SENT,
                    payload_json=json.dumps(
                        {
                            "id": fresh.id,
                            "sms_id": fresh.id,
                            "alert_id": fresh.alert_id,
                            "phone": fresh.phone_number,
                            "attempt": fresh.attempts + 1,
                            "response_time_ms": response_time_ms,
                            "send_started_at_utc": send_started_at.isoformat(),
                            "raw": raw,
                        }
                    ),
                )
            logger.info("SMS sent: id=%s to=%s", row.id, row.phone_number)
        except Exception:
            logger.exception("Failed to mark SMS sent: id=%s", row.id)

    def _mark_failed(
        self,
        row: SmsQueue,
        *,
        reason: str,
        response_time_ms: int,
        send_started_at: datetime,
    ) -> None:
        now = utc_now()
        try:
            with get_db() as db:
                fresh = db.get(SmsQueue, row.id)
                if fresh is None:
                    return

                fresh.attempts += 1
                fresh.failure_reason = reason[:255]

                if fresh.attempts >= settings.SMS_RETRY_ATTEMPTS:
                    fresh.status = SmsStatus.FAILED.value
                    logger.warning(
                        "SMS permanently failed: id=%s to=%s reason=%s attempts=%d",
                        fresh.id, fresh.phone_number, reason, fresh.attempts,
                    )
                else:
                    backoff = settings.SMS_RETRY_BACKOFF_SECONDS * (2 ** (fresh.attempts - 1))
                    fresh.next_attempt_at = to_db(now + timedelta(seconds=backoff))
                    fresh.status = SmsStatus.PENDING.value
                    logger.info(
                        "SMS retry scheduled: id=%s attempt=%d backoff=%ds",
                        fresh.id, fresh.attempts, backoff,
                    )

                AuditLogRepository.log(
                    db,
                    event_type=EVENT_SMS_FAILED,
                    payload_json=json.dumps(
                        {
                            "id": fresh.id,
                            "sms_id": fresh.id,
                            "alert_id": fresh.alert_id,
                            "phone": fresh.phone_number,
                            "reason": reason[:255],
                            "attempt": fresh.attempts,
                            "response_time_ms": response_time_ms,
                            "send_started_at_utc": send_started_at.isoformat(),
                        }
                    ),
                )
        except Exception:
            logger.exception("Failed to mark SMS failed: id=%s", row.id)


# ============================================================
# Helpers
# ============================================================

def _update_analytics_sent_ts(db, alert_id: int, sent_ts: datetime) -> None:
    row = db.query(Analytics).filter_by(alert_id=alert_id).first()
    if row is None:
        return
    row.sent_ts = to_db(sent_ts)  # store as naive UTC
    # row.queue_ts was read from DB → naive. safe_diff_ms handles that.
    row.delivery_time_ms = safe_diff_ms(sent_ts, row.queue_ts)