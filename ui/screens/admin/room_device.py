"""
T.A.G.A.P. - Admin > Room Device Dashboard (Image 1)
"""
import flet as ft
from typing import Callable
from ui.theme import *
from data import queries


def _stat_tile(label: str, value: str, subtitle: str = "") -> ft.Control:
    return ft.Container(
        expand=True,
        padding=ft.Padding.all(16),
        bgcolor=ADMIN_CONTENT_BG,
        border_radius=10,
        content=ft.Column(
            tight=True, spacing=4,
            controls=[
                ft.Text(label, size=10, color=MUTED, weight=ft.FontWeight.W_600),
                ft.Text(value, size=20, weight=ft.FontWeight.BOLD, color=INK),
                ft.Text(subtitle, size=9, color=MUTED) if subtitle else ft.Container(),
            ],
        ),
    )


def _card(title: str, content: ft.Control, expand: bool = True) -> ft.Control:
    return ft.Container(
        expand=expand,
        padding=ft.Padding.all(20),
        bgcolor=CARD_WHITE,
        border=ft.Border.all(1, BORDER_COLOR),
        border_radius=12,
        content=ft.Column(
            tight=True, spacing=14,
            controls=[
                ft.Text(title, size=14, weight=ft.FontWeight.W_600, color=INK),
                content,
            ],
        ),
    )


