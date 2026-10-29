"""
T.A.G.A.P. - UI Queries

Read-only queries for the Flet UI. Returns plain dicts / primitives.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func
from data.database import get_db
from core.time_utils import utc_now
from models import Alert, SmsQueue, Analytics, Room, School, Card


def get_dashboard_data() -> dict[str, Any]:
    """Data for the main Room Device Dashboard (Image 1)."""
    with get_db() as db:
        room = db.query(Room).first()
        if not room:
            return {}

        # Last scan
        last_alert = db.query(Alert).order_by(Alert.triggered_at.desc()).first()
        last_scan_time = last_alert.triggered_at if last_alert else None

        return {
            "room_id": room.id,
            "room_name": room.name,
            "wing": room.wing,
            "floor": room.floor,
            "school_name": room.school.name,
            "device_online": True,  # Mocked for now, will wire to Hardware later
            "last_scan_time": last_scan_time,
            "last_tag_id": last_alert.card_uid if last_alert else None,
            "last_tag_type": last_alert.card_type if last_alert else None,
        }


def get_alert_history_stats() -> dict[str, Any]:
    """Data for the top of the Alert History page (Image 3 & 4)."""
    with get_db() as db:
        # SMS Stats
        total_sms = db.query(SmsQueue).count()
        sent_sms = db.query(SmsQueue).filter_by(status="SENT").count()
        delivery_rate = int((sent_sms / total_sms * 100)) if total_sms > 0 else 0

        # RFID Stats
        total_rfid = db.query(Alert).count()

        return {
            "total_sms": total_sms,
            "sent_sms": sent_sms,
            "delivery_rate": delivery_rate,
            "total_rfid": total_rfid,
            "distinct_meanings": 3,
        }


def get_sms_history(limit: int = 10) -> list[dict]:
    """Data for the SMS History list (Image 3)."""
    with get_db() as db:
        alerts = db.query(Alert).order_by(Alert.triggered_at.desc()).limit(limit).all()
        results = []
        for alert in alerts:
            parents = db.query(SmsQueue).filter_by(alert_id=alert.id, recipient_type="PARENT").count()
            results.append({
                "id": alert.id,
                "message": f"Alert sent to parents and staff",  # Placeholder
                "date": alert.triggered_at.strftime("%b %d, %Y"),
                "time": alert.triggered_at.strftime("%I:%M %p"),
                "recipients": parents,
                "status": "Delivered",  # Placeholder for now
            })
        return results


def get_rfid_history(limit: int = 10) -> list[dict]:
    """Data for the RFID History list (Image 3)."""
    with get_db() as db:
        alerts = db.query(Alert).order_by(Alert.triggered_at.desc()).limit(limit).all()
        results = []
        for alert in alerts:
            results.append({
                "id": alert.id,
                "tag_id": alert.card_uid,
                "date": alert.triggered_at.strftime("%b %d, %Y"),
                "time": alert.triggered_at.strftime("%I:%M %p"),
                "meaning": alert.card_type.title(),
            })
        return results