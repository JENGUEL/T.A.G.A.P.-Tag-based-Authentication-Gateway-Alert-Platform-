"""Operational metrics for the researcher-administered performance checklist."""

from __future__ import annotations

import json
import logging
import statistics
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import or_, select

from core.constants import (
    EVENT_ADMIN_ACCESS,
    EVENT_ALERT_CANCELLED,
    EVENT_ALERT_CONFIRMED,
    EVENT_ALERT_QUEUED,
    EVENT_CARD_REJECTED_DUPLICATE,
    EVENT_CARD_SCANNED,
    EVENT_CONFIRMATION_SHOWN,
    EVENT_CONFIRMATION_TIMEOUT,
    EVENT_DEVICE_CONNECTION_CHANGED,
    EVENT_RFID_SCAN_DETECTED,
    EVENT_SMS_DISPATCH_STARTED,
    EVENT_SMS_FAILED,
    EVENT_SMS_SENT,
    EVENT_SYSTEM_BOOT,
    EVENT_SYSTEM_SHUTDOWN,
    SmsStatus,
)
from data.database import get_db
from models import Alert, Analytics, AuditLog, Card, Room, SmsQueue

logger = logging.getLogger(__name__)

REPORT_TIMEZONE = timezone(timedelta(hours=8), "Asia/Manila")
REPORT_EVENTS = (
    EVENT_RFID_SCAN_DETECTED,
    EVENT_CARD_SCANNED,
    EVENT_CARD_REJECTED_DUPLICATE,
    EVENT_ADMIN_ACCESS,
    EVENT_CONFIRMATION_SHOWN,
    EVENT_ALERT_CONFIRMED,
    EVENT_ALERT_CANCELLED,
    EVENT_CONFIRMATION_TIMEOUT,
    EVENT_ALERT_QUEUED,
    EVENT_SMS_DISPATCH_STARTED,
    EVENT_SMS_SENT,
    EVENT_SMS_FAILED,
    EVENT_DEVICE_CONNECTION_CHANGED,
)


def _utc_boundary(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=REPORT_TIMEZONE).astimezone(
        timezone.utc
    ).replace(tzinfo=None)


def _latency_summary(values: list[int]) -> dict[str, int | float | None]:
    if not values:
        return {
            "samples": 0,
            "mean_ms": None,
            "median_ms": None,
            "min_ms": None,
            "max_ms": None,
        }
    return {
        "samples": len(values),
        "mean_ms": round(statistics.fmean(values), 1),
        "median_ms": round(statistics.median(values), 1),
        "min_ms": min(values),
        "max_ms": max(values),
    }


def _elapsed_ms(later: datetime, earlier: datetime) -> int:
    if later.tzinfo is None:
        later = later.replace(tzinfo=timezone.utc)
    if earlier.tzinfo is None:
        earlier = earlier.replace(tzinfo=timezone.utc)
    return max(0, int((later - earlier).total_seconds() * 1000))


