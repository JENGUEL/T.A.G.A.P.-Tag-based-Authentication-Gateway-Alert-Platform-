import asyncio

import flet as ft
import pytest

from ui import router as router_module


class FakePage:
    def __init__(self):
        self.views = []
        self.dialog = None
        self.pop_dialog_calls = 0

    def show_dialog(self, dialog):
        self.dialog = dialog

    def pop_dialog(self):
        self.pop_dialog_calls += 1

    def update(self):
        return None


@pytest.fixture
def audio_calls(monkeypatch):
    calls = {"beep": 0, "error": 0}
    monkeypatch.setattr(
        router_module.AudioService,
        "beep",
        lambda: calls.__setitem__("beep", calls["beep"] + 1),
    )
    monkeypatch.setattr(
        router_module.AudioService,
        "error",
        lambda: calls.__setitem__("error", calls["error"] + 1),
    )
    return calls


def test_reader_monitor_routes_to_settings_when_admin_card_is_missing(monkeypatch):
    router = object.__new__(router_module.AppRouter)
    router.page = FakePage()
    router.room_id = 1
    opened = []
    router.show_admin = opened.append
    monkeypatch.setattr(
        router_module.CardRepository,
        "has_active_admin_card",
        lambda _: False,
    )
    monkeypatch.setattr(router_module.Toast, "show", lambda *_args, **_kwargs: None)

    router.show_reader_monitor()

    assert opened == ["Settings"]
    assert router.page.dialog is None


def test_reader_monitor_requires_a_registered_admin_card_scan(monkeypatch, audio_calls):
    router = object.__new__(router_module.AppRouter)
    router.page = FakePage()
    router.room_id = 1
    router.in_admin_mode = False
    router.current_alert = None
    router.reader_monitor_auth_pending = False
    router.reader_monitor_auth_dialog = None
    router.reader_monitor_auth_status = None
    opened = []
    router.show_admin = opened.append
    monkeypatch.setattr(
        router_module.CardRepository,
        "has_active_admin_card",
        lambda _: True,
    )
    monkeypatch.setattr(
        router_module.CardRepository,
        "is_active_admin_uid",
        lambda _room_id, uid: uid == "ADMIN-UID",
    )
    monkeypatch.setattr(
        router_module.AlertService,
        "record_operational_event",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(router_module.Toast, "show", lambda *_args, **_kwargs: None)

    router.show_reader_monitor()
    assert router.reader_monitor_auth_pending is True
    router.handle_card_scan("NON-ADMIN-UID")
    assert opened == []
    router.handle_card_scan("ADMIN-UID")

    assert opened == ["Reader Monitor"]
    assert router.reader_monitor_auth_pending is False
    assert router.page.pop_dialog_calls == 1
    assert audio_calls == {"beep": 2, "error": 1}


def test_card_enrollment_requires_confirmation_and_a_matching_second_scan(
    monkeypatch, audio_calls
):
    router = object.__new__(router_module.AppRouter)
    router.page = FakePage()
    router.room_id = 1
    router.current_alert = None
    router.in_admin_mode = True
    router.current_admin_section = "Settings"
    router.reader_monitor_auth_pending = False
    router.card_registration_session = None
    saved = []
    refreshed = []
    monkeypatch.setattr(
        router_module.AlertService,
        "record_operational_event",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        router_module.CardRepository,
        "register",
        lambda *args: saved.append(args),
    )
    monkeypatch.setattr(
        router_module.CardCategoryRepository,
        "get_active",
        lambda: ["SAFE", "ASSIST", "DANGER"],
    )
    monkeypatch.setattr(
        router,
        "_refresh_admin_content",
        lambda section: refreshed.append(section),
    )
    monkeypatch.setattr(router_module.Toast, "show", lambda *_args, **_kwargs: None)

    router._begin_card_registration("ASSIST")
    dialog = router.page.dialog
    router.handle_card_scan("04AABBCC")
    assert router.card_registration_session["stage"] == "confirm_first"
    assert "ASSIST" in dialog.content.content.controls[1].value
    dialog.actions[1].on_click(None)

    router.handle_card_scan("DIFFERENT")
    assert router.card_registration_session["stage"] == "scan_second"
    assert saved == []
    router.handle_card_scan("04AABBCC")
    assert router.card_registration_session["stage"] == "ready"
    assert saved == []

    asyncio.run(dialog.actions[1].on_click(None))

    assert saved[0][0:2] == (1, "04AABBCC")
    assert saved[0][2] == "ASSIST"
    assert router.card_registration_session is None
    assert refreshed == ["Settings"]
    assert router.page.pop_dialog_calls == 1
    assert audio_calls == {"beep": 3, "error": 1}
