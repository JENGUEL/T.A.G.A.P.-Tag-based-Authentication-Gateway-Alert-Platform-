from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import models
from data import repositories
from models import (
    Alert,
    Card,
    Parent,
    PoliceStation,
    Room,
    School,
    SmsQueue,
    SmsTemplate,
    Student,
)
from services import alert_service
from services.alert_service import AlertService
from models.sms_result_dto import AlertOutcome


@pytest.mark.parametrize("card_type", ["ONGOING", "END", "FUTURE_ALERT"])
def test_lockdown_alert_queues_template_sms_to_parents_only(monkeypatch, card_type):
    database_engine = create_engine("sqlite:///:memory:")
    models.Base.metadata.create_all(database_engine)

    @contextmanager
    def test_get_db():
        with Session(database_engine, expire_on_commit=False) as session:
            yield session
            session.commit()

    monkeypatch.setattr(repositories, "get_db", test_get_db)
    monkeypatch.setattr(alert_service, "get_db", test_get_db)

    with Session(database_engine) as session:
        school = School(name="St. Mary's Academy of Palo", hotline="000")
        room = Room(
            school=school,
            name="Room 201",
            section="Grade 11 – Section A",
            floor="2nd Floor",
        )
        student = Student(name="Student", room=room)
        student.parents.append(Parent(name="Parent", phone_number="09170000000"))
        session.add_all(
            [
                room,
                student,
                PoliceStation(
                    school=school,
                    name="Test Police Station",
                    phone_number="09179999999",
                ),
                Card(
                    uid="LOCKDOWN-CARD",
                    type=card_type,
                    room=room,
                    active=True,
                ),
                SmsTemplate(
                    card_type=card_type,
                    recipient_type="PARENT",
                    template_text="{grade_section} | {time} | {date}",
                ),
            ]
        )
        session.commit()

    confirmed_at = datetime(2026, 11, 26, 10, 30, tzinfo=timezone.utc)
    result = AlertService.execute_alert(
        "LOCKDOWN-CARD",
        confirmed_at,
        confirmed_at=confirmed_at,
        scan_id="lockdown-test",
    )

    assert result.outcome == AlertOutcome.NEEDS_CONFIRMATION
    assert result.sms_queued == 1
    with Session(database_engine) as session:
        alert = session.scalar(select(Alert).where(Alert.card_uid == "LOCKDOWN-CARD"))
        messages = session.scalars(select(SmsQueue)).all()
        assert alert is not None
        assert alert.card_type == card_type
        assert len(messages) == 1
        assert messages[0].recipient_type == "PARENT"
        assert messages[0].phone_number == "09170000000"
        local_time = confirmed_at.astimezone()
        assert messages[0].message == (
            "Grade 11 – Section A | "
            f"{local_time.strftime('%I:%M %p')} | "
            f"{local_time.strftime('%B %d, %Y')}"
        )

    database_engine.dispose()