def _build_sms_attempts(
    events: list[dict[str, object]],
    sms_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    sms_by_id = {int(row["id"]): row for row in sms_rows}
    starts_by_sms: dict[int, list[dict[str, object]]] = defaultdict(list)
    outcomes_by_sms: dict[int, list[dict[str, object]]] = defaultdict(list)

    for event in events:
        event_type = event["event_type"]
        payload = event["payload"]
        if not isinstance(payload, dict):
            continue
        if event_type == EVENT_SMS_DISPATCH_STARTED:
            sms_id = payload.get("sms_id")
            if isinstance(sms_id, int):
                starts_by_sms[sms_id].append(event)
        elif event_type in (EVENT_SMS_SENT, EVENT_SMS_FAILED):
            sms_id = payload.get("sms_id", payload.get("id"))
            if isinstance(sms_id, int):
                outcomes_by_sms[sms_id].append(event)

    attempts: list[dict[str, object]] = []
    for sms_id, starts in starts_by_sms.items():
        sms_row = sms_by_id.get(sms_id, {})
        ordered_starts = sorted(starts, key=lambda item: item["created_at"])
        ordered_outcomes = sorted(
            outcomes_by_sms.get(sms_id, []),
            key=lambda item: item["created_at"],
        )
        used_outcome_ids: set[int] = set()
        for start in ordered_starts:
            start_payload = start["payload"]
            start_attempt = (
                start_payload.get("attempt")
                if isinstance(start_payload, dict)
                else None
            )
            matching_outcome = None
            for outcome in ordered_outcomes:
                if outcome["event_id"] in used_outcome_ids:
                    continue
                if outcome["created_at"] < start["created_at"]:
                    continue
                outcome_payload = outcome["payload"]
                outcome_attempt = (
                    outcome_payload.get("attempt")
                    if isinstance(outcome_payload, dict)
                    else None
                )
                if (
                    start_attempt is not None
                    and outcome_attempt is not None
                    and start_attempt != outcome_attempt
                ):
                    continue
                matching_outcome = outcome
                break

            elapsed_ms = None
            reported_ms = None
            response_source = "Not recorded"
            outcome_type = "NO RESULT RECORDED"
            outcome_at = None
            outcome_event_id = None
            send_started_at = start["created_at"]
            if matching_outcome is not None:
                used_outcome_ids.add(int(matching_outcome["event_id"]))
                outcome_payload = matching_outcome["payload"]
                if isinstance(outcome_payload, dict):
                    raw_send_started_at = outcome_payload.get("send_started_at_utc")
                    if isinstance(raw_send_started_at, str):
                        try:
                            send_started_at = datetime.fromisoformat(
                                raw_send_started_at
                            )
                        except ValueError:
                            logger.warning(
                                "Invalid SMS send start timestamp in audit event id=%s",
                                matching_outcome["event_id"],
                            )
                elapsed_ms = _elapsed_ms(
                    matching_outcome["created_at"],
                    send_started_at,
                )
                raw_response_ms = (
                    outcome_payload.get("response_time_ms")
                    if isinstance(outcome_payload, dict)
                    else None
                )
                if isinstance(raw_response_ms, int) and not isinstance(
                    raw_response_ms, bool
                ):
                    reported_ms = raw_response_ms
                    response_ms = raw_response_ms
                    response_source = "Worker measured"
                else:
                    response_ms = elapsed_ms
                    response_source = "Audit timestamp estimate"
                outcome_type = str(matching_outcome["event_type"])
                outcome_at = matching_outcome["created_at"]
                outcome_event_id = matching_outcome["event_id"]
            else:
                response_ms = None

            attempts.append(
                {
                    "sms_id": sms_id,
                    "alert_id": sms_row.get("alert_id"),
                    "recipient_type": sms_row.get("recipient_type"),
                    "attempt": start_attempt,
                    "dispatch_event_id": start["event_id"],
                    "dispatch_started_at": start["created_at"],
                    "send_started_at": send_started_at,
                    "outcome_event_id": outcome_event_id,
                    "outcome_type": outcome_type,
                    "outcome_at": outcome_at,
                    "response_time_ms": response_ms,
                    "reported_response_time_ms": reported_ms,
                    "audit_elapsed_ms": elapsed_ms,
                    "response_time_source": response_source,
                }
            )
    return sorted(
        attempts,
        key=lambda item: (item["dispatch_started_at"], item["sms_id"]),
    )


def get_operational_report_data(
    room_id: int,
    start_date: date,
    end_date: date,
) -> dict[str, object]:
    """Return Instrument 1 operational metrics for an inclusive local date range."""
    if start_date > end_date:
        raise ValueError("Report start date must be on or before the end date")

    start_utc = _utc_boundary(start_date)
    end_utc = _utc_boundary(end_date + timedelta(days=1))
    with get_db() as db:
        room = db.get(Room, room_id)
        if room is None:
            raise LookupError(f"Room {room_id} does not exist")

        room_info = {
            "id": room.id,
            "name": room.name,
            "room_number": room.room_number,
            "section": room.section,
            "floor": room.floor,
            "school": room.school.name,
        }
        raw_cards = [
            {
                "id": card.id,
                "room_id": card.room_id,
                "uid": card.uid,
                "card_type": card.type,
                "active": card.active,
                "created_at": card.created_at,
                "updated_at": card.updated_at,
            }
            for card in db.scalars(
                select(Card).where(Card.room_id == room_id).order_by(Card.id)
            )
        ]
        alerts = list(
            db.scalars(
                select(Alert).where(
                    Alert.room_id == room_id,
                    Alert.triggered_at >= start_utc,
                    Alert.triggered_at < end_utc,
                    Alert.card_uid.not_like("MANUAL-%"),
                )
            )
        )
        alert_ids = {alert.id for alert in alerts}
        raw_alerts = [
            {
                "id": alert.id,
                "room_id": alert.room_id,
                "card_uid": alert.card_uid,
                "card_type": alert.card_type,
                "triggered_at": alert.triggered_at,
                "confirmed_at": alert.confirmed_at,
                "created_at": alert.created_at,
                "updated_at": alert.updated_at,
            }
            for alert in alerts
        ]
        sms_rows = (
            list(
                db.scalars(
                    select(SmsQueue).where(SmsQueue.alert_id.in_(alert_ids))
                )
            )
            if alert_ids
            else []
        )
        sms_ids = {row.id for row in sms_rows}
        analytics_rows = (
            list(
                db.scalars(
                    select(Analytics).where(Analytics.alert_id.in_(alert_ids))
                )
            )
            if alert_ids
            else []
        )
        audit_rows = list(
            db.scalars(
                select(AuditLog)
                .where(
                    or_(
                        (
                            (AuditLog.created_at >= start_utc)
                            & (AuditLog.created_at < end_utc)
                        ),
                        AuditLog.event_type.in_(
                            (
                                EVENT_ALERT_QUEUED,
                                EVENT_SMS_DISPATCH_STARTED,
                                EVENT_SMS_SENT,
                                EVENT_SMS_FAILED,
                            )
                        ),
                    )
                )
                .order_by(AuditLog.created_at)
            )
        )

        parsed_events: list[dict[str, object]] = []
        raw_events: list[dict[str, object]] = []
        malformed_audit_events = 0
        for row in audit_rows:
            try:
                payload = json.loads(row.payload_json)
            except (TypeError, json.JSONDecodeError):
                logger.warning("Skipping malformed audit payload id=%s", row.id)
                if row.event_type in REPORT_EVENTS:
                    malformed_audit_events += 1
                    raw_events.append(
                        {
                            "event_id": row.id,
                            "event_type": row.event_type,
                            "created_at": row.created_at,
                            "payload": None,
                            "payload_error": "Malformed JSON; source omitted",
                        }
                    )
                continue
            if not isinstance(payload, dict):
                logger.warning("Skipping non-object audit payload id=%s", row.id)
                if row.event_type in REPORT_EVENTS:
                    malformed_audit_events += 1
                    raw_events.append(
                        {
                            "event_id": row.id,
                            "event_type": row.event_type,
                            "created_at": row.created_at,
                            "payload": None,
                            "payload_error": "Payload is not a JSON object",
                        }
                    )
                continue

            event_sms_id = payload.get("sms_id", payload.get("id"))
            is_in_room = payload.get("room_id") == room_id
            is_in_alert = payload.get("alert_id") in alert_ids
            is_in_sms_queue = (
                row.event_type
                in (EVENT_SMS_DISPATCH_STARTED, EVENT_SMS_SENT, EVENT_SMS_FAILED)
                and event_sms_id in sms_ids
            )
            is_system_event = row.event_type in (
                EVENT_SYSTEM_BOOT,
                EVENT_SYSTEM_SHUTDOWN,
            )
            if not (is_in_room or is_in_alert or is_in_sms_queue or is_system_event):
                continue

            event = {
                "event_id": row.id,
                "event_type": row.event_type,
                "created_at": row.created_at,
                "payload": payload,
                "payload_error": None,
            }
            raw_events.append(event)
            if row.event_type in REPORT_EVENTS:
                parsed_events.append(event)

        raw_sms_rows = [
            {
                "id": row.id,
                "alert_id": row.alert_id,
                "recipient_type": row.recipient_type,
                "phone_number": row.phone_number,
                "message": row.message,
                "status": row.status,
                "attempts": row.attempts,
                "failure_reason": row.failure_reason,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
                "sent_at": row.sent_at,
                "next_attempt_at": row.next_attempt_at,
            }
            for row in sms_rows
        ]
        raw_sms_attempts = _build_sms_attempts(raw_events, raw_sms_rows)
        raw_analytics = [
            {
                "id": row.id,
                "alert_id": row.alert_id,
                "scan_ts": row.scan_ts,
                "confirm_ts": row.confirm_ts,
                "queue_ts": row.queue_ts,
                "sent_ts": row.sent_ts,
                "response_time_ms": row.response_time_ms,
                "delivery_time_ms": row.delivery_time_ms,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
            for row in analytics_rows
        ]

    events_by_scan: dict[str, dict[str, list[datetime]]] = defaultdict(
        lambda: defaultdict(list)
    )
    by_type: dict[str, list[dict[str, object]]] = defaultdict(list)
    for event in parsed_events:
        event_type = str(event["event_type"])
        payload = event["payload"]
        event_time = event["created_at"]
        by_type[event_type].append(event)
        scan_id = payload.get("scan_id")
        if isinstance(scan_id, str) and scan_id:
            events_by_scan[scan_id][event_type].append(event_time)

    detected = by_type[EVENT_RFID_SCAN_DETECTED]
    identified_scan_ids = {
        str(event["payload"].get("scan_id"))
        for event in by_type[EVENT_CARD_SCANNED]
        if event["payload"].get("result") == "needs_confirmation"
        and event["payload"].get("scan_id")
    }
    identified_scan_ids.update(
        str(event["payload"].get("scan_id"))
        for event in by_type[EVENT_CARD_REJECTED_DUPLICATE]
        if event["payload"].get("scan_id")
    )
    identified_scan_ids.update(
        str(event["payload"].get("scan_id"))
        for event in by_type[EVENT_ADMIN_ACCESS]
        if event["payload"].get("scan_id")
    )

    confirmation_times = {
        str(event["payload"].get("scan_id")): event["created_at"]
        for event in by_type[EVENT_ALERT_CONFIRMED]
        if event["payload"].get("scan_id")
    }
    queued_by_scan = {
        str(event["payload"].get("scan_id")): event
        for event in by_type[EVENT_ALERT_QUEUED]
        if event["payload"].get("scan_id")
    }
    cancelled_scan_ids = {
        str(event["payload"].get("scan_id"))
        for event in by_type[EVENT_ALERT_CANCELLED]
        if event["payload"].get("scan_id")
    }
    queued_scan_ids = set(queued_by_scan)

    scan_authentication_ms = []
    confirmation_to_queue_ms = []
    for scan_id, milestones in events_by_scan.items():
        detected_times = milestones.get(EVENT_RFID_SCAN_DETECTED, [])
        identified_times = (
            milestones.get(EVENT_CARD_SCANNED, [])
            + milestones.get(EVENT_CARD_REJECTED_DUPLICATE, [])
        )
        if detected_times and identified_times:
            scan_authentication_ms.append(
                _elapsed_ms(identified_times[0], detected_times[0])
            )
        confirmed_at = confirmation_times.get(scan_id)
        queued_event = queued_by_scan.get(scan_id)
        if confirmed_at and queued_event:
            confirmation_to_queue_ms.append(
                _elapsed_ms(queued_event["created_at"], confirmed_at)
            )

    alert_id_by_scan = {
        scan_id: event["payload"].get("alert_id")
        for scan_id, event in queued_by_scan.items()
    }
    confirmation_to_dispatch_ms = []
    for event in by_type[EVENT_SMS_DISPATCH_STARTED]:
        alert_id = event["payload"].get("alert_id")
        scan_id = next(
            (
                linked_scan_id
                for linked_scan_id, linked_alert_id in alert_id_by_scan.items()
                if linked_alert_id == alert_id
            ),
            None,
        )
        confirmed_at = confirmation_times.get(scan_id) if scan_id else None
        if confirmed_at:
            confirmation_to_dispatch_ms.append(
                _elapsed_ms(event["created_at"], confirmed_at)
            )
    dispatch_to_result_ms = [
        int(attempt["response_time_ms"])
        for attempt in raw_sms_attempts
        if isinstance(attempt["response_time_ms"], int)
        and not isinstance(attempt["response_time_ms"], bool)
    ]

    events_by_scan_id: dict[str, dict[str, dict[str, object]]] = defaultdict(dict)
    for event in parsed_events:
        payload = event["payload"]
        scan_id = payload.get("scan_id")
        if isinstance(scan_id, str) and scan_id:
            events_by_scan_id[scan_id][str(event["event_type"])] = event

    latency_records = []
    for scan_id, scan_events in events_by_scan_id.items():
        detected_event = scan_events.get(EVENT_RFID_SCAN_DETECTED)
        identified_event = scan_events.get(EVENT_CARD_SCANNED) or scan_events.get(
            EVENT_CARD_REJECTED_DUPLICATE
        )
        shown_event = scan_events.get(EVENT_CONFIRMATION_SHOWN)
        confirmed_event = scan_events.get(EVENT_ALERT_CONFIRMED)
        cancelled_event = scan_events.get(EVENT_ALERT_CANCELLED)
        timeout_event = scan_events.get(EVENT_CONFIRMATION_TIMEOUT)
        queued_event = scan_events.get(EVENT_ALERT_QUEUED)
        card_event = identified_event or detected_event
        card_payload = card_event["payload"] if card_event else {}
        alert_id = (
            queued_event["payload"].get("alert_id")
            if queued_event
            else None
        )
        dispatch_events = [
            event
            for event in by_type[EVENT_SMS_DISPATCH_STARTED]
            if event["payload"].get("alert_id") == alert_id
        ]
        dispatch_event = (
            min(dispatch_events, key=lambda event: event["created_at"])
            if dispatch_events
            else None
        )
        detected_at = detected_event["created_at"] if detected_event else None
        identified_at = identified_event["created_at"] if identified_event else None
        confirmed_at = confirmed_event["created_at"] if confirmed_event else None
        queued_at = queued_event["created_at"] if queued_event else None
        dispatch_at = dispatch_event["created_at"] if dispatch_event else None

        def duration_ms(later, earlier):
            return _elapsed_ms(later, earlier) if later and earlier else None

        latency_records.append(
            {
                "scan_id": scan_id,
                "alert_id": alert_id,
                "card_type": card_payload.get("card_type"),
                "card_uid": card_payload.get(
                    "uid",
                    card_payload.get("card_uid"),
                ),
                "detected_at": detected_at,
                "identified_at": identified_at,
                "confirmation_shown_at": (
                    shown_event["created_at"] if shown_event else None
                ),
                "confirmed_at": confirmed_at,
                "cancelled_at": (
                    cancelled_event["created_at"] if cancelled_event else None
                ),
                "timed_out_at": timeout_event["created_at"] if timeout_event else None,
                "queued_at": queued_at,
                "dispatch_started_at": dispatch_at,
                "scan_to_identification_ms": duration_ms(
                    identified_at,
                    detected_at,
                ),
                "confirmation_to_queue_ms": duration_ms(queued_at, confirmed_at),
                "confirmation_to_dispatch_ms": duration_ms(
                    dispatch_at,
                    confirmed_at,
                ),
                "confirmation_result": (
                    "CONFIRMED"
                    if confirmed_event
                    else "CANCELLED"
                    if cancelled_event
                    else "TIMED OUT"
                    if timeout_event
                    else "NOT RECORDED"
                ),
            }
        )

    sms_counts = {
        "sent": sum(row.status == SmsStatus.SENT.value for row in sms_rows),
        "failed": sum(row.status == SmsStatus.FAILED.value for row in sms_rows),
        "pending": sum(
            row.status in (SmsStatus.PENDING.value, SmsStatus.SENDING.value)
            for row in sms_rows
        ),
    }
    completed_sms = sms_counts["sent"] + sms_counts["failed"]
    success_rate = (
        round(sms_counts["sent"] / completed_sms * 100, 1)
        if completed_sms
        else None
    )

    rows_by_alert: dict[int, list[SmsQueue]] = defaultdict(list)
    for row in sms_rows:
        rows_by_alert[row.alert_id].append(row)
    trial_rows = []
    for alert in sorted(alerts, key=lambda item: item.triggered_at):
        trial_sms = rows_by_alert[alert.id]
        sent = sum(row.status == SmsStatus.SENT.value for row in trial_sms)
        failed = sum(row.status == SmsStatus.FAILED.value for row in trial_sms)
        pending = sum(
            row.status in (SmsStatus.PENDING.value, SmsStatus.SENDING.value)
            for row in trial_sms
        )
        completed = sent + failed
        trial_rows.append(
            {
                "triggered_at": alert.triggered_at,
                "card_type": alert.card_type,
                "recipient_count": len(trial_sms),
                "sent": sent,
                "failed": failed,
                "pending": pending,
                "success_rate": round(sent / completed * 100, 1) if completed else None,
            }
        )

    trial_rates = [
        row["success_rate"]
        for row in trial_rows
        if row["success_rate"] is not None
    ]
    sms_type_counts = defaultdict(int)
    for alert in alerts:
        sms_type_counts[alert.card_type] += 1

    return {
        "room": room_info,
        "generated_at": datetime.now(REPORT_TIMEZONE),
        "period": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "timezone": "Asia/Manila",
        },
        "rfid": {
            "scans_detected": len(detected),
            "cards_identified": len(identified_scan_ids),
            "identification_rate": (
                round(len(identified_scan_ids) / len(detected) * 100, 1)
                if detected
                else None
            ),
            "confirmation_interfaces": len(by_type[EVENT_CONFIRMATION_SHOWN]),
            "confirmed": len(by_type[EVENT_ALERT_CONFIRMED]),
            "cancelled": len(cancelled_scan_ids),
            "timed_out": len(by_type[EVENT_CONFIRMATION_TIMEOUT]),
            "cancelled_with_sms_queued": len(cancelled_scan_ids & queued_scan_ids),
        },
        "latency": {
            "scan_to_authentication": _latency_summary(scan_authentication_ms),
            "confirmation_to_queue": _latency_summary(confirmation_to_queue_ms),
            "confirmation_to_dispatch": _latency_summary(
                confirmation_to_dispatch_ms
            ),
            "dispatch_to_modem_result": _latency_summary(dispatch_to_result_ms),
        },
        "sms": {
            **sms_counts,
            "recipient_count": len(sms_rows),
            "success_rate": success_rate,
            "receipt_time_captured": False,
            "receipt_time_note": (
                "The modem records its SMS submission acknowledgement; it does not "
                "confirm when the parent receives the message."
            ),
        },
        "trials": trial_rows,
        "trial_success_rate_consistency": {
            "trials_with_completed_messages": len(trial_rates),
            "mean_percent": round(statistics.fmean(trial_rates), 1)
            if trial_rates
            else None,
            "stddev_percent": round(statistics.pstdev(trial_rates), 1)
            if trial_rates
            else None,
        },
        "alerts_by_type": dict(sms_type_counts),
        "analytics_samples": len(analytics_rows),
        "raw_data": {
            "rfid_events": [
                event
                for event in raw_events
                if event["event_type"]
                in (
                    EVENT_RFID_SCAN_DETECTED,
                    EVENT_CARD_SCANNED,
                    EVENT_CARD_REJECTED_DUPLICATE,
                    EVENT_ADMIN_ACCESS,
                    EVENT_CONFIRMATION_SHOWN,
                    EVENT_ALERT_CONFIRMED,
                    EVENT_ALERT_CANCELLED,
                    EVENT_CONFIRMATION_TIMEOUT,
                )
            ],
            "rfid_cards": raw_cards,
            "alerts": raw_alerts,
            "sms_queue": raw_sms_rows,
            "sms_attempts": raw_sms_attempts,
            "audit_events": raw_events,
            "analytics": raw_analytics,
            "latency": latency_records,
            "malformed_audit_events": malformed_audit_events,
        },
    }
