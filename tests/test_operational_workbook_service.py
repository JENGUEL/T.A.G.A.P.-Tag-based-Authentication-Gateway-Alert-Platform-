from datetime import datetime

from openpyxl import load_workbook

from services.operational_workbook_service import generate_operational_workbook


def test_workbook_exports_raw_sheets_and_places_summary_last(tmp_path):
    timestamp = datetime(2026, 1, 1, 0, 0, 0)
    latency = {
        "samples": 1,
        "mean_ms": 120.0,
        "median_ms": 120.0,
        "min_ms": 120,
        "max_ms": 120,
    }
    report = {
        "room": {
            "id": 1,
            "name": "Room 201",
            "room_number": "201",
            "section": "Section A",
            "wing": "North",
            "floor": "2nd Floor",
            "school": "Research School",
        },
        "period": {"start": "2026-01-01", "end": "2026-01-31"},
        "rfid": {
            "scans_detected": 1,
            "cards_identified": 1,
            "identification_rate": 100.0,
            "confirmation_interfaces": 1,
            "confirmed": 1,
            "cancelled": 0,
            "timed_out": 0,
            "cancelled_with_sms_queued": 0,
        },
        "sms": {
            "sent": 1,
            "failed": 0,
            "pending": 0,
            "recipient_count": 1,
            "success_rate": 100.0,
        },
        "latency": {
            "scan_to_authentication": latency,
            "confirmation_to_queue": latency,
            "confirmation_to_dispatch": latency,
            "dispatch_to_modem_result": latency,
        },
        "trial_success_rate_consistency": {
            "mean_percent": 100.0,
            "stddev_percent": 0.0,
            "trials_with_completed_messages": 1,
        },
        "alerts_by_type": {"DANGER": 1},
        "raw_data": {
            "rfid_cards": [
                {
                    "id": 1,
                    "room_id": 1,
                    "uid": "A1B2C3D4",
                    "card_type": "DANGER",
                    "active": True,
                    "created_at": timestamp,
                    "updated_at": timestamp,
                }
            ],
            "rfid_events": [
                {
                    "event_id": 1,
                    "event_type": "RFID_SCAN_DETECTED",
                    "created_at": timestamp,
                    "payload": {
                        "room_id": 1,
                        "scan_id": "scan-1",
                        "uid": "A1B2C3D4",
                    },
                    "payload_error": None,
                }
            ],
            "alerts": [
                {
                    "id": 1,
                    "room_id": 1,
                    "card_uid": "A1B2C3D4",
                    "card_type": "DANGER",
                    "triggered_at": timestamp,
                    "confirmed_at": timestamp,
                    "created_at": timestamp,
                    "updated_at": timestamp,
                }
            ],
            "sms_queue": [
                {
                    "id": 1,
                    "alert_id": 1,
                    "recipient_type": "PARENT",
                    "phone_number": "09170000001",
                    "message": "[TAGAP] Emergency alert for Room 201.",
                    "status": "SENT",
                    "attempts": 0,
                    "failure_reason": None,
                    "created_at": timestamp,
                    "updated_at": timestamp,
                    "sent_at": timestamp,
                    "next_attempt_at": timestamp,
                }
            ],
            "sms_attempts": [
                {
                    "sms_id": 1,
                    "alert_id": 1,
                    "recipient_type": "PARENT",
                    "attempt": 1,
                    "dispatch_event_id": 2,
                    "dispatch_started_at": timestamp,
                    "send_started_at": timestamp,
                    "outcome_event_id": 3,
                    "outcome_type": "SMS_SENT",
                    "outcome_at": timestamp,
                    "response_time_ms": 45,
                    "reported_response_time_ms": 45,
                    "audit_elapsed_ms": 49,
                    "response_time_source": "Worker measured",
                }
            ],
            "audit_events": [
                {
                    "event_id": 1,
                    "event_type": "RFID_SCAN_DETECTED",
                    "created_at": timestamp,
                    "payload": {
                        "room_id": 1,
                        "scan_id": "scan-1",
                        "uid": "A1B2C3D4",
                        "phone": "09170000001",
                    },
                    "payload_error": None,
                }
            ],
            "analytics": [
                {
                    "id": 1,
                    "alert_id": 1,
                    "scan_ts": timestamp,
                    "confirm_ts": timestamp,
                    "queue_ts": timestamp,
                    "sent_ts": timestamp,
                    "response_time_ms": 0,
                    "delivery_time_ms": 0,
                    "created_at": timestamp,
                    "updated_at": timestamp,
                }
            ],
            "latency": [
                {
                    "scan_id": "scan-1",
                    "alert_id": 1,
                    "card_type": "DANGER",
                    "card_uid": "A1B2C3D4",
                    "detected_at": timestamp,
                    "identified_at": timestamp,
                    "confirmation_shown_at": timestamp,
                    "confirmed_at": timestamp,
                    "cancelled_at": None,
                    "timed_out_at": None,
                    "queued_at": timestamp,
                    "dispatch_started_at": timestamp,
                    "scan_to_identification_ms": 0,
                    "confirmation_to_queue_ms": 0,
                    "confirmation_to_dispatch_ms": 0,
                    "confirmation_result": "CONFIRMED",
                }
            ],
            "malformed_audit_events": 0,
        },
    }

    output = generate_operational_workbook(report, tmp_path)
    workbook = load_workbook(output, data_only=True)

    assert workbook.sheetnames == [
        "RFID Events",
        "RFID Cards",
        "Alerts",
        "SMS Queue",
        "SMS Attempts",
        "Audit Trail",
        "Analytics",
        "Latency",
        "Summary",
    ]
    assert workbook.active.title == "Summary"
    assert workbook["SMS Queue"]["D5"].value == "****0001"
    assert "Emergency alert" in workbook["SMS Queue"]["E5"].value
    assert "A1B2C3D4" not in str(workbook["RFID Events"]["H5"].value)
    audit_payload = workbook["Audit Trail"]["I5"].value
    assert "09170000001" not in audit_payload
    assert "****0001" in audit_payload
    assert workbook["SMS Attempts"]["N5"].value == 45
    assert "response time" in " ".join(
        str(workbook["Summary"].cell(row, 1).value).lower()
        for row in range(1, workbook["Summary"].max_row + 1)
    )
