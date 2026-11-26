"""Editable student and contact roster dialog shared by Settings and Quick Actions."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Callable

import flet as ft

from data.repositories import StudentRepository
from ui.components.toast import Toast
from ui.theme import BORDER_COLOR, CARD_WHITE, INK, MUTED, PRIMARY_RED, SUCCESS_GREEN

logger = logging.getLogger(__name__)

_COLUMN_WIDTHS = (220, 220, 180)
_ACCENT_BLUE = "#4169D8"
_PAGE_BG = "#F6F7F9"
_SOFT_TEXT = "#697586"


@dataclass
class _RosterRowControls:
    student_id: int | None
    parent_id: int | None
    student: ft.TextField
    contact: ft.TextField
    phone: ft.TextField


def show_roster_editor(
    page: ft.Page,
    room_id: int,
    on_saved: Callable[[], None] | None = None,
) -> None:
    records = StudentRepository.get_room_roster(room_id)
    if not records:
        records = [
            {
                "student_id": None,
                "parent_id": None,
                "student_name": "",
                "contact_name": "",
                "phone": "",
            }
        ]

    row_controls: list[_RosterRowControls] = []
    rows = ft.Column(spacing=7, controls=[])
    row_count = ft.Text(size=11, color=_SOFT_TEXT)
    contact_count = ft.Text(size=11, color=_SOFT_TEXT)

    def update_summary() -> None:
        row_count.value = f"{len(row_controls)} roster rows"
        contact_total = sum(
            1 for row_state in row_controls
            if (row_state.contact.value or "").strip()
            or (row_state.phone.value or "").strip()
        )
        contact_count.value = f"{contact_total} contacts"
        try:
            row_count.update()
            contact_count.update()
        except RuntimeError:
            pass

    def input_field(
        value: str,
        hint: str,
        width: int,
        max_length: int,
        *,
        phone: bool = False,
    ) -> ft.TextField:
        return ft.TextField(
            value=value,
            hint_text=hint,
            width=width,
            dense=True,
            max_length=max_length,
            text_size=12,
            filled=True,
            fill_color="#FAFBFD",
            border_color="#E5E9F0",
            focused_border_color=_ACCENT_BLUE,
            border_radius=9,
            content_padding=ft.Padding.symmetric(horizontal=11, vertical=10),
            keyboard_type=ft.KeyboardType.PHONE if phone else ft.KeyboardType.TEXT,
        )

    def build_row(record: dict[str, object] | None = None) -> ft.Control:
        record = record or {}
        raw_student_id = record.get("student_id")
        raw_parent_id = record.get("parent_id")
        student = input_field(
            str(record.get("student_name") or ""),
            "Student full name",
            _COLUMN_WIDTHS[0],
            200,
        )
        contact = input_field(
            str(record.get("contact_name") or ""),
            "Parent / guardian name",
            _COLUMN_WIDTHS[1],
            200,
        )
        phone = input_field(
            str(record.get("phone") or ""),
            "Mobile number",
            _COLUMN_WIDTHS[2],
            20,
            phone=True,
        )
        row_state = _RosterRowControls(
            student_id=int(raw_student_id) if raw_student_id is not None else None,
            parent_id=int(raw_parent_id) if raw_parent_id is not None else None,
            student=student,
            contact=contact,
            phone=phone,
        )
        row_controls.append(row_state)
        contact.on_change = lambda _event=None: update_summary()
        phone.on_change = lambda _event=None: update_summary()

        def sync_student_name(_event=None) -> None:
            if row_state.student_id is None:
                return
            for other in row_controls:
                if other is row_state or other.student_id != row_state.student_id:
                    continue
                other.student.value = student.value
                try:
                    other.student.update()
                except RuntimeError:
                    pass

        student.on_change = sync_student_name

        def add_contact(_event=None) -> None:
            if row_state.student_id is None:
                Toast.show(
                    page,
                    "Save this student before adding another contact.",
                    "warning",
                )
                return
            rows.controls.append(
                build_row(
                    {
                        "student_id": row_state.student_id,
                        "parent_id": None,
                        "student_name": student.value,
                    }
                )
            )
            update_summary()
            page.update()

        def remove_unsaved(_event=None) -> None:
            if row_state.student_id is not None:
                Toast.show(page, "Saved roster rows cannot be removed from this editor.", "warning")
                return
            row_controls.remove(row_state)
            rows.controls.remove(row)
            update_summary()
            page.update()

        add_contact_button = ft.IconButton(
            icon=ft.Icons.PERSON_ADD_ALT_1_ROUNDED,
            icon_color=_ACCENT_BLUE,
            tooltip="Add another contact for this student",
            disabled=row_state.student_id is None,
            on_click=add_contact,
        )
        remove_button = ft.IconButton(
            icon=ft.Icons.DELETE_OUTLINE_ROUNDED,
            icon_color="#9AA4B2",
            tooltip="Remove unsaved row",
            disabled=row_state.student_id is not None,
            on_click=remove_unsaved,
        )
        row = ft.Container(
            padding=ft.Padding.symmetric(horizontal=11, vertical=7),
            bgcolor=CARD_WHITE,
            border=ft.Border.all(1, "#E8ECF2"),
            border_radius=11,
            content=ft.Row(
                spacing=9,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    student,
                    contact,
                    phone,
                    ft.Container(
                        width=76,
                        content=ft.Row(
                            tight=True,
                            spacing=0,
                            controls=[add_contact_button, remove_button],
                        ),
                    ),
                ],
            ),
        )
        return row

    rows.controls = [build_row(record) for record in records]
    update_summary()

    def column_heading(label: str, width: int) -> ft.Container:
        return ft.Container(
            width=width,
            padding=ft.Padding.only(left=9, bottom=5),
            content=ft.Text(
                label.upper(),
                size=9,
                color=_SOFT_TEXT,
                weight=ft.FontWeight.BOLD,
            ),
        )

    def add_row(_event=None) -> None:
        rows.controls.append(build_row())
        update_summary()
        page.update()

    async def save_roster(_event=None) -> None:
        payload: list[dict[str, object]] = []
        for row_state in row_controls:
            payload.append(
                {
                    "student_id": row_state.student_id,
                    "parent_id": row_state.parent_id,
                    "student_name": row_state.student.value,
                    "contact_name": row_state.contact.value,
                    "phone": row_state.phone.value,
                }
            )
        try:
            await asyncio.to_thread(
                StudentRepository.save_room_roster,
                room_id,
                payload,
            )
        except ValueError as exc:
            Toast.show(page, str(exc), "warning")
            return
        except Exception as exc:
            logger.exception("Could not save room student/contact roster")
            Toast.show(page, f"Could not save roster: {exc}", "error")
            return

        page.pop_dialog()
        if on_saved:
            on_saved()
        Toast.show(page, "Student and contact records saved.", "success")

    title = ft.Row(
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Row(
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Container(
                        width=44,
                        height=44,
                        alignment=ft.Alignment.CENTER,
                        bgcolor="#EEF2FF",
                        border_radius=13,
                        content=ft.Icon(
                            ft.Icons.GROUPS_2_OUTLINED,
                            size=23,
                            color=_ACCENT_BLUE,
                        ),
                    ),
                    ft.Column(
                        tight=True,
                        spacing=3,
                        controls=[
                            ft.Text(
                                "Students & Contacts",
                                size=20,
                                weight=ft.FontWeight.BOLD,
                                color="#202A3B",
                            ),
                            ft.Text(
                                "Manage the people who receive room alerts.",
                                size=11,
                                color=_SOFT_TEXT,
                            ),
                        ],
                    ),
                ],
            ),
            ft.IconButton(
                icon=ft.Icons.CLOSE_ROUNDED,
                tooltip="Close",
                icon_color=_SOFT_TEXT,
                on_click=lambda _: page.pop_dialog(),
            ),
        ],
    )

    summary = ft.Row(
        spacing=10,
        controls=[
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=13, vertical=9),
                bgcolor="#FFFFFF",
                border=ft.Border.all(1, "#E8ECF2"),
                border_radius=10,
                content=ft.Row(
                    tight=True,
                    spacing=7,
                    controls=[
                        ft.Icon(ft.Icons.SCHOOL_OUTLINED, size=16, color=_ACCENT_BLUE),
                        row_count,
                    ],
                ),
            ),
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=13, vertical=9),
                bgcolor="#FFFFFF",
                border=ft.Border.all(1, "#E8ECF2"),
                border_radius=10,
                content=ft.Row(
                    tight=True,
                    spacing=7,
                    controls=[
                        ft.Icon(ft.Icons.PHONELINK_RING_OUTLINED, size=15, color=SUCCESS_GREEN),
                        contact_count,
                    ],
                ),
            ),
            ft.Container(expand=True),
            ft.OutlinedButton(
                content="Add student",
                icon=ft.Icons.PERSON_ADD_ALT_1_ROUNDED,
                on_click=add_row,
            ),
        ],
    )

    grid_header = ft.Container(
        padding=ft.Padding.only(left=17, right=80, top=5, bottom=3),
        content=ft.Row(
            spacing=9,
            controls=[
                column_heading("Student", _COLUMN_WIDTHS[0]),
                column_heading("Parent / contact", _COLUMN_WIDTHS[1]),
                column_heading("Phone number", _COLUMN_WIDTHS[2]),
            ],
        ),
    )

    roster_card = ft.Container(
        expand=True,
        padding=ft.Padding.all(12),
        bgcolor="#FFFFFF",
        border=ft.Border.all(1, "#E6EAF0"),
        border_radius=14,
        content=ft.Column(
            expand=True,
            spacing=7,
            controls=[
                grid_header,
                ft.Column(
                    expand=True,
                    spacing=7,
                    scroll=ft.ScrollMode.AUTO,
                    controls=[rows],
                ),
            ],
        ),
    )

    how_it_works = ft.Container(
        width=245,
        padding=ft.Padding.all(15),
        bgcolor="#FFFFFF",
        border=ft.Border.all(1, "#E6EAF0"),
        border_radius=14,
        content=ft.Column(
            tight=True,
            spacing=12,
            controls=[
                ft.Row(
                    spacing=8,
                    controls=[
                        ft.Text(
                            "How it works",
                            size=13,
                            weight=ft.FontWeight.BOLD,
                            color="#202A3B",
                        ),
                        ft.Icon(
                            ft.Icons.INFO_OUTLINE_ROUNDED,
                            size=16,
                            color=_SOFT_TEXT,
                        ),
                    ],
                ),
                ft.Row(
                    vertical_alignment=ft.CrossAxisAlignment.START,
                    spacing=9,
                    controls=[
                        ft.Container(
                            width=24,
                            height=24,
                            alignment=ft.Alignment.CENTER,
                            bgcolor="#EAF0FF",
                            border_radius=12,
                            content=ft.Text("1", size=10, color=_ACCENT_BLUE,
                                            weight=ft.FontWeight.BOLD),
                        ),
                        ft.Column(tight=True, spacing=2, controls=[
                            ft.Text("Add students", size=11, weight=ft.FontWeight.W_600, color=INK),
                            ft.Text("Enter each student's name in the roster.", size=9, color=_SOFT_TEXT),
                        ]),
                    ],
                ),
                ft.Row(
                    vertical_alignment=ft.CrossAxisAlignment.START,
                    spacing=9,
                    controls=[
                        ft.Container(
                            width=24,
                            height=24,
                            alignment=ft.Alignment.CENTER,
                            bgcolor="#EAF0FF",
                            border_radius=12,
                            content=ft.Text("2", size=10, color=_ACCENT_BLUE,
                                            weight=ft.FontWeight.BOLD),
                        ),
                        ft.Column(tight=True, spacing=2, controls=[
                            ft.Text("Add contacts", size=11, weight=ft.FontWeight.W_600, color=INK),
                            ft.Text("Include a guardian and mobile number.", size=9, color=_SOFT_TEXT),
                        ]),
                    ],
                ),
                ft.Row(
                    vertical_alignment=ft.CrossAxisAlignment.START,
                    spacing=9,
                    controls=[
                        ft.Container(
                            width=24,
                            height=24,
                            alignment=ft.Alignment.CENTER,
                            bgcolor="#EAF0FF",
                            border_radius=12,
                            content=ft.Text("3", size=10, color=_ACCENT_BLUE,
                                            weight=ft.FontWeight.BOLD),
                        ),
                        ft.Column(tight=True, spacing=2, controls=[
                            ft.Text("Save the roster", size=11, weight=ft.FontWeight.W_600, color=INK),
                            ft.Text("Saved contacts receive room alert SMS.", size=9, color=_SOFT_TEXT),
                        ]),
                    ],
                ),
                ft.Container(
                    padding=ft.Padding.all(10),
                    bgcolor="#F2F7F5",
                    border_radius=9,
                    content=ft.Row(
                        vertical_alignment=ft.CrossAxisAlignment.START,
                        spacing=7,
                        controls=[
                            ft.Icon(ft.Icons.LOCK_OUTLINE, size=14, color=SUCCESS_GREEN),
                            ft.Text(
                                "Changes are stored locally in the school database.",
                                size=9,
                                color="#52685F",
                            ),
                        ],
                    ),
                ),
            ],
        ),
    )

    help_row = ft.Row(
        spacing=14,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Container(
                expand=True,
                padding=ft.Padding.only(left=3),
                content=ft.Text(
                    "Use the person-plus icon on a saved student to add another guardian. "
                    "For a new student, save first, then add additional contacts.",
                    size=9,
                    color=_SOFT_TEXT,
                ),
            ),
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=11, vertical=8),
                bgcolor="#F1F4F8",
                border_radius=9,
                content=ft.Text(
                    "Room alert recipients",
                    size=9,
                    color="#536174",
                    weight=ft.FontWeight.W_600,
                ),
            ),
        ],
    )

    workspace = ft.Row(
        expand=True,
        spacing=12,
        vertical_alignment=ft.CrossAxisAlignment.STRETCH,
        controls=[
            roster_card,
            how_it_works,
        ],
    )

    page.show_dialog(
        ft.AlertDialog(
            modal=True,
            bgcolor=_PAGE_BG,
            title=title,
            content=ft.Container(
                width=1040,
                height=560,
                content=ft.Column(
                    expand=True,
                    spacing=12,
                    controls=[
                        summary,
                        workspace,
                        help_row,
                    ],
                ),
            ),
            actions=[
                ft.TextButton(
                    content="Cancel",
                    on_click=lambda _: page.pop_dialog(),
                ),
                ft.Button(
                    content="Save roster",
                    icon=ft.Icons.SAVE_OUTLINED,
                    bgcolor=PRIMARY_RED,
                    color=ft.Colors.WHITE,
                    on_click=save_roster,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
    )
