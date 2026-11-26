from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

import models
from core.constants import CardType
from data import repositories
from models import Card, CardCategory, Parent, Room, School, Student, SmsTemplate


def _repository_db(monkeypatch):
    database_engine = create_engine("sqlite:///:memory:")
    models.Base.metadata.create_all(database_engine)

    @contextmanager
    def test_get_db():
        with Session(database_engine) as session:
            yield session
            session.commit()

    monkeypatch.setattr(repositories, "get_db", test_get_db)
    with Session(database_engine) as session:
        school = School(name="Test School", hotline="000")
        room = Room(school=school, name="Room 201")
        other_room = Room(school=school, name="Room 202")
        session.add_all((room, other_room))
        session.commit()
        room_ids = (room.id, other_room.id)
    return database_engine, room_ids


def test_roster_saves_students_and_reuses_contacts_by_phone(monkeypatch):
    database_engine, (room_id, _) = _repository_db(monkeypatch)

    repositories.StudentRepository.save_room_roster(
        room_id,
        [
            {
                "student_id": None,
                "parent_id": None,
                "student_name": "Ari Santos",
                "contact_name": "Mina Santos",
                "phone": "+639171234567",
            }
        ],
    )
    saved = repositories.StudentRepository.get_room_roster(room_id)
    assert saved[0]["student_name"] == "Ari Santos"
    assert saved[0]["contact_name"] == "Mina Santos"

    repositories.StudentRepository.save_room_roster(
        room_id,
        [
            {
                **saved[0],
                "student_name": "Ari Santos Jr.",
                "contact_name": "Mina Santos",
                "phone": "+639171234567",
            },
            {
                "student_id": None,
                "parent_id": None,
                "student_name": "Bea Santos",
                "contact_name": "Mina Santos",
                "phone": "+639171234567",
            },
            {
                "student_id": saved[0]["student_id"],
                "parent_id": None,
                "student_name": "Ari Santos Jr.",
                "contact_name": "Other Guardian",
                "phone": "+639171234568",
            },
        ],
    )

    with Session(database_engine) as session:
        assert session.scalar(select(func.count(Student.id))) == 2
        assert session.scalar(select(func.count(Parent.id))) == 2
        assert session.scalar(select(Student.name).where(Student.name == "Ari Santos Jr.")) == "Ari Santos Jr."
        ari = session.scalar(select(Student).where(Student.name == "Ari Santos Jr."))
        assert len(ari.parents) == 2
        shared_parent = session.scalar(
            select(Parent).where(Parent.phone_number == "+639171234567")
        )
        assert len(shared_parent.students) == 2
    database_engine.dispose()


def test_roster_rejects_partial_contact_rows(monkeypatch):
    _, (room_id, _) = _repository_db(monkeypatch)

    with pytest.raises(ValueError, match="both contact name and phone"):
        repositories.StudentRepository.save_room_roster(
            room_id,
            [
                {
                    "student_name": "Ari Santos",
                    "contact_name": "Mina Santos",
                    "phone": "",
                }
            ],
        )


def test_roster_requires_matching_student_names_across_contact_rows(monkeypatch):
    _, (room_id, _) = _repository_db(monkeypatch)
    repositories.StudentRepository.save_room_roster(
        room_id,
        [
            {
                "student_name": "Ari Santos",
                "contact_name": "First Guardian",
                "phone": "09170000001",
            }
        ],
    )
    saved = repositories.StudentRepository.get_room_roster(room_id)
    repositories.StudentRepository.save_room_roster(
        room_id,
        [
            saved[0],
            {
                "student_id": saved[0]["student_id"],
                "parent_id": None,
                "student_name": "Ari Santos",
                "contact_name": "Second Guardian",
                "phone": "09170000002",
            },
        ],
    )
    saved = repositories.StudentRepository.get_room_roster(room_id)

    with pytest.raises(ValueError, match="same across all"):
        repositories.StudentRepository.save_room_roster(
            room_id,
            [
                {**saved[0], "student_name": "Ari Santos Jr."},
                {**saved[1], "student_name": "Ari Santos"},
            ],
        )


