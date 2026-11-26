import asyncio

import flet as ft

from ui.screens.admin import settings as settings_screen


class FakePage:
    def __init__(self):
        self.overlay = []
        self.dialog = None

    def show_dialog(self, dialog):
        self.dialog = dialog

    def pop_dialog(self):
        return None

    def update(self):
        return None


def _walk(control):
    yield control
    for child in getattr(control, "controls", []) or []:
        yield from _walk(child)
    content = getattr(control, "content", None)
    if content is not None:
        yield from _walk(content)


def test_settings_exposes_roster_cards_and_editable_sms_templates(monkeypatch):
    monkeypatch.setattr(
        settings_screen.queries,
        "get_room_info",
        lambda _: {
            "room_name": "Room 201",
            "grade_section": "Grade 8 - Section A",
            "floor": "2nd Floor",
            "school_name": "Test School",
            "wing": "North",
        },
    )
    monkeypatch.setattr(
        settings_screen.queries,
        "get_settings_snapshot",
        lambda _: {
            "system_name": "T.A.G.A.P.",
            "room_id": "TAGAP-RD-001",
            "dedup_window": 60,
            "confirmation_timeout": 3,
            "sms_retry_attempts": 3,
            "mock_rfid": False,
            "mock_sms": False,
            "cards": [{"id": 4, "uid": "A1B2C3D4", "type": "ADMIN", "active": True}],
            "categories": ["SAFE", "ASSIST", "DANGER", "CUSTOM"],
            "templates": [
                {
                    "id": 1,
                    "card_type": "ASSIST",
                    "recipient_type": "PARENT",
                    "text": "Help requested at {room_name}",
                }
            ],
        },
    )
    monkeypatch.setattr(
        settings_screen.queries,
        "get_queue_stats",
        lambda: {"pending": 0, "sent": 0, "failed": 0},
    )
    monkeypatch.setattr(
        settings_screen.StudentRepository,
        "get_room_roster",
        lambda _: [],
    )
    saved_settings = []
    monkeypatch.setattr(
        settings_screen.OperationalSettingsRepository,
        "save",
        lambda values: saved_settings.append(values),
    )
    saved_templates = []
    monkeypatch.setattr(
        settings_screen.AlertService,
        "update_sms_template",
        lambda card_type, recipient_type, text: saved_templates.append(
            (card_type, recipient_type, text)
        )
        or True,
    )
    monkeypatch.setattr(settings_screen.Toast, "show", lambda *_args, **_kwargs: None)

    registered = []
    page = FakePage()
    view = settings_screen.build_settings(
        page,
        1,
        lambda _: None,
        lambda: None,
        on_register_card=registered.append,
    )
    controls = list(_walk(view))

    assert isinstance(view, ft.View)
    assert any(
        isinstance(control, ft.TextField)
        and control.value == "Help requested at {room_name}"
        for control in controls
    )
    assert any(
        isinstance(control, ft.Text)
        and control.value == "Students & Contacts"
        for control in controls
    )
    register_assist = next(
        control
        for control in controls
        if isinstance(control, ft.OutlinedButton)
        and control.content == "Register Assist"
    )
    register_assist.on_click(None)
    assert registered == ["ASSIST"]
    register_custom = next(
        control
        for control in controls
        if isinstance(control, ft.OutlinedButton)
        and control.content == "Register Custom"
    )
    register_custom.on_click(None)
    assert registered == ["ASSIST", "CUSTOM"]
    assert not any(
        isinstance(control, ft.Text) and "Wing" in str(control.value)
        for control in controls
    )

    template_field = next(
        control
        for control in controls
        if isinstance(control, ft.TextField)
        and control.value == "Help requested at {room_name}"
    )
    template_field.value = "Updated message for {room_name}"
    save_template = next(
        control
        for control in controls
        if isinstance(control, ft.OutlinedButton)
        and control.content == "Save Template"
    )
    asyncio.run(save_template.on_click(None))
    assert saved_templates == [
        ("ASSIST", "PARENT", "Updated message for {room_name}")
    ]

    dedup_field = next(
        control
        for control in controls
        if isinstance(control, ft.TextField)
        and control.label == "Deduplication window (seconds)"
    )
    confirmation_field = next(
        control
        for control in controls
        if isinstance(control, ft.TextField)
        and control.label == "RFID confirmation timeout (seconds)"
    )
    retry_field = next(
        control
        for control in controls
        if isinstance(control, ft.TextField)
        and control.label == "SMS retry attempts"
    )
    dedup_field.value = "120"
    confirmation_field.value = "20"
    retry_field.value = "4"
    save_settings = next(
        control
        for control in controls
        if isinstance(control, ft.Button)
        and control.content == "Save Device & Alert Settings"
    )
    asyncio.run(save_settings.on_click(None))
    assert saved_settings == [
        {
            "dedup_window": 120,
            "confirmation_timeout": 20,
            "sms_retry_attempts": 4,
        }
    ]
