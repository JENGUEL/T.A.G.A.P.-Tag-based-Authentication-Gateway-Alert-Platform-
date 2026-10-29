"""
T.A.G.A.P. - Seed Data

Populates the DB with a demo school, police station, room, 4 cards,
students, parents, and SMS templates. Idempotent — safe to run multiple times.
"""

from __future__ import annotations

import logging

from core.constants import CardType
from data.database import get_db, init_db
from data.repositories import SmsTemplateRepository
from models import Card, Parent, PoliceStation, Room, School, Student, SmsTemplate

logger = logging.getLogger(__name__)


DEFAULT_TEMPLATES = {
    (CardType.SAFE, "PARENT"):
        "[T.A.G.A.P.] SAFE: Your child in {room_name} is safe. Reported at {timestamp}. No action needed. — {school_name}",
    (CardType.ASSIST, "PARENT"):
        "[T.A.G.A.P.] ASSIST: Assistance requested in {room_name} at {timestamp}. Please monitor for updates. — {school_name}",
    (CardType.DANGER, "PARENT"):
        "[T.A.G.A.P.] DANGER: Emergency in {room_name} at {timestamp}. Follow school instructions. Hotline: {school_hotline}.",

    (CardType.SAFE, "POLICE"):
        "[T.A.G.A.P.] SAFE status at {school_name}, {room_name} ({wing}) at {timestamp}. No emergency. — Hotline: {school_hotline}",
    (CardType.ASSIST, "POLICE"):
        "[T.A.G.A.P.] ASSIST request at {school_name}, {room_name} ({wing}) at {timestamp}. Situation requires attention. — Hotline: {school_hotline}",
    (CardType.DANGER, "POLICE"):
        "[T.A.G.A.P. EMERGENCY] ACTIVE THREAT at {school_name}, {room_name} ({wing}) at {timestamp}. Immediate response required. — Hotline: {school_hotline}",
}


def seed() -> None:
    init_db()

    with get_db() as db:
        # --- School ---
        school = db.query(School).first()
        if not school:
            school = School(name="San Jose National High School", hotline="0917-000-0000")
            db.add(school)
            db.flush()
            logger.info("Seeded school: %s", school.name)

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
                wing="North Wing",
                floor="2nd Floor",
            )
            db.add(room)
            db.flush()
            logger.info("Seeded room: %s", room.name)

        # --- Cards ---
        card_uids = {
            CardType.SAFE:   "CARD-SAFE-0001",
            CardType.ASSIST: "CARD-ASSIST-0001",
            CardType.DANGER: "CARD-DANGER-0001",
            CardType.ADMIN:  "CARD-ADMIN-0001",
        }
        for ctype, uid in card_uids.items():
            if not db.query(Card).filter_by(uid=uid).first():
                db.add(Card(uid=uid, type=ctype.value, room_id=room.id, active=True))
        logger.info("Seeded 4 cards for room %s", room.name)

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
            SmsTemplateRepository.upsert(db, ctype, rtype, text)
        logger.info("Seeded %d SMS templates", len(DEFAULT_TEMPLATES))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    seed()
    print("✅ Seed complete.")