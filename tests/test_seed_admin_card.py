from contextlib import contextmanager

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import models
from data import seed as seed_module
from models import Card, CardCategory, Room, School, SmsTemplate


def test_seed_deactivates_the_demo_admin_card_and_requires_enrollment(monkeypatch):
    database_engine = create_engine("sqlite:///:memory:")
    models.Base.metadata.create_all(database_engine)

    @contextmanager
    def test_get_db():
        with Session(database_engine) as session:
            yield session
            session.commit()

    with Session(database_engine) as session:
        school = School(name="Old Demo School", hotline="000")
        room = Room(school=school, name="Room 201")
        session.add(room)
        session.flush()
        session.add(
            Card(
                uid="CARD-ADMIN-0001",
                type="ADMIN",
                room_id=room.id,
                active=True,
            )
        )
        session.add(CardCategory(name="DANGER", active=True))
        session.add(
            Card(
                uid="CARD-DANGER-OLD",
                type="DANGER",
                room_id=room.id,
                active=True,
            )
        )
        session.commit()

    monkeypatch.setattr(seed_module, "get_db", test_get_db)
    monkeypatch.setattr(seed_module, "init_db", lambda: None)

    seed_module.seed()

    with Session(database_engine) as session:
        demo_admin = session.scalar(
            select(Card).where(Card.uid == "CARD-ADMIN-0001")
        )
        assert demo_admin is not None
        assert demo_admin.active is False
        assert session.scalar(
            select(Card.id).where(Card.type == "ADMIN", Card.active.is_(True))
        ) is None
        old_card = session.scalar(
            select(Card).where(Card.uid == "CARD-DANGER-OLD")
        )
        assert old_card is not None
        assert old_card.active is False
        assert session.get(CardCategory, "DANGER").active is False

        ongoing_card = session.scalar(
            select(Card).where(Card.type == "ONGOING", Card.active.is_(True))
        )
        end_card = session.scalar(
            select(Card).where(Card.type == "END", Card.active.is_(True))
        )
        assert ongoing_card is not None
        assert end_card is not None
        ongoing_template = session.scalar(
            select(SmsTemplate).where(
                SmsTemplate.card_type == "ONGOING",
                SmsTemplate.recipient_type == "PARENT",
            )
        )
        assert ongoing_template is not None
        assert ongoing_template.template_text == (
            "ST. MARY'S ACADEMY OF PALO\n\n"
            "This is to inform you that the SCHOOL LOCKDOWN DRILL for {grade_section} "
            "is currently ongoing as of {time} on {date}.\n\n"
            "Students and school personnel are following the established safety protocols. "
            "Please remain calm and wait for further official announcements from the school.\n\n"
            "This is a scheduled drill. Thank you.\n\n"
            "Sent via T.A.G.A.P. Communication System"
        )
        end_template = session.scalar(
            select(SmsTemplate).where(
                SmsTemplate.card_type == "END",
                SmsTemplate.recipient_type == "PARENT",
            )
        )
        assert end_template is not None
        assert end_template.template_text == (
            "ST. MARY'S ACADEMY OF PALO\n\n"
            "This is to inform you that the SCHOOL LOCKDOWN DRILL for {grade_section} "
            "has officially concluded as of {time} on {date}.\n\n"
            "Students and school personnel have completed the drill in accordance with "
            "the school's established safety protocols. Please wait for further official "
            "announcements regarding the resumption of regular school activities.\n\n"
            "Thank you for your cooperation.\n\n"
            "Sent via T.A.G.A.P. Communication System"
        )
        ongoing_template.template_text = "Admin edited this template."
        session.commit()

    seed_module.seed()

    with Session(database_engine) as session:
        ongoing_template = session.scalar(
            select(SmsTemplate).where(
                SmsTemplate.card_type == "ONGOING",
                SmsTemplate.recipient_type == "PARENT",
            )
        )
        assert ongoing_template.template_text == "Admin edited this template."
        assert session.scalar(
            select(SmsTemplate.id).where(SmsTemplate.recipient_type == "POLICE")
        ) is None
    database_engine.dispose()
