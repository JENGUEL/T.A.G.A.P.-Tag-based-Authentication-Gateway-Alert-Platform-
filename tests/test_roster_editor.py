import asyncio

from ui.components import roster_editor


class FakePage:
    def __init__(self):
        self.dialog = None
        self.pop_dialog_calls = 0

    def show_dialog(self, dialog):
        self.dialog = dialog

    def pop_dialog(self):
        self.pop_dialog_calls += 1

    def update(self):
        return None


def test_roster_editor_persists_editable_grid_rows(monkeypatch):
    page = FakePage()
    saved = []
    notifications = []
    monkeypatch.setattr(roster_editor.StudentRepository, "get_room_roster", lambda _: [])
    monkeypatch.setattr(
        roster_editor.StudentRepository,
        "save_room_roster",
        lambda room_id, records: saved.append((room_id, records)),
    )
    monkeypatch.setattr(
        roster_editor.Toast,
        "show",
        lambda _page, message, kind: notifications.append((message, kind)),
    )
    updated = []

    roster_editor.show_roster_editor(page, 7, lambda: updated.append(True))
    dialog = page.dialog
    table_rows = dialog.content.content.controls[1]
    student, contact, phone, _add_contact, _remove = table_rows.controls[0].content.controls
    student.value = "Student Name"
    contact.value = "Contact Name"
    phone.value = "+639171234567"

    asyncio.run(dialog.actions[1].on_click(None))

    assert saved == [
        (
            7,
            [
                {
                    "student_id": None,
                    "parent_id": None,
                    "student_name": "Student Name",
                    "contact_name": "Contact Name",
                    "phone": "+639171234567",
                }
            ],
        )
    ]
    assert page.pop_dialog_calls == 1
    assert updated == [True]
    assert notifications[-1][1] == "success"


def test_roster_editor_can_add_another_contact_to_a_saved_student(monkeypatch):
    page = FakePage()
    monkeypatch.setattr(
        roster_editor.StudentRepository,
        "get_room_roster",
        lambda _: [
            {
                "student_id": 12,
                "parent_id": 31,
                "student_name": "Student Name",
                "contact_name": "First Contact",
                "phone": "09170000001",
            }
        ],
    )
    saved = []
    monkeypatch.setattr(
        roster_editor.StudentRepository,
        "save_room_roster",
        lambda room_id, records: saved.append((room_id, records)),
    )
    monkeypatch.setattr(roster_editor.Toast, "show", lambda *_args, **_kwargs: None)

    roster_editor.show_roster_editor(page, 4)
    dialog = page.dialog
    table_rows = dialog.content.content.controls[1]
    first_row = table_rows.controls[0].content
    first_row.controls[3].on_click(None)
    assert len(table_rows.controls) == 2
    added_fields = table_rows.controls[1].content.controls
    assert added_fields[0].value == "Student Name"
    assert added_fields[1].value == ""
    added_fields[1].value = "Second Contact"
    added_fields[2].value = "09170000002"

    asyncio.run(dialog.actions[1].on_click(None))

    assert saved[0][0] == 4
    assert saved[0][1][1]["student_id"] == 12
    assert saved[0][1][1]["parent_id"] is None
    assert saved[0][1][1]["contact_name"] == "Second Contact"
