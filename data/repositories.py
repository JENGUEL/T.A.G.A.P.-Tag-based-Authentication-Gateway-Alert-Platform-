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
from sqlalchemy.orm import Session, joinedload, selectinload

from core.constants import CardType, SmsStatus, card_type_value
from data.database import get_db
from models import (
    Alert,
    Analytics,
    AppSetting,
    AuditLog,
    Card,
    CardCategory,
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

    @staticmethod
    def update_device_info(
        room_id: int,
        *,
        room_number: str,
        section: str,
        floor: str,
    ) -> None:
        with get_db() as db:
            room = db.get(Room, room_id)
            if room is None:
                raise LookupError(f"Room {room_id} does not exist")
            room.name = f"Room {room_number}"
            room.room_number = room_number
            room.section = section
            room.floor = floor

    @staticmethod
    def update_quick_actions(
        room_id: int,
        actions: list[dict[str, object]],
    ) -> None:
        with get_db() as db:
            room = db.get(Room, room_id)
            if room is None:
                raise LookupError(f"Room {room_id} does not exist")
            room.quick_actions = actions


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

    @staticmethod
    def get_for_room(room_id: int) -> list[dict[str, object]]:
        with get_db() as db:
            cards = db.scalars(
                select(Card)
                .where(Card.room_id == room_id)
                .order_by(Card.type, Card.uid)
            ).all()
            return [
                {
                    "id": card.id,
                    "uid": card.uid,
                    "type": card.type,
                    "active": card.active,
                }
                for card in cards
            ]

    @staticmethod
    def has_active_admin_card(room_id: int) -> bool:
        with get_db() as db:
            return db.scalar(
                select(Card.id)
                .where(
                    Card.room_id == room_id,
                    Card.type == CardType.ADMIN.value,
                    Card.active.is_(True),
                )
                .limit(1)
            ) is not None

    @staticmethod
    def is_active_admin_uid(room_id: int, uid: str) -> bool:
        with get_db() as db:
            return db.scalar(
                select(Card.id)
                .where(
                    Card.room_id == room_id,
                    Card.uid == uid,
                    Card.type == CardType.ADMIN.value,
                    Card.active.is_(True),
                )
                .limit(1)
            ) is not None

    @staticmethod
    def register(room_id: int, uid: str, card_type: CardType | str) -> None:
        normalized_uid = uid.strip()
        if not normalized_uid:
            raise ValueError("A scanned card UID is required.")
        normalized_type = card_type_value(card_type)
        with get_db() as db:
            if normalized_type != CardType.ADMIN.value:
                category = db.get(CardCategory, normalized_type)
                if category is None or not category.active:
                    raise ValueError(
                        f"Alert category {normalized_type} is not active."
                    )
            card = db.scalar(select(Card).where(Card.uid == normalized_uid))
            if card is not None and card.room_id != room_id:
                raise ValueError("This card is already assigned to another room.")
            if card is None:
                card = Card(
                    uid=normalized_uid,
                    type=normalized_type,
                    room_id=room_id,
                )
                db.add(card)
            else:
                card.type = normalized_type
                card.active = True

    @staticmethod
    def set_active(card_id: int, active: bool) -> None:
        with get_db() as db:
            card = db.get(Card, card_id)
            if card is None:
                raise LookupError(f"Card {card_id} does not exist.")
            card.active = active

    @staticmethod
    def delete(card_id: int) -> None:
        with get_db() as db:
            card = db.get(Card, card_id)
            if card is None:
                raise LookupError(f"Card {card_id} does not exist.")
            db.delete(card)


class CardCategoryRepository:
    @staticmethod
    def get_active() -> list[str]:
        with get_db() as db:
            return list(
                db.scalars(
                    select(CardCategory.name)
                    .where(CardCategory.active.is_(True))
                    .order_by(CardCategory.name)
                )
            )

    @staticmethod
    def create(name: str) -> str:
        normalized = " ".join(name.strip().upper().split())
        if not normalized or len(normalized) > 32:
            raise ValueError("Category names must contain 1 to 32 characters.")
        if normalized == CardType.ADMIN.value:
            raise ValueError("ADMIN is reserved for system access.")
        if any(not (character.isalnum() or character in " -_") for character in normalized):
            raise ValueError("Use only letters, numbers, spaces, hyphens, or underscores.")

        with get_db() as db:
            category = db.get(CardCategory, normalized)
            if category is None:
                category = CardCategory(name=normalized, active=True)
                db.add(category)
            elif category.active:
                raise ValueError(f"{normalized} already exists.")
            else:
                category.active = True

            for recipient_type, text in (
                (
                    "PARENT",
                    f"[T.A.G.A.P.] {normalized}: Alert in {{room_name}} at {{timestamp}}. "
                    "Please follow school instructions. — {school_name}",
                ),
                (
                    "POLICE",
                    f"[T.A.G.A.P.] {normalized} alert at {{school_name}}, {{room_name}} "
                    "({floor}) at {timestamp}. Hotline: {school_hotline}",
                ),
            ):
                SmsTemplateRepository.upsert(db, normalized, recipient_type, text)
        return normalized

    @staticmethod
    def deactivate(name: str) -> None:
        normalized = card_type_value(name)
        if normalized == CardType.ADMIN.value:
            raise ValueError("ADMIN is reserved for system access.")
        with get_db() as db:
            category = db.get(CardCategory, normalized)
            if category is None or not category.active:
                raise LookupError(f"Active category {normalized} does not exist.")
            category.active = False
            db.query(Card).filter(Card.type == normalized).update(
                {Card.active: False},
                synchronize_session=False,
            )
            db.query(SmsTemplate).filter(
                SmsTemplate.card_type == normalized
            ).delete(synchronize_session=False)


class OperationalSettingsRepository:
    _SETTING_FIELDS = {
        "dedup_window": ("DEDUPLICATION_WINDOW_SECONDS", 1, 3600),
        "confirmation_timeout": ("CONFIRMATION_TIMEOUT_SECONDS", 1, 300),
        "sms_retry_attempts": ("SMS_RETRY_ATTEMPTS", 1, 10),
    }

    @classmethod
    def save(cls, values: dict[str, int]) -> None:
        from config import settings

        validated: dict[str, tuple[str, int]] = {}
        for key, value in values.items():
            if key not in cls._SETTING_FIELDS:
                raise ValueError(f"Unsupported operational setting: {key}")
            field_name, minimum, maximum = cls._SETTING_FIELDS[key]
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not minimum <= value <= maximum
            ):
                raise ValueError(
                    f"{key} must be between {minimum} and {maximum}."
                )
            validated[key] = (field_name, value)

        with get_db() as db:
            for key, (_, value) in validated.items():
                setting = db.get(AppSetting, key)
                if setting is None:
                    db.add(AppSetting(key=key, value=str(value)))
                else:
                    setting.value = str(value)

        for _, (field_name, value) in validated.items():
            setattr(settings, field_name, value)

    @classmethod
    def load_into_runtime(cls) -> None:
        from config import settings

        with get_db() as db:
            persisted = {
                row.key: row.value
                for row in db.scalars(select(AppSetting))
            }
        for key, (field_name, minimum, maximum) in cls._SETTING_FIELDS.items():
            if key not in persisted:
                continue
            try:
                value = int(persisted[key])
            except ValueError as exc:
                raise RuntimeError(
                    f"Persisted setting {key} is not a valid integer."
                ) from exc
            if not minimum <= value <= maximum:
                raise RuntimeError(f"Persisted setting {key} is out of range.")
            setattr(settings, field_name, value)


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