def test_card_registration_and_activation_control_reader_admin_access(monkeypatch):
    database_engine, (room_id, other_room_id) = _repository_db(monkeypatch)

    assert not repositories.CardRepository.has_active_admin_card(room_id)
    repositories.CardRepository.register(room_id, "A1B2C3D4", CardType.ADMIN)
    assert repositories.CardRepository.has_active_admin_card(room_id)
    assert repositories.CardRepository.is_active_admin_uid(room_id, "A1B2C3D4")

    card = repositories.CardRepository.get_for_room(room_id)[0]
    repositories.CardRepository.set_active(int(card["id"]), False)
    assert not repositories.CardRepository.has_active_admin_card(room_id)

    with pytest.raises(ValueError, match="another room"):
        repositories.CardRepository.register(other_room_id, "A1B2C3D4", CardType.ADMIN)

    with Session(database_engine) as session:
        saved = session.scalar(select(Card).where(Card.uid == "A1B2C3D4"))
        assert saved is not None
        assert saved.active is False
    database_engine.dispose()


def test_custom_card_categories_route_cards_and_can_be_deactivated(monkeypatch):
    database_engine, (room_id, _) = _repository_db(monkeypatch)

    category_name = repositories.CardCategoryRepository.create("Fire Drill")
    repositories.CardRepository.register(room_id, "F1RE1234", category_name)
    card = repositories.CardRepository.get_for_room(room_id)[0]
    assert category_name == "FIRE DRILL"
    assert card["type"] == "FIRE DRILL"
    assert category_name in repositories.CardCategoryRepository.get_active()
    with Session(database_engine) as session:
        stored_card = session.scalar(select(Card).where(Card.uid == "F1RE1234"))
        assert stored_card.card_type == "FIRE DRILL"

    repositories.CardCategoryRepository.deactivate(category_name)

    assert category_name not in repositories.CardCategoryRepository.get_active()
    assert repositories.CardRepository.get_for_room(room_id)[0]["active"] is False
    with Session(database_engine) as session:
        stored_category = session.get(CardCategory, category_name)
        assert stored_category.active is False
        assert session.scalar(
            select(SmsTemplate.id).where(SmsTemplate.card_type == category_name)
        ) is None
    database_engine.dispose()


def test_operational_settings_are_validated_and_persisted(monkeypatch):
    database_engine, _ = _repository_db(monkeypatch)
    from config import settings

    monkeypatch.setattr(settings, "DEDUPLICATION_WINDOW_SECONDS", 60)
    monkeypatch.setattr(settings, "CONFIRMATION_TIMEOUT_SECONDS", 3)
    monkeypatch.setattr(settings, "SMS_RETRY_ATTEMPTS", 3)

    values = {
        "dedup_window": 90,
        "confirmation_timeout": 15,
        "sms_retry_attempts": 5,
    }
    repositories.OperationalSettingsRepository.save(values)
    assert settings.DEDUPLICATION_WINDOW_SECONDS == 90
    assert settings.CONFIRMATION_TIMEOUT_SECONDS == 15
    assert settings.SMS_RETRY_ATTEMPTS == 5

    monkeypatch.setattr(settings, "DEDUPLICATION_WINDOW_SECONDS", 60)
    monkeypatch.setattr(settings, "CONFIRMATION_TIMEOUT_SECONDS", 3)
    monkeypatch.setattr(settings, "SMS_RETRY_ATTEMPTS", 3)
    repositories.OperationalSettingsRepository.load_into_runtime()
    assert settings.DEDUPLICATION_WINDOW_SECONDS == 90
    assert settings.CONFIRMATION_TIMEOUT_SECONDS == 15
    assert settings.SMS_RETRY_ATTEMPTS == 5

    with pytest.raises(ValueError, match="between 1 and 10"):
        repositories.OperationalSettingsRepository.save({"sms_retry_attempts": 11})
    database_engine.dispose()
