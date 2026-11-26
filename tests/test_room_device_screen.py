import asyncio

import flet as ft

from ui.screens.admin import room_device


class FakePage:
    def __init__(self):
        self.overlay = []
        self.dialog = None
        self.pop_dialog_calls = 0

    def update(self):
        return None

    def show_dialog(self, dialog):
        self.dialog = dialog

    def pop_dialog(self):
        self.pop_dialog_calls += 1


def _mock_room_queries(monkeypatch):
    monkeypatch.setattr(
        room_device.queries,
        "get_room_info",
        lambda _: {
            "room_name": "Room 201",
            "room_number": "201",
            "section": "Grade 8 - Section A",
            "wing": "North",
            "floor": "2nd Floor",
            "quick_actions": [],
        },
    )
    monkeypatch.setattr(
        room_device.queries, "get_alert_history_stats", lambda: {"total_rfid": 0}
    )
    monkeypatch.setattr(room_device.queries, "get_parents_for_room", lambda _: [])
    monkeypatch.setattr(room_device.queries, "get_dashboard_data", lambda: {})


def _build_screen(monkeypatch, page, registered, on_room_updated=lambda: None):
    _mock_room_queries(monkeypatch)
    return room_device.build_room_device(
        page,
        1,
        lambda _: None,
        lambda: None,
        reader_connected=True,
        reader_port="COM3",
        on_room_updated=on_room_updated,
        register_controls=registered.update,
    )


def test_room_device_screen_builds_and_registers_live_controls(monkeypatch):
    registered = {}

    view = _build_screen(monkeypatch, FakePage(), registered)

    assert isinstance(view, ft.View)
    assert registered["reader_status"].value == "Reader Connected"
    assert registered["scan_test_button"].disabled is False
    assert registered["last_uid"].value == "No UID captured yet"
    assert len(registered["quick_actions_grid"].controls) == 4
    assert registered["quick_actions_grid"].controls[0].col == {"xs": 12, "sm": 6}


def test_students_and_contacts_quick_action_opens_shared_editor(monkeypatch):
    page = FakePage()
    registered = {}
    opened = []
    monkeypatch.setattr(
        room_device,
        "show_roster_editor",
        lambda target_page, room_id: opened.append((target_page, room_id)),
    )
    _build_screen(monkeypatch, page, registered)

    registered["quick_actions_grid"].controls[0].on_click(None)

    assert opened == [(page, 1)]


def test_room_info_dialog_close_and_cancel_buttons_dismiss(monkeypatch):
    for close_with in ("icon", "cancel"):
        page = FakePage()
        registered = {}
        _build_screen(monkeypatch, page, registered)
        registered["edit_info_button"].on_click(None)
        dialog = page.dialog

        close_button = (
            dialog.title.controls[1]
            if close_with == "icon"
            else dialog.actions[0]
        )
        close_button.on_click(None)

        assert page.pop_dialog_calls == 1


def test_saving_room_info_closes_dialog_after_success(monkeypatch):
    page = FakePage()
    registered = {}
    saved = {}
    updated = []
    _build_screen(
        monkeypatch,
        page,
        registered,
        on_room_updated=lambda: updated.append(True),
    )
    monkeypatch.setattr(
        room_device.RoomRepository,
        "update_device_info",
        lambda room_id, **values: saved.update(room_id=room_id, **values),
    )
    monkeypatch.setattr(room_device.Toast, "show", lambda *_args, **_kwargs: None)
    registered["edit_info_button"].on_click(None)
    dialog = page.dialog
    room_number, section, floor = dialog.content.content.controls
    room_number.value = "305"
    section.value = "Grade 8 - Section C"
    floor.value = "3rd Floor"

    asyncio.run(dialog.actions[1].on_click(None))

    assert page.pop_dialog_calls == 1
    assert saved == {
        "room_id": 1,
        "room_number": "305",
        "section": "Grade 8 - Section C",
        "floor": "3rd Floor",
    }
    assert updated == [True]
