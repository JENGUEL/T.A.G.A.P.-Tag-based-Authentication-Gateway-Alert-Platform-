"""
T.A.G.A.P. - Seed Data

Populates the DB with a demo school, room, RFID cards, students, parents,
and SMS templates. Idempotent — safe to run multiple times.
"""

from __future__ import annotations

import logging

from core.constants import CardType
from data.database import get_db, init_db
from models import (
    AppSetting,
    Card,
    CardCategory,
    Parent,
    PoliceStation,
    Room,
    School,
    Student,
    SmsTemplate,
)

logger = logging.getLogger(__name__)


DEFAULT_TEMPLATES = {
    (CardType.ONGOING, "PARENT"): (
        "ST. MARY'S ACADEMY OF PALO\n\n"
        "This is to inform you that the SCHOOL LOCKDOWN DRILL for {grade_section} "
        "is currently ongoing as of {time} on {date}.\n\n"
        "Students and school personnel are following the established safety protocols. "
        "Please remain calm and wait for further official announcements from the school.\n\n"
        "This is a scheduled drill. Thank you.\n\n"
        "Sent via T.A.G.A.P. Communication System"
    ),
    (CardType.END, "PARENT"): (
        "ST. MARY'S ACADEMY OF PALO\n\n"
        "This is to inform you that the SCHOOL LOCKDOWN DRILL for {grade_section} "
        "has officially concluded as of {time} on {date}.\n\n"
        "Students and school personnel have completed the drill in accordance with "
        "the school's established safety protocols. Please wait for further official "
        "announcements regarding the resumption of regular school activities.\n\n"
        "Thank you for your cooperation.\n\n"
        "Sent via T.A.G.A.P. Communication System"
    ),
}


def seed() -> None:
    init_db()

    with get_db() as db:
        # --- School ---
        school = db.query(School).first()
        if not school:
            school = School(name="St. Mary's Academy of Palo, Leyte, Inc.", hotline="0917-000-0000")
            db.add(school)
            db.flush()
            logger.info("Seeded school: %s", school.name)
        elif school.name != "St. Mary's Academy of Palo, Leyte, Inc.":
            school.name = "St. Mary's Academy of Palo, Leyte, Inc."
            logger.info("Updated school name: %s", school.name)

        # --- Police station ---
        if not db.query(PoliceStation).first():
            db.add(PoliceStation(
                school_id=school.id,
                name="San Jose Police Station",
                phone_number="0999-000-1111",
            ))
            logger.info("Seeded police station")

        # --- Room ---
        room = db.query(Room).filter_by(name="Room 201").first()
        if not room:
            room = Room(
                school_id=school.id,
                name="Room 201",
                room_number="201",
                section="Grade 7 - Section A",
                wing="",
                floor="2nd Floor",
            )
            db.add(room)
            db.flush()
            logger.info("Seeded room: %s", room.name)
        else:
            if not room.room_number:
                room.room_number = (
                    room.name[5:]
                    if room.name.lower().startswith("room ")
                    else room.name
                )
            if not room.section:
                room.section = "Grade 11 – Section A"
            elif room.section == "Grade 7 - Section A":
                room.section = "Grade 11 – Section A"

        for category_name in (CardType.ONGOING.value, CardType.END.value):
            if db.get(CardCategory, category_name) is None:
                db.add(CardCategory(name=category_name, active=True))
        db.flush()

        migration_key = "legacy_alert_cards_retired_v1"
        if db.get(AppSetting, migration_key) is None:
            legacy_types = (
                CardType.SAFE.value,
                CardType.ASSIST.value,
                CardType.DANGER.value,
            )
            for category_name in legacy_types:
                category = db.get(CardCategory, category_name)
                if category is not None:
                    category.active = False
            db.query(Card).filter(Card.type.in_(legacy_types)).update(
                {Card.active: False},
                synchronize_session=False,
            )
            db.add(AppSetting(key=migration_key, value="1"))

        # --- Cards ---
        card_uids = {
            CardType.ONGOING: "CARD-ONGOING-0001",
            CardType.END: "CARD-END-0001",
        }
        for ctype, uid in card_uids.items():
            category = db.get(CardCategory, ctype.value)
            if (
                category is not None
                and category.active
                and not db.query(Card).filter_by(uid=uid).first()
            ):
                db.add(Card(uid=uid, type=ctype.value, room_id=room.id, active=True))
        demo_admin_card = db.query(Card).filter_by(uid="CARD-ADMIN-0001").first()
        if demo_admin_card is not None and demo_admin_card.active:
            demo_admin_card.active = False
        logger.info("Seeded %d demo alert cards for room %s", len(card_uids), room.name)

        # --- Students + Parents ---
        if db.query(Student).filter_by(room_id=room.id).count() == 0:
            demo_students = [
                ("Juan Dela Cruz", [("Maria Dela Cruz", "0917-111-0001")]),
                ("Ana Reyes",      [("Pedro Reyes",      "0917-111-0002")]),
                ("Carlo Santos",   [("Rosa Santos",      "0917-111-0003")]),
            ]
            for sname, parents in demo_students:
                student = Student(name=sname, room_id=room.id)
                db.add(student)
                db.flush()
                for pname, phone in parents:
                    parent = db.query(Parent).filter_by(phone_number=phone).first()
                    if not parent:
                        parent = Parent(name=pname, phone_number=phone)
                        db.add(parent)
                        db.flush()
                    student.parents.append(parent)
            logger.info("Seeded demo students + parents")

        # --- SMS Templates ---
        for (ctype, rtype), text in DEFAULT_TEMPLATES.items():
            category = db.get(CardCategory, ctype.value)
            if category is not None and category.active:
                existing = db.query(SmsTemplate).filter_by(
                    card_type=ctype.value,
                    recipient_type=rtype,
                ).first()
                if existing is None:
                    db.add(
                        SmsTemplate(
                            card_type=ctype.value,
                            recipient_type=rtype,
                            template_text=text,
                        )
                    )
        logger.info("Seeded %d SMS templates", len(DEFAULT_TEMPLATES))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    seed()
    print("✅ Seed complete.")