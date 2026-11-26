from contextlib import contextmanager

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import models
from data import seed as seed_module
from models import Card, Room, School


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
    database_engine.dispose()