class StudentRepository:
    @staticmethod
    def get_room_roster(room_id: int) -> list[dict[str, object]]:
        with get_db() as db:
            students = db.scalars(
                select(Student)
                .options(selectinload(Student.parents))
                .where(Student.room_id == room_id)
                .order_by(Student.name, Student.id)
            ).all()
            rows: list[dict[str, object]] = []
            for student in students:
                parents = sorted(student.parents, key=lambda parent: parent.id)
                if not parents:
                    rows.append(
                        {
                            "student_id": student.id,
                            "parent_id": None,
                            "student_name": student.name,
                            "contact_name": "",
                            "phone": "",
                        }
                    )
                    continue
                rows.extend(
                    {
                        "student_id": student.id,
                        "parent_id": parent.id,
                        "student_name": student.name,
                        "contact_name": parent.name,
                        "phone": parent.phone_number,
                    }
                    for parent in parents
                )
            return rows

    @staticmethod
    def save_room_roster(room_id: int, records: list[dict[str, object]]) -> None:
        normalized_records: list[dict[str, object]] = []
        names_by_student_id: dict[int, str] = {}
        for record in records:
            student_name = str(record.get("student_name") or "").strip()
            contact_name = str(record.get("contact_name") or "").strip()
            phone = str(record.get("phone") or "").strip()
            student_id = record.get("student_id")
            parent_id = record.get("parent_id")
            if not student_name:
                raise ValueError("Every roster row needs a student name.")
            if bool(contact_name) != bool(phone):
                raise ValueError("Enter both contact name and phone, or leave both blank.")
            if len(phone) > 20:
                raise ValueError("Contact phone numbers must be 20 characters or fewer.")
            if student_id is not None:
                normalized_student_id = int(student_id)
                previous_name = names_by_student_id.get(normalized_student_id)
                if previous_name is not None and previous_name != student_name:
                    raise ValueError(
                        "Keep the student name the same across all of that student's contact rows."
                    )
                names_by_student_id[normalized_student_id] = student_name
            normalized_records.append(
                {
                    "student_id": int(student_id) if student_id is not None else None,
                    "parent_id": int(parent_id) if parent_id is not None else None,
                    "student_name": student_name,
                    "contact_name": contact_name,
                    "phone": phone,
                }
            )

        if not normalized_records:
            raise ValueError("Add at least one student before saving.")

        with get_db() as db:
            room_students = db.scalars(
                select(Student)
                .options(selectinload(Student.parents))
                .where(Student.room_id == room_id)
            ).all()
            students_by_id = {student.id: student for student in room_students}
            parents_in_room = {
                parent.id
                for student in room_students
                for parent in student.parents
            }
            desired_parents: dict[int, list[Parent]] = {}
            for record in normalized_records:
                student_id = record["student_id"]
                student = (
                    students_by_id.get(student_id)
                    if student_id is not None
                    else None
                )
                if student_id is not None and student is None:
                    raise ValueError("A student row no longer belongs to this room.")
                if student is None:
                    student = Student(
                        room_id=room_id,
                        name=str(record["student_name"]),
                    )
                    db.add(student)
                    db.flush()
                    students_by_id[student.id] = student
                else:
                    student.name = str(record["student_name"])

                parent: Parent | None = None
                parent_id = record["parent_id"]
                if parent_id is not None:
                    if parent_id not in parents_in_room:
                        raise ValueError("A contact row no longer belongs to this room.")
                    if record["contact_name"]:
                        parent = db.get(Parent, parent_id)
                        if parent is None:
                            raise ValueError("A contact row no longer exists.")
                elif record["phone"]:
                    parent = db.scalar(
                        select(Parent).where(Parent.phone_number == record["phone"])
                    )
                    if parent is None:
                        parent = Parent(
                            name=str(record["contact_name"]),
                            phone_number=str(record["phone"]),
                        )
                        db.add(parent)
                        db.flush()
                    else:
                        parent.name = str(record["contact_name"])
                        parents_in_room.add(parent.id)

                desired = desired_parents.setdefault(student.id, [])
                if parent is not None:
                    parent.name = str(record["contact_name"])
                    parent.phone_number = str(record["phone"])
                    if all(existing.id != parent.id for existing in desired):
                        desired.append(parent)

            for student_id, parents in desired_parents.items():
                students_by_id[student_id].parents = parents


# ============================================================
# SMS Template
# ============================================================

class SmsTemplateRepository:
    @staticmethod
    def get(
        db: Session, card_type: CardType | str, recipient_type: str
    ) -> Optional[SmsTemplate]:
        return db.scalar(
            select(SmsTemplate).where(
                SmsTemplate.card_type == card_type_value(card_type),
                SmsTemplate.recipient_type == recipient_type,
            )
        )

    @staticmethod
    def upsert(
        db: Session, card_type: CardType | str, recipient_type: str, text: str
    ) -> SmsTemplate:
        existing = SmsTemplateRepository.get(db, card_type, recipient_type)
        if existing:
            existing.template_text = text
            return existing
        tpl = SmsTemplate(
            card_type=card_type_value(card_type),
            recipient_type=recipient_type,
            template_text=text,
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
        card_type: CardType | str,
        room_id: int,
        triggered_at: datetime,
    ) -> Alert:
        alert = Alert(
            card_uid=card_uid,
            card_type=card_type_value(card_type),
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