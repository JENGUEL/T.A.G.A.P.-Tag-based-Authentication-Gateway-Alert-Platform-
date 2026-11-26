from contextlib import contextmanager

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import models
from data import repositories
from models import Room, School


def test_room_device_info_and_quick_actions_persist(monkeypatch):
    database_engine = create_engine("sqlite:///:memory:")
    models.Base.metadata.create_all(database_engine)
    with Session(database_engine) as session:
        school = School(name="Test School", hotline="000")
        room = Room(
            school=school,
            name="Room 201",
            room_number="201",
            section="Section A",
            floor="2nd Floor",
        )
        session.add(room)
        session.commit()
        room_id = room.id

    @contextmanager
    def test_get_db():
        with Session(database_engine) as session:
            yield session
            session.commit()

    monkeypatch.setattr(repositories, "get_db", test_get_db)
    actions = [
        {"key": "diagnostics", "label": "Check RFID", "enabled": True}
    ]

    RoomRepository = repositories.RoomRepository
    RoomRepository.update_device_info(
        room_id,
        room_number="305",
        section="Grade 8 - Section C",
        floor="3rd Floor",
    )
    RoomRepository.update_quick_actions(room_id, actions)

    with Session(database_engine) as session:
        saved = session.scalar(select(Room).where(Room.id == room_id))
        assert saved.name == "Room 305"
        assert saved.room_number == "305"
        assert saved.section == "Grade 8 - Section C"
        assert saved.floor == "3rd Floor"
        assert saved.quick_actions == actions
    database_engine.dispose()
