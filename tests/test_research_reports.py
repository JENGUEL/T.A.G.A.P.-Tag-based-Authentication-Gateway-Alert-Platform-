import json
from contextlib import contextmanager
from datetime import date, datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import models
from core.constants import (
    EVENT_ALERT_CANCELLED,
    EVENT_ALERT_CONFIRMED,
    EVENT_ALERT_QUEUED,
    EVENT_CARD_SCANNED,
    EVENT_CONFIRMATION_SHOWN,
    EVENT_DEVICE_CONNECTION_CHANGED,
    EVENT_RFID_SCAN_DETECTED,
    EVENT_SMS_DISPATCH_STARTED,
    EVENT_SMS_FAILED,
    EVENT_SMS_SENT,
    SmsStatus,
)
from data import research_reports
from models import Alert, AuditLog, Card, Room, School, SmsQueue


def test_operational_report_aggregates_instrument_one_metrics(monkeypatch):
    database_engine = create_engine("sqlite:///:memory:")
    models.Base.metadata.create_all(database_engine)
    with Session(database_engine) as session:
        school = School(name="Research School", hotline="000")
        room = Room(
            school=school,
            name="Room 201",
            room_number="201",
            section="Section A",
            wing="North",
            floor="2nd Floor",
        )
        session.add(room)
        session.flush()
        session.add(
            Card(
                uid="CARD-DANGER-0001",
                type="DANGER",
                room_id=room.id,
                active=True,
            )
        )
        alert = Alert(
            room_id=room.id,
            card_uid="CARD-DANGER-0001",
            card_type="DANGER",
            triggered_at=datetime(2026, 1, 1, 0, 0),
            confirmed_at=datetime(2026, 1, 1, 0, 0, 1),
        )
        session.add(alert)
        session.flush()
        alert_id = alert.id
        session.add_all(
            [
                SmsQueue(
                    alert_id=alert_id,
                    recipient_type="PARENT",
                    phone_number="09170000001",
                    message="test",
                    status=SmsStatus.SENT.value,
                    sent_at=datetime(2026, 1, 1, 0, 0, 3),
                ),
                SmsQueue(
                    alert_id=alert_id,
                    recipient_type="PARENT",
                    phone_number="09170000002",
                    message="test",
                    status=SmsStatus.FAILED.value,
                ),
                SmsQueue(
                    alert_id=alert_id,
                    recipient_type="POLICE",
                    phone_number="09990000001",
                    message="test",
                    status=SmsStatus.PENDING.value,
                ),
            ]
        )

        def add_event(event_type, timestamp, payload):
            session.add(
                AuditLog(
                    event_type=event_type,
                    payload_json=json.dumps(payload),
                    created_at=timestamp,
                )
            )

        scan_id = "scan-confirmed"
        scan_time = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        add_event(
            EVENT_RFID_SCAN_DETECTED,
            scan_time,
            {"room_id": room.id, "scan_id": scan_id, "uid": "CARD-DANGER-0001"},
        )
        add_event(
            EVENT_CARD_SCANNED,
            datetime(2026, 1, 1, 0, 0, 0, 120000, tzinfo=timezone.utc),
            {
                "room_id": room.id,
                "scan_id": scan_id,
                "card_type": "DANGER",
                "result": "needs_confirmation",
            },
        )
        add_event(
            EVENT_CONFIRMATION_SHOWN,
            datetime(2026, 1, 1, 0, 0, 0, 150000, tzinfo=timezone.utc),
            {"room_id": room.id, "scan_id": scan_id, "card_type": "DANGER"},
        )
        add_event(
            EVENT_ALERT_CONFIRMED,
            datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc),
            {"room_id": room.id, "scan_id": scan_id, "card_type": "DANGER"},
        )
        add_event(
            EVENT_ALERT_QUEUED,
            datetime(2026, 1, 1, 0, 0, 1, 20000, tzinfo=timezone.utc),
            {
                "room_id": room.id,
                "scan_id": scan_id,
                "alert_id": alert_id,
                "card_type": "DANGER",
            },
        )
        add_event(
            EVENT_SMS_DISPATCH_STARTED,
            datetime(2026, 1, 1, 0, 0, 2, tzinfo=timezone.utc),
            {"alert_id": alert_id, "sms_id": 1, "attempt": 1},
        )
        add_event(
            EVENT_SMS_SENT,
            datetime(2026, 1, 1, 0, 0, 2, 150000, tzinfo=timezone.utc),
            {
                "alert_id": alert_id,
                "id": 1,
                "sms_id": 1,
                "attempt": 1,
                "response_time_ms": 150,
            },
        )
        add_event(
            EVENT_SMS_DISPATCH_STARTED,
            datetime(2026, 1, 1, 0, 0, 3, tzinfo=timezone.utc),
            {"alert_id": alert_id, "sms_id": 2, "attempt": 1},
        )
        add_event(
            EVENT_SMS_FAILED,
            datetime(2026, 1, 1, 0, 0, 3, 500000, tzinfo=timezone.utc),
            {
                "alert_id": alert_id,
                "id": 2,
                "sms_id": 2,
                "attempt": 1,
                "response_time_ms": 500,
            },
        )
        add_event(
            EVENT_DEVICE_CONNECTION_CHANGED,
            datetime(2026, 1, 1, 0, 0, 4, tzinfo=timezone.utc),
            {
                "room_id": room.id,
                "device": "GSM modem",
                "connected": True,
                "mode": "REAL HARDWARE",
            },
        )
        cancelled_scan_id = "scan-cancelled"
        add_event(
            EVENT_RFID_SCAN_DETECTED,
            datetime(2026, 1, 1, 0, 1, tzinfo=timezone.utc),
            {"room_id": room.id, "scan_id": cancelled_scan_id, "uid": "CARD-SAFE-1"},
        )
        add_event(
            EVENT_CARD_SCANNED,
            datetime(2026, 1, 1, 0, 1, 0, 100000, tzinfo=timezone.utc),
            {
                "room_id": room.id,
                "scan_id": cancelled_scan_id,
                "card_type": "SAFE",
                "result": "needs_confirmation",
            },
        )
        add_event(
            EVENT_CONFIRMATION_SHOWN,
            datetime(2026, 1, 1, 0, 1, 0, 150000, tzinfo=timezone.utc),
            {"room_id": room.id, "scan_id": cancelled_scan_id, "card_type": "SAFE"},
        )
        add_event(
            EVENT_ALERT_CANCELLED,
            datetime(2026, 1, 1, 0, 1, 1, tzinfo=timezone.utc),
            {"room_id": room.id, "scan_id": cancelled_scan_id, "card_type": "SAFE"},
        )
        session.commit()
        room_id = room.id

    @contextmanager
    def test_get_db():
        with Session(database_engine, expire_on_commit=False) as session:
            yield session
            session.commit()

    monkeypatch.setattr(research_reports, "get_db", test_get_db)

    report = research_reports.get_operational_report_data(
        room_id,
        date(2026, 1, 1),
        date(2026, 1, 1),
    )

    assert report["rfid"] == {
        "scans_detected": 2,
        "cards_identified": 2,
        "identification_rate": 100.0,
        "confirmation_interfaces": 2,
        "confirmed": 1,
        "cancelled": 1,
        "timed_out": 0,
        "cancelled_with_sms_queued": 0,
    }
    assert report["sms"]["sent"] == 1
    assert report["sms"]["failed"] == 1
    assert report["sms"]["pending"] == 1
    assert report["sms"]["success_rate"] == 50.0
    assert report["sms"]["receipt_time_captured"] is False
    assert report["latency"]["scan_to_authentication"]["mean_ms"] == 110.0
    assert report["latency"]["confirmation_to_queue"]["mean_ms"] == 20.0
    assert report["latency"]["confirmation_to_dispatch"]["mean_ms"] == 1500.0
    assert report["latency"]["dispatch_to_modem_result"]["mean_ms"] == 325.0
    assert len(report["raw_data"]["sms_attempts"]) == 2
    assert [
        attempt["response_time_ms"]
        for attempt in report["raw_data"]["sms_attempts"]
    ] == [150, 500]
    assert len(report["raw_data"]["rfid_cards"]) == 1
    assert any(
        event["event_type"] == EVENT_DEVICE_CONNECTION_CHANGED
        for event in report["raw_data"]["audit_events"]
    )
    assert report["raw_data"]["malformed_audit_events"] == 0
    assert report["trial_success_rate_consistency"]["mean_percent"] == 50.0
    database_engine.dispose()
