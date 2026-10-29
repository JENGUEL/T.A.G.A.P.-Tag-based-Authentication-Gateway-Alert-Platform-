"""
T.A.G.A.P. - Repositories

Data-access layer. Each repository is a class with static/class methods
that encapsulate a specific entity's queries.

Design:
- No SQL in services or UI.
- All DB operations use `get_db()` context manager.
- Return plain ORM objects or DTOs.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from core.constants import CardType, SmsStatus
from data.database import get_db
from models import (
    Alert,
    Analytics,
    AuditLog,
    Card,
    Parent,
    PoliceStation,
    Room,
    School,
    SmsQueue,
    SmsTemplate,
    Student,
)


# ============================================================
# School
# ============================================================

class SchoolRepository:
    @staticmethod
    def get_or_create_default(name: str, hotline: str) -> School:
        with get_db() as db:
            school = db.scalar(select(School).limit(1))
            if school is None:
                school = School(name=name, hotline=hotline)
                db.add(school)
                db.flush()
            return school

    @staticmethod
    def get(db: Session) -> Optional[School]:
        return db.scalar(select(School).limit(1))


# ============================================================
# Police Station
# ============================================================

class PoliceStationRepository:
    @staticmethod
    def get_for_school(db: Session, school_id: int) -> list[PoliceStation]:
        return list(db.scalars(select(PoliceStation).where(PoliceStation.school_id == school_id)))


# ============================================================
# Room
# ============================================================

class RoomRepository:
    @staticmethod
    def get_by_name(db: Session, name: str) -> Optional[Room]:
        return db.scalar(select(Room).where(Room.name == name))


# ============================================================
# Card
# ============================================================

class CardRepository:
    @staticmethod
    def get_by_uid(uid: str) -> Optional[Card]:
        with get_db() as db:
            return db.scalar(
                select(Card)
                .options(joinedload(Card.room).joinedload(Room.school))
                .where(Card.uid == uid, Card.active.is_(True))
            )

    @staticmethod
    def get_all_active(db: Session) -> list[Card]:
        return list(db.scalars(select(Card).where(Card.active.is_(True))))


# ============================================================
# Parent lookup (by room)
# ============================================================

class ParentRepository:
    @staticmethod
    def get_for_room(db: Session, room_id: int) -> list[Parent]:
        """
        Return every unique parent whose child is in the given room.
        Uses join through students to deduplicate.
        """
        stmt = (
            select(Parent)
            .join(Parent.students)
            .where(Student.room_id == room_id)
            .distinct()
        )
        return list(db.scalars(stmt))


# ============================================================
# SMS Template
# ============================================================

class SmsTemplateRepository:
    @staticmethod
    def get(db: Session, card_type: CardType, recipient_type: str) -> Optional[SmsTemplate]:
        return db.scalar(
            select(SmsTemplate).where(
                SmsTemplate.card_type == card_type.value,
                SmsTemplate.recipient_type == recipient_type,
            )
        )

    @staticmethod
    def upsert(db: Session, card_type: CardType, recipient_type: str, text: str) -> SmsTemplate:
        existing = SmsTemplateRepository.get(db, card_type, recipient_type)
        if existing:
            existing.template_text = text
            return existing
        tpl = SmsTemplate(
            card_type=card_type.value, recipient_type=recipient_type, template_text=text
        )
        db.add(tpl)
        return tpl


# ============================================================
# Alert
# ============================================================

class AlertRepository:
    @staticmethod
    def create(
        db: Session,
        *,
        card_uid: str,
        card_type: CardType,
        room_id: int,
        triggered_at: datetime,
    ) -> Alert:
        alert = Alert(
            card_uid=card_uid,
            card_type=card_type.value,
            room_id=room_id,
            triggered_at=triggered_at,
        )
        db.add(alert)
        db.flush()
        return alert

    @staticmethod
    def recent(db: Session, limit: int = 20) -> list[Alert]:
        return list(db.scalars(select(Alert).order_by(Alert.created_at.desc()).limit(limit)))


# ============================================================
# SMS Queue
# ============================================================

class SmsQueueRepository:
    @staticmethod
    def enqueue(
        db: Session,
        *,
        alert_id: int,
        recipient_type: str,
        phone_number: str,
        message: str,
    ) -> SmsQueue:
        row = SmsQueue(
            alert_id=alert_id,
            recipient_type=recipient_type,
            phone_number=phone_number,
            message=message,
            status=SmsStatus.PENDING.value,
        )
        db.add(row)
        return row

    @staticmethod
    def fetch_pending(db: Session, limit: int = 10) -> list[SmsQueue]:
        return list(
            db.scalars(
                select(SmsQueue)
                .where(SmsQueue.status.in_([SmsStatus.PENDING.value, SmsStatus.FAILED.value]))
                .order_by(SmsQueue.created_at.asc())
                .limit(limit)
            )
        )

    @staticmethod
    def mark_sent(db: Session, row: SmsQueue, *, sent_at: datetime) -> None:
        row.status = SmsStatus.SENT.value
        row.sent_at = sent_at
        row.attempts += 1

    @staticmethod
    def mark_failed(db: Session, row: SmsQueue, *, reason: str) -> None:
        row.status = SmsStatus.FAILED.value
        row.attempts += 1
        row.failure_reason = reason[:255]


# ============================================================
# Deduplication check
# ============================================================

class DeduplicationChecker:
    @staticmethod
    def is_duplicate(db: Session, card_uid: str, window_seconds: int) -> bool:
        """Return True if this card was confirmed within the window."""
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
        latest = db.scalar(
            select(Alert)
            .where(Alert.card_uid == card_uid)
            .where(Alert.confirmed_at.is_not(None))
            .where(Alert.confirmed_at >= cutoff)
            .limit(1)
        )
        return latest is not None


# ============================================================
# Audit log
# ============================================================

class AuditLogRepository:
    @staticmethod
    def log(db: Session, *, event_type: str, payload_json: str = "{}") -> None:
        db.add(AuditLog(event_type=event_type, payload_json=payload_json))


# ============================================================
# Analytics
# ============================================================

class AnalyticsRepository:
    @staticmethod
    def create(
        db: Session,
        *,
        alert_id: int,
        scan_ts: datetime,
        confirm_ts: Optional[datetime] = None,
        queue_ts: Optional[datetime] = None,
        sent_ts: Optional[datetime] = None,
    ) -> Analytics:
        row = Analytics(
            alert_id=alert_id,
            scan_ts=scan_ts,
            confirm_ts=confirm_ts,
            queue_ts=queue_ts,
            sent_ts=sent_ts,
        )
        if confirm_ts:
            row.response_time_ms = int((confirm_ts - scan_ts).total_seconds() * 1000)
        if sent_ts and queue_ts:
            row.delivery_time_ms = int((sent_ts - queue_ts).total_seconds() * 1000)
        db.add(row)
        return row