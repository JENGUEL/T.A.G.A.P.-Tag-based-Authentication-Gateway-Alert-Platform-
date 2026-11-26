"""Editable operational settings for the active room."""

from __future__ import annotations

import asyncio
import logging
from typing import Callable

import flet as ft

from core.constants import CardType
from data import queries
from data.repositories import CardRepository, StudentRepository
from services.alert_service import AlertService, validate_sms_template
from ui.components.roster_editor import show_roster_editor
from ui.components.toast import Toast
from ui.screens.admin.shell import build_admin_shell
from ui.theme import (
    ADMIN_CONTENT_BG,
    BORDER_COLOR,
    CARD_WHITE,
    INK,
    MUTED,
    PRIMARY_RED,
    SUCCESS_GREEN,
)

logger = logging.getLogger(__name__)


def _section(title: str, content: ft.Control) -> ft.Control:
    return ft.Container(
        padding=ft.Padding.all(18),
        bgcolor=CARD_WHITE,
        border=ft.Border.all(1, BORDER_COLOR),
        border_radius=12,
        content=ft.Column(
            tight=True,
            spacing=12,
            controls=[
                ft.Text(title, size=14, weight=ft.FontWeight.W_600, color=INK),
                ft.Divider(height=1, color=BORDER_COLOR),
                content,
            ],
        ),
    )


def _row(label: str, value: str) -> ft.Row:
    return ft.Row(
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        controls=[
            ft.Text(label, size=11, color=MUTED),
            ft.Text(value, size=11, weight=ft.FontWeight.W_600, color=INK),
        ],
    )


