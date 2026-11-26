import asyncio

import flet as ft

from config import settings
from core.constants import CardType
from models.sms_result_dto import AlertOutcome, AlertResult
from services.audio_service import AudioService
from ui.screens.confirmation import build_confirmation_screen


class FakePage:
    def update(self):
        pass

    def run_task(self, handler, *args):
        return asyncio.create_task(handler(*args))


def _find_button(control, label):
    if isinstance(control, ft.Button) and control.content == label:
        return control

    for child in getattr(control, "controls", []):
        found = _find_button(child, label)
        if found:
            return found

    content = getattr(control, "content", None)
    if isinstance(content, ft.Control):
        return _find_button(content, label)
    return None


def _alert_result():
    return AlertResult(
        outcome=AlertOutcome.NEEDS_CONFIRMATION,
        card_uid="04A1B2C3",
        card_type=CardType.SAFE,
        room_name="Room 201",
    )


def test_countdown_expiry_performs_no_alert_operation(monkeypatch):
    monkeypatch.setattr(settings, "CONFIRMATION_TIMEOUT_SECONDS", 0)
    monkeypatch.setattr(AudioService, "beep", lambda: None)

    async def scenario():
        confirmations = []
        cancellations = []
        timeouts = []
        page = FakePage()
        build_confirmation_screen(
            page,
            _alert_result(),
            lambda: confirmations.append(True),
            lambda: cancellations.append(True),
            lambda: timeouts.append(True),
        )
        await page.countdown_task
        return confirmations, cancellations, timeouts

    confirmations, cancellations, timeouts = asyncio.run(scenario())

    assert confirmations == []
    assert cancellations == []
    assert timeouts == [True]


def test_only_explicit_confirm_runs_confirmation_callback(monkeypatch):
    monkeypatch.setattr(AudioService, "beep", lambda: None)

    async def scenario():
        confirmations = []
        timeouts = []
        page = FakePage()
        view = build_confirmation_screen(
            page,
            _alert_result(),
            lambda: confirmations.append(True),
            lambda: None,
            lambda: timeouts.append(True),
        )
        confirm_button = _find_button(view, "CONFIRM ALERT")
        assert confirm_button is not None
        await asyncio.sleep(0)
        confirm_button.on_click(None)
        await page.countdown_task
        return confirmations, timeouts

    confirmations, timeouts = asyncio.run(scenario())
    assert confirmations == [True]
    assert timeouts == []


def test_explicit_cancel_cancels_without_confirming(monkeypatch):
    monkeypatch.setattr(AudioService, "beep", lambda: None)

    async def scenario():
        confirmations = []
        cancellations = []
        page = FakePage()
        view = build_confirmation_screen(
            page,
            _alert_result(),
            lambda: confirmations.append(True),
            lambda: cancellations.append(True),
            lambda: None,
        )
        cancel_button = _find_button(view, "CANCEL")
        assert cancel_button is not None
        await asyncio.sleep(0)
        cancel_button.on_click(None)
        await page.countdown_task
        return confirmations, cancellations

    confirmations, cancellations = asyncio.run(scenario())
    assert confirmations == []
    assert cancellations == [True]
