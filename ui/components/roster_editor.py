"""Editable student and contact roster dialog shared by Settings and Quick Actions."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Callable

import flet as ft

from data.repositories import StudentRepository
from ui.components.toast import Toast
from ui.theme import BORDER_COLOR, CARD_WHITE, INK, MUTED, PRIMARY_RED

logger = logging.getLogger(__name__)

_COLUMN_WIDTHS = (230, 230, 210)


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
    rows = ft.Column(spacing=6, controls=[])

    def build_row(record: dict[str, object] | None = None) -> ft.Control:
        record = record or {}
        raw_student_id = record.get("student_id")
        raw_parent_id = record.get("parent_id")
        student = ft.TextField(
            value=str(record.get("student_name") or ""),
            width=_COLUMN_WIDTHS[0],
            dense=True,
            max_length=200,
            text_size=11,
        )
        contact = ft.TextField(
            value=str(record.get("contact_name") or ""),
            width=_COLUMN_WIDTHS[1],
            dense=True,
            max_length=200,
            text_size=11,
        )
        phone = ft.TextField(
            value=str(record.get("phone") or ""),
            width=_COLUMN_WIDTHS[2],
            dense=True,
            max_length=20,
            text_size=11,
            keyboard_type=ft.KeyboardType.PHONE,
        )
        row_state = _RosterRowControls(
            student_id=int(raw_student_id) if raw_student_id is not None else None,
            parent_id=int(raw_parent_id) if raw_parent_id is not None else None,
            student=student,
            contact=contact,
            phone=phone,
        )
        row_controls.append(row_state)

        def sync_student_name(_event=None) -> None:
            if row_state.student_id is None:
                return
            for other in row_controls:
                if other is row_state or other.student_id != row_state.student_id:
                    continue
                other.student.value = student.value
                other.student.update()

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
            page.update()

        def remove_unsaved(_event=None) -> None:
            if row_state.student_id is not None:
                Toast.show(page, "Saved roster rows cannot be removed from this editor.", "warning")
                return
            row_controls.remove(row_state)
            rows.controls.remove(row)
            page.update()

        remove_button = ft.IconButton(
            icon=ft.Icons.REMOVE_CIRCLE_OUTLINE,
            icon_color=MUTED,
            tooltip="Remove unsaved row",
            disabled=row_state.student_id is not None,
            on_click=remove_unsaved,
        )
        add_contact_button = ft.IconButton(
            icon=ft.Icons.PERSON_ADD,
            icon_color=PRIMARY_RED,
            tooltip="Add another contact for this student",
            disabled=row_state.student_id is None,
            on_click=add_contact,
        )
        row = ft.Container(
            padding=ft.Padding.symmetric(horizontal=8, vertical=4),
            bgcolor=CARD_WHITE,
            border=ft.Border.all(1, BORDER_COLOR),
            border_radius=8,
            content=ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[student, contact, phone, add_contact_button, remove_button],
            ),
        )
        return row

    rows.controls = [build_row(record) for record in records]
    headers = ft.Row(
        spacing=8,
        controls=[
            ft.Container(
                width=width,
                padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                content=ft.Text(label, size=10, weight=ft.FontWeight.W_600, color=MUTED),
            )
            for label, width in zip(
                ("Student", "Parent / Contact", "Phone Number"),
                _COLUMN_WIDTHS,
            )
        ]
        + [ft.Container(width=80)],
    )

    def add_row(_event=None) -> None:
        rows.controls.append(build_row())
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

    page.show_dialog(
        ft.AlertDialog(
            modal=True,
            title=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                controls=[
                    ft.Column(
                        tight=True,
                        spacing=2,
                        controls=[
                            ft.Text("Students & Contacts", weight=ft.FontWeight.BOLD, color=INK),
                            ft.Text(
                                "Edit the room roster in a spreadsheet-style grid.",
                                size=10,
                                color=MUTED,
                            ),
                        ],
                    ),
                    ft.IconButton(
                        icon=ft.Icons.CLOSE,
                        tooltip="Close",
                        on_click=lambda _: page.pop_dialog(),
                    ),
                ],
            ),
            content=ft.Container(
                width=860,
                height=410,
                content=ft.Column(
                    spacing=8,
                    scroll=ft.ScrollMode.AUTO,
                    controls=[
                        headers,
                        rows,
                        ft.OutlinedButton(
                            content="Add student / contact row",
                            icon=ft.Icons.ADD,
                            on_click=add_row,
                        ),
                        ft.Text(
                            "Enter both contact name and phone number, or leave both blank. "
                            "Use the person-plus button to add another contact for a saved student. "
                            "New rows are added when saved.",
                            size=10,
                            color=MUTED,
                        ),
                    ],
                ),
            ),
            actions=[
                ft.TextButton(
                    content="Cancel",
                    on_click=lambda _: page.pop_dialog(),
                ),
                ft.Button(content="Save Roster", on_click=save_roster),
            ],
        )
    )
