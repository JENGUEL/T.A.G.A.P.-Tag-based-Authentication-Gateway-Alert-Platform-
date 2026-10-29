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



def get_room_info(room_id: int) -> dict[str, Any]:
    """Full info about a room for the Dashboard header."""
    with get_db() as db:
        room = db.query(Room).filter_by(id=room_id).first()
        if not room:
            return {}
        return {
            "room_id": room.id,
            "room_name": room.name,
            "wing": room.wing,
            "floor": room.floor,
            "school_name": room.school.name,
            "school_hotline": room.school.hotline,
            "grade_section": "Grade 7 - Section A",  # Placeholder until we add to DB
        }


def get_parents_for_room(room_id: int) -> list[dict]:
    """List of parents linked to a room (for Quick Actions)."""
    with get_db() as db:
        from models import Parent, Student
        parents = (
            db.query(Parent)
            .join(Parent.students)
            .filter(Student.room_id == room_id)
            .distinct()
            .all()
        )
        return [
            {"id": p.id, "name": p.name, "phone": p.phone_number}
            for p in parents
        ]


def get_settings_snapshot(room_id: int) -> dict[str, Any]:
    """All settings data for the Settings page."""
    from config import settings
    from models import SmsTemplate, Card

    with get_db() as db:
        cards = db.query(Card).filter_by(room_id=room_id).all()
        templates = db.query(SmsTemplate).all()

        return {
            "system_name": settings.APP_NAME,
            "room_id": f"TAGAP-RD-{room_id:03d}",
            "dedup_window": settings.DEDUPLICATION_WINDOW_SECONDS,
            "confirmation_timeout": settings.CONFIRMATION_TIMEOUT_SECONDS,
            "sms_retry_attempts": settings.SMS_RETRY_ATTEMPTS,
            "mock_rfid": settings.USE_MOCK_RFID,
            "mock_sms": settings.USE_MOCK_SMS,
            "cards": [
                {"uid": c.uid, "type": c.type, "active": c.active}
                for c in cards
            ],
            "templates": [
                {
                    "id": t.id,
                    "card_type": t.card_type,
                    "recipient_type": t.recipient_type,
                    "text": t.template_text,
                }
                for t in templates
            ],
        }


def get_queue_stats(room_id: int | None = None) -> dict[str, int]:
    """Pending / sent / failed SMS counts."""
    with get_db() as db:
        base = db.query(SmsQueue)
        return {
            "pending": base.filter_by(status="PENDING").count(),
            "sent": base.filter_by(status="SENT").count(),
            "failed": base.filter_by(status="FAILED").count(),
        }