def build_room_device(page: ft.Page, room_id: int, on_navigate: Callable, on_exit: Callable):
    info = queries.get_room_info(room_id)
    stats = queries.get_alert_history_stats()
    queue = queries.get_queue_stats()
    parents = queries.get_parents_for_room(room_id)
    dashboard = queries.get_dashboard_data()

    content = ft.Column(
        spacing=16,
        controls=[
            # Page header
            ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Column(
                        tight=True, spacing=2,
                        controls=[
                            ft.Text(info.get("room_name", "Room"), size=24,
                                    weight=ft.FontWeight.BOLD, color=INK),
                            ft.Text(
                                f"{info.get('grade_section', '')} · {info.get('wing', '')} · {info.get('floor', '')}",
                                size=11, color=MUTED,
                            ),
                        ],
                    ),
                    ft.Container(
                        padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                        bgcolor="#E8F5F0",
                        border_radius=20,
                        content=ft.Row(
                            tight=True, spacing=6,
                            controls=[
                                ft.Container(
                                    width=6, height=6, border_radius=3,
                                    bgcolor=SUCCESS_GREEN,
                                ),
                                ft.Text("Device Connected", size=10, color=SUCCESS_GREEN,
                                        weight=ft.FontWeight.W_600),
                            ],
                        ),
                    ),
                ],
            ),
            # Warning strip
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=14, vertical=10),
                bgcolor="#FBE9EC",
                border=ft.Border.all(1, "#F4D9DE"),
                border_radius=8,
                content=ft.Row(
                    tight=True, spacing=8,
                    controls=[
                        ft.Icon(ft.Icons.SHIELD_OUTLINED, size=14, color=PRIMARY_RED),
                        ft.Text("EMERGENCY STATUS", size=10, color=PRIMARY_RED,
                                weight=ft.FontWeight.BOLD),
                        ft.Text("No active emergency. The RFID reader is connected and ready.",
                                size=10, color=INK),
                    ],
                ),
            ),
            # Row 1: RFID Device + Classroom Info
            ft.Row(
                spacing=16,
                controls=[
                    _card(
                        "RFID Device",
                        ft.Column(
                            spacing=12,
                            controls=[
                                ft.Container(
                                    height=180,
                                    alignment=ft.Alignment.CENTER,
                                    bgcolor=ADMIN_CONTENT_BG,
                                    border_radius=10,
                                    content=ft.Column(
                                        tight=True,
                                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                        spacing=6,
                                        controls=[
                                            ft.Icon(ft.Icons.CONTACTLESS, size=42, color=PRIMARY_RED),
                                            ft.Text("Reader Online", size=12,
                                                    weight=ft.FontWeight.W_600, color=INK),
                                            ft.Text("TAGAP-RD-101 · Active", size=9, color=MUTED),
                                        ],
                                    ),
                                ),
                                ft.Row(
                                    tight=True, spacing=8,
                                    controls=[
                                        ft.Icon(ft.Icons.SCHEDULE, size=12, color=MUTED),
                                        ft.Text(
                                            f"Last scan: {dashboard.get('last_scan_time', 'None')}",
                                            size=10, color=MUTED,
                                        ),
                                    ],
                                ),
                            ],
                        ),
                    ),
                    _card(
                        "Classroom Device Info",
                        ft.Column(
                            spacing=12,
                            controls=[
                                ft.Row(
                                    controls=[
                                        ft.Column(
                                            tight=True, spacing=2,
                                            controls=[
                                                ft.Text("101", size=32,
                                                        weight=ft.FontWeight.BOLD, color=INK),
                                                ft.Text("Room Number", size=9, color=MUTED),
                                            ],
                                        ),
                                        ft.Container(expand=True),
                                        ft.Container(
                                            padding=ft.Padding.all(10),
                                            bgcolor="#FBE9EC",
                                            border=ft.Border.all(2, PRIMARY_RED),
                                            border_radius=50,
                                            content=ft.Text("Online", size=11,
                                                            color=PRIMARY_RED,
                                                            weight=ft.FontWeight.BOLD),
                                        ),
                                    ],
                                ),
                                ft.Container(
                                    padding=ft.Padding.all(10),
                                    bgcolor=ADMIN_CONTENT_BG,
                                    border_radius=8,
                                    content=ft.Column(
                                        tight=True, spacing=8,
                                        controls=[
                                            ft.Row(
                                                controls=[
                                                    ft.Column(tight=True, spacing=0, controls=[
                                                        ft.Text("Active", size=10, weight=ft.FontWeight.W_600, color=INK),
                                                        ft.Text("Status", size=8, color=MUTED),
                                                    ]),
                                                    ft.Column(tight=True, spacing=0, controls=[
                                                        ft.Text(info.get("floor", "1st Floor"), size=10, weight=ft.FontWeight.W_600, color=INK),
                                                        ft.Text("Floor", size=8, color=MUTED),
                                                    ]),
                                                ],
                                            ),
                                            ft.Divider(height=1, color=BORDER_COLOR),
                                            ft.Text(f"Device ID: TAGAP-RD-{room_id:03d}", size=10, color=INK),
                                            ft.Text(f"RFID Tag: CARD-DANGER-{room_id:04d}", size=10, color=INK),
                                        ],
                                    ),
                                ),
                            ],
                        ),
                    ),
                ],
            ),
            # Row 2: Device Controls + Quick Actions
            ft.Row(
                spacing=16,
                controls=[
                    _card(
                        "Device Controls",
                        ft.Column(
                            spacing=8,
                            controls=[
                                ft.Row([
                                    ft.Text("Scan Test", size=11, weight=ft.FontWeight.W_600, color=INK),
                                    ft.Container(expand=True),
                                    ft.Text("Available", size=10, color=SUCCESS_GREEN),
                                ]),
                                ft.Row([
                                    ft.Text("Restart RFID", size=11, weight=ft.FontWeight.W_600, color=INK),
                                    ft.Container(expand=True),
                                    ft.Text("Available", size=10, color=SUCCESS_GREEN),
                                ]),
                                ft.Row([
                                    ft.Text("Disconnect", size=11, weight=ft.FontWeight.W_600, color=INK),
                                    ft.Container(expand=True),
                                    ft.Text("Available", size=10, color=SUCCESS_GREEN),
                                ]),
                            ],
                        ),
                    ),
                    _card(
                        "Quick Actions",
                        ft.Column(
                            spacing=10,
                            controls=[
                                ft.Text(f"View Room Contacts ({len(parents)} parents)",
                                        size=11, color=INK),
                                ft.Text(f"View Alert History ({stats.get('total_rfid', 0)} alerts)",
                                        size=11, color=INK),
                                ft.Container(height=6),
                                ft.Button(
                                    "Open Settings",
                                    icon=ft.Icons.SETTINGS_OUTLINED,
                                    bgcolor=ADMIN_CONTENT_BG,
                                    color=INK,
                                    on_click=lambda _: on_navigate("Settings"),
                                ),
                            ],
                        ),
                    ),
                ],
            ),
        ],
    )

    from ui.screens.admin.shell import build_admin_shell
    return build_admin_shell(
        page,
        active_page="Room Device",
        room_name=info.get("room_name", "Room"),
        on_navigate=on_navigate,
        on_back_to_kiosk=on_exit,
        content=ft.Column(scroll=ft.ScrollMode.AUTO, controls=[content]),
    )