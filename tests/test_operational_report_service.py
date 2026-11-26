from datetime import datetime

from services.operational_report_service import generate_operational_pdf


def test_generate_operational_pdf_creates_a_nonempty_pdf(tmp_path):
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
            "scans_detected": 4,
            "cards_identified": 4,
            "identification_rate": 100.0,
            "confirmation_interfaces": 3,
            "confirmed": 2,
            "cancelled": 1,
            "timed_out": 0,
            "cancelled_with_sms_queued": 0,
        },
        "sms": {
            "sent": 3,
            "failed": 1,
            "pending": 0,
            "recipient_count": 4,
            "success_rate": 75.0,
            "receipt_time_note": (
                "The modem acknowledgement does not confirm parent receipt."
            ),
        },
        "latency": {
            "scan_to_authentication": latency,
            "confirmation_to_queue": latency,
            "confirmation_to_dispatch": latency,
            "dispatch_to_modem_result": latency,
        },
        "trial_success_rate_consistency": {
            "mean_percent": 75.0,
            "stddev_percent": 0.0,
            "trials_with_completed_messages": 1,
        },
        "alerts_by_type": {"DANGER": 2},
        "trials": [
            {
                "triggered_at": datetime(2026, 1, 2, 12, 0),
                "card_type": "DANGER",
                "recipient_count": 2,
                "sent": 2,
                "failed": 0,
                "pending": 0,
                "success_rate": 100.0,
            }
        ],
    }

    output = generate_operational_pdf(report, tmp_path)

    assert output.is_file()
    contents = output.read_bytes()
    assert contents.startswith(b"%PDF-")
    assert b"%%EOF" in contents[-32:]
