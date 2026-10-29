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
import threading
import time
from datetime import datetime, timedelta, timezone

from config import settings
from core.constants import EVENT_SMS_FAILED, EVENT_SMS_SENT, SmsStatus
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

    def __init__(self, sms_service: ISmsService | None = None) -> None:
        self._sms = sms_service or get_sms_service()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

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
        with get_db() as db:
            rows = self._fetch_due(db, limit=10)

        for row in rows:
            if self._stop_event.is_set():
                return
            self._send_one(row)

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
        try:
            result = self._sms.send_sms(row.phone_number, row.message)
        except Exception as exc:
            logger.exception("SMS send raised for id=%s", row.id)
            self._mark_failed(row, reason=f"exception: {exc}")
            return

        if result.success:
            self._mark_sent(row, raw=result.raw_response)
        else:
            self._mark_failed(row, reason=result.reason or "unknown")

    def _mark_sent(self, row: SmsQueue, *, raw: str = "") -> None:
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
                    payload_json=f'{{"id":{fresh.id},"phone":"{fresh.phone_number}","raw":"{raw[:80]}"}}',
                )
            logger.info("SMS sent: id=%s to=%s", row.id, row.phone_number)
        except Exception:
            logger.exception("Failed to mark SMS sent: id=%s", row.id)

    def _mark_failed(self, row: SmsQueue, *, reason: str) -> None:
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
                    payload_json=(
                        f'{{"id":{fresh.id},"phone":"{fresh.phone_number}",'
                        f'"reason":"{reason[:80]}","attempts":{fresh.attempts}}}'
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