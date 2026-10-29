"""
T.A.G.A.P. - Admin > Settings (Image 2) — Read-Only View
"""
import flet as ft
from typing import Callable
from ui.theme import *
from data import queries


def _section(title: str, content: ft.Control) -> ft.Control:
    return ft.Container(
        padding=ft.Padding.all(20),
        bgcolor=CARD_WHITE,
        border=ft.Border.all(1, BORDER_COLOR),
        border_radius=12,
        content=ft.Column(
            tight=True, spacing=12,
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


def build_settings(page: ft.Page, room_id: int, on_navigate: Callable, on_exit: Callable):
    info = queries.get_room_info(room_id)
    snap = queries.get_settings_snapshot(room_id)
    queue = queries.get_queue_stats()

    content = ft.Column(
        spacing=16,
        controls=[
            # Page header
            ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                controls=[
                    ft.Column(
                        tight=True, spacing=2,
                        controls=[
                            ft.Text("Settings", size=24, weight=ft.FontWeight.BOLD, color=INK),
                            ft.Text(
                                f"{info.get('room_name', '')} · {info.get('grade_section', '')} · {info.get('floor', '')}",
                                size=11, color=MUTED,
                            ),
                        ],
                    ),
                ],
            ),
            # Info strip
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=14, vertical=10),
                bgcolor="#FBE9EC",
                border=ft.Border.all(1, "#F4D9DE"),
                border_radius=8,
                content=ft.Row(
                    tight=True, spacing=8,
                    controls=[
                        ft.Icon(ft.Icons.SHIELD_OUTLINED, size=14, color=PRIMARY_RED),
                        ft.Text("Settings are read-only in this phase.", size=10,
                                color=INK),
                        ft.Container(expand=True),
                        ft.Text("Editing comes in Sprint 6.5", size=10,
                                color=MUTED, italic=True),
                    ],
                ),
            ),
            # General System
            _section(
                "General System",
                ft.Column(
                    tight=True, spacing=10,
                    controls=[
                        _row("System Name", snap["system_name"]),
                        _row("Room ID", snap["room_id"]),
                        _row("School", info.get("school_name", "")),
                        _row("Wing", info.get("wing", "")),
                        _row("Floor", info.get("floor", "")),
                    ],
                ),
            ),
            # Hardware & RFID
            _section(
                "Devices & RFID",
                ft.Column(
                    tight=True, spacing=10,
                    controls=[
                        _row("Mock RFID Mode", str(snap["mock_rfid"])),
                        _row("Mock SMS Mode", str(snap["mock_sms"])),
                        _row("Dedup Window", f"{snap['dedup_window']} seconds"),
                        _row("Confirmation Timeout", f"{snap['confirmation_timeout']} seconds"),
                        _row("SMS Retry Attempts", str(snap["sms_retry_attempts"])),
                    ],
                ),
            ),
            # Registered Cards
            _section(
                "Registered RFID Cards",
                ft.Column(
                    tight=True, spacing=6,
                    controls=[
                        ft.Row(
                            controls=[
                                ft.Text(c["type"], size=11, weight=ft.FontWeight.W_600, color=INK),
                                ft.Container(expand=True),
                                ft.Text(c["uid"], size=11, color=MUTED),
                                ft.Container(width=8),
                                ft.Container(
                                    padding=ft.Padding.symmetric(horizontal=6, vertical=2),
                                    bgcolor="#E8F5F0" if c["active"] else "#FBE9EC",
                                    border_radius=4,
                                    content=ft.Text(
                                        "Active" if c["active"] else "Inactive",
                                        size=9,
                                        color=SUCCESS_GREEN if c["active"] else PRIMARY_RED,
                                    ),
                                ),
                            ],
                        ) for c in snap["cards"]
                    ],
                ),
            ),
            # SMS Queue Status
            _section(
                "SMS Queue Status",
                ft.Column(
                    tight=True, spacing=10,
                    controls=[
                        _row("Pending", str(queue["pending"])),
                        _row("Sent", str(queue["sent"])),
                        _row("Failed", str(queue["failed"])),
                    ],
                ),
            ),
            # Templates
            _section(
                "SMS Templates",
                ft.Column(
                    tight=True, spacing=10,
                    controls=[
                        ft.Container(
                            padding=ft.Padding.all(10),
                            bgcolor=ADMIN_CONTENT_BG,
                            border_radius=8,
                            content=ft.Column(
                                tight=True, spacing=4,
                                controls=[
                                    ft.Text(f"{t['card_type']} → {t['recipient_type']}",
                                            size=10, weight=ft.FontWeight.W_600,
                                            color=PRIMARY_RED),
                                    ft.Text(t["text"], size=10, color=INK),
                                ],
                            ),
                        ) for t in snap["templates"]
                    ],
                ),
            ),
        ],
    )

    from ui.screens.admin.shell import build_admin_shell
    return build_admin_shell(
        page,
        active_page="Settings",
        room_name=info.get("room_name", "Room"),
        on_navigate=on_navigate,
        on_back_to_kiosk=on_exit,
        content=ft.Column(scroll=ft.ScrollMode.AUTO, controls=[content]),
    )