def build_settings(
    page: ft.Page,
    room_id: int,
    on_navigate: Callable[[str], None],
    on_exit: Callable[[], None],
    on_register_card: Callable[[str], None] | None = None,
    on_card_updated: Callable[[], None] | None = None,
) -> ft.View:
    info = queries.get_room_info(room_id)
    snapshot = queries.get_settings_snapshot(room_id)
    queue = queries.get_queue_stats()
    roster_count = len(StudentRepository.get_room_roster(room_id))

    roster_summary = ft.Text(
        f"{roster_count} student/contact rows currently saved for this room.",
        size=10,
        color=MUTED,
    )

    def refresh_roster_summary() -> None:
        roster_summary.value = (
            f"{len(StudentRepository.get_room_roster(room_id))} "
            "student/contact rows currently saved for this room."
        )
        page.update()

    def open_roster_editor(_event=None) -> None:
        show_roster_editor(page, room_id, refresh_roster_summary)

    roster_section = _section(
        "Students & Contacts",
        ft.Column(
            tight=True,
            spacing=8,
            controls=[
                ft.Text(
                    "Edit the room roster in a spreadsheet-style grid. Changes are saved to the database "
                    "and used for alert recipients.",
                    size=10,
                    color=MUTED,
                ),
                roster_summary,
                ft.Button(
                    content="Manage Students & Contacts",
                    icon=ft.Icons.GROUPS_OUTLINED,
                    on_click=open_roster_editor,
                ),
            ],
        ),
    )

    def build_card_rows() -> ft.Column:
        rows: list[ft.Control] = []
        for card in snapshot["cards"]:
            card_id = int(card["id"])
            card_type = str(card["type"])
            active = bool(card["active"])

            async def toggle_card(_event=None, card_id=card_id, active=active) -> None:
                try:
                    await asyncio.to_thread(CardRepository.set_active, card_id, not active)
                except Exception as exc:
                    logger.exception("Could not update registered card state")
                    Toast.show(page, f"Could not update card: {exc}", "error")
                    return
                Toast.show(page, "Card status updated.", "success")
                if on_card_updated:
                    on_card_updated()

            rows.append(
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                    border=ft.Border.all(1, BORDER_COLOR),
                    border_radius=8,
                    content=ft.Row(
                        spacing=10,
                        controls=[
                            ft.Text(
                                card_type,
                                width=75,
                                size=10,
                                weight=ft.FontWeight.W_600,
                                color=PRIMARY_RED,
                            ),
                            ft.Text(card["uid"], expand=True, size=10, color=INK),
                            ft.Text(
                                "Active" if active else "Inactive",
                                size=10,
                                color=SUCCESS_GREEN if active else MUTED,
                            ),
                            ft.TextButton(
                                content="Disable" if active else "Enable",
                                on_click=toggle_card,
                            ),
                        ],
                    ),
                )
            )
        if not rows:
            rows.append(ft.Text("No cards registered for this room.", size=10, color=MUTED))
        return ft.Column(spacing=6, controls=rows)

    register_buttons = [
        ft.OutlinedButton(
            content=f"Register {card_type.value.title()}",
            icon=ft.Icons.ADD_CARD,
            disabled=on_register_card is None,
            on_click=(
                lambda _, value=card_type.value: on_register_card(value)
                if on_register_card
                else None
            ),
        )
        for card_type in CardType
    ]

    cards_section = _section(
        "Registered RFID Cards",
        ft.Column(
            spacing=10,
            controls=[
                ft.Text(
                    "Register or disable SAFE, ASSIST, DANGER, and ADMIN cards. Enrollment requires "
                    "two matching scans and an explicit save.",
                    size=10,
                    color=MUTED,
                ),
                ft.ResponsiveRow(
                    spacing=8,
                    run_spacing=8,
                    controls=[
                        ft.Container(col={"xs": 6, "md": 3}, content=button)
                        for button in register_buttons
                    ],
                ),
                build_card_rows(),
            ],
        ),
    )

    async def save_template(
        card_type: str,
        recipient_type: str,
        field: ft.TextField,
        _event=None,
    ) -> None:
        try:
            parsed_type = CardType(card_type)
        except ValueError:
            Toast.show(page, f"Unsupported card type: {card_type}", "error")
            return
        text = (field.value or "").strip()
        if not text:
            Toast.show(page, "SMS templates cannot be empty.", "warning")
            return
        try:
            validate_sms_template(text)
        except ValueError as exc:
            Toast.show(page, str(exc), "warning")
            return
        saved = await asyncio.to_thread(
            AlertService.update_sms_template,
            parsed_type,
            recipient_type,
            text,
        )
        if not saved:
            Toast.show(page, "Could not save this SMS template. Check the application log.", "error")
            return
        Toast.show(page, f"{card_type} → {recipient_type} template saved.", "success")

    template_cards: list[ft.Control] = []
    for template in snapshot["templates"]:
        card_type = str(template["card_type"])
        recipient_type = str(template["recipient_type"])
        message = ft.TextField(
            value=str(template["text"]),
            multiline=True,
            min_lines=2,
            max_lines=5,
            max_length=480,
            expand=True,
            text_size=11,
        )
        template_cards.append(
            ft.Container(
                padding=ft.Padding.all(10),
                bgcolor=ADMIN_CONTENT_BG,
                border_radius=8,
                content=ft.Column(
                    spacing=8,
                    controls=[
                        ft.Row(
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            controls=[
                                ft.Text(
                                    f"{card_type} → {recipient_type}",
                                    size=10,
                                    weight=ft.FontWeight.W_600,
                                    color=PRIMARY_RED,
                                ),
                                ft.OutlinedButton(
                                    content="Save Template",
                                    icon=ft.Icons.SAVE_OUTLINED,
                                    on_click=lambda event, ct=card_type, rt=recipient_type, control=message: (
                                        save_template(ct, rt, control, event)
                                    ),
                                ),
                            ],
                        ),
                        message,
                    ],
                ),
            )
        )

    content = ft.Column(
        spacing=14,
        controls=[
            ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                controls=[
                    ft.Column(
                        tight=True,
                        spacing=2,
                        controls=[
                            ft.Text("Settings", size=24, weight=ft.FontWeight.BOLD, color=INK),
                            ft.Text(
                                f"{info.get('room_name', '')} · "
                                f"{info.get('grade_section', '')} · {info.get('floor', '')}",
                                size=11,
                                color=MUTED,
                            ),
                        ],
                    ),
                ],
            ),
            _section(
                "General System",
                ft.Column(
                    tight=True,
                    spacing=10,
                    controls=[
                        _row("System Name", snapshot["system_name"]),
                        _row("Room ID", snapshot["room_id"]),
                        _row("School", info.get("school_name", "")),
                        _row("Wing", info.get("wing", "")),
                        _row("Floor", info.get("floor", "")),
                    ],
                ),
            ),
            roster_section,
            cards_section,
            _section(
                "Devices & RFID",
                ft.Column(
                    tight=True,
                    spacing=10,
                    controls=[
                        _row("Mock RFID Mode", str(snapshot["mock_rfid"])),
                        _row("Mock SMS Mode", str(snapshot["mock_sms"])),
                        _row("Dedup Window", f"{snapshot['dedup_window']} seconds"),
                        _row(
                            "Confirmation Timeout",
                            f"{snapshot['confirmation_timeout']} seconds",
                        ),
                        _row("SMS Retry Attempts", str(snapshot["sms_retry_attempts"])),
                    ],
                ),
            ),
            _section(
                "SMS Queue Status",
                ft.Column(
                    tight=True,
                    spacing=10,
                    controls=[
                        _row("Pending", str(queue["pending"])),
                        _row("Sent", str(queue["sent"])),
                        _row("Failed", str(queue["failed"])),
                    ],
                ),
            ),
            _section(
                "SMS Message Templates",
                ft.Column(
                    spacing=8,
                    controls=[
                        ft.Text(
                            "Available fields: {room_name}, {wing}, {floor}, {school_name}, "
                            "{school_hotline}, {timestamp}. Invalid fields are rejected before saving.",
                            size=10,
                            color=MUTED,
                        ),
                        *(
                            template_cards
                            or [ft.Text("No templates are configured.", size=10, color=MUTED)]
                        ),
                    ],
                ),
            ),
        ],
    )

    return build_admin_shell(
        page,
        active_page="Settings",
        room_name=info.get("room_name", "Room"),
        on_navigate=on_navigate,
        on_back_to_kiosk=on_exit,
        content=ft.Column(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            controls=[content],
        ),
    )
