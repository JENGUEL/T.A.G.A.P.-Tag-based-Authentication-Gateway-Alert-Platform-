"""
T.A.G.A.P. - Admin > Alert History (Images 3 & 4)
"""
import flet as ft
from typing import Callable
from ui.theme import *
from data import queries


def _history_row(title: str, date: str, status: str, badge_color: str) -> ft.Control:
    return ft.Container(
        padding=ft.Padding.all(10),
        bgcolor=ADMIN_CONTENT_BG,
        border_radius=8,
        content=ft.Row(
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Column(
                    tight=True, spacing=2, expand=True,
                    controls=[
                        ft.Text(title, size=11, weight=ft.FontWeight.W_600, color=INK),
                        ft.Text(date, size=9, color=MUTED),
                    ],
                ),
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                    bgcolor=ft.Colors.with_opacity(0.15, badge_color),
                    border_radius=4,
                    content=ft.Text(status, size=9, color=badge_color,
                                    weight=ft.FontWeight.W_600),
                ),
            ],
        ),
    )


def build_alert_history(page: ft.Page, room_id: int, on_navigate: Callable, on_exit: Callable):
    info = queries.get_room_info(room_id)
    stats = queries.get_alert_history_stats()
    sms_history = queries.get_sms_history(limit=5)
    rfid_history = queries.get_rfid_history(limit=5)

    # SMS History list
    sms_card = ft.Container(
        expand=True,
        padding=ft.Padding.all(20),
        bgcolor=CARD_WHITE,
        border=ft.Border.all(1, BORDER_COLOR),
        border_radius=12,
        content=ft.Column(
            spacing=10,
            controls=[
                ft.Text("SMS History", size=14, weight=ft.FontWeight.W_600, color=INK),
                ft.Row(
                    spacing=0,
                    controls=[
                        ft.Column(
                            tight=True, spacing=2, expand=True,
                            controls=[
                                ft.Text(str(stats["total_sms"]), size=28,
                                        weight=ft.FontWeight.BOLD, color=INK),
                                ft.Text("Successful sends", size=10, color=MUTED),
                            ],
                        ),
                        ft.Column(
                            tight=True, spacing=2,
                            horizontal_alignment=ft.CrossAxisAlignment.END,
                            controls=[
                                ft.Text(f"{stats['delivery_rate']}%", size=28,
                                        weight=ft.FontWeight.BOLD, color=INK),
                                ft.Text("Delivery rate", size=10, color=MUTED),
                            ],
                        ),
                    ],
                ),
                ft.Divider(height=1, color=BORDER_COLOR),
                *[
                    _history_row(
                        m["message"], f"{m['date']} · {m['time']}",
                        m["status"],
                        SUCCESS_GREEN if m["status"] == "Delivered" else PRIMARY_RED,
                    )
                    for m in sms_history
                ],
            ],
        ),
    )

    # RFID History list
    rfid_card = ft.Container(
        expand=True,
        padding=ft.Padding.all(20),
        bgcolor=CARD_WHITE,
        border=ft.Border.all(1, BORDER_COLOR),
        border_radius=12,
        content=ft.Column(
            spacing=10,
            controls=[
                ft.Text("RFID History", size=14, weight=ft.FontWeight.W_600, color=INK),
                ft.Row(
                    spacing=0,
                    controls=[
                        ft.Column(
                            tight=True, spacing=2, expand=True,
                            controls=[
                                ft.Text(str(stats["total_rfid"]), size=28,
                                        weight=ft.FontWeight.BOLD, color=INK),
                                ft.Text("Scanned events", size=10, color=MUTED),
                            ],
                        ),
                        ft.Column(
                            tight=True, spacing=2,
                            horizontal_alignment=ft.CrossAxisAlignment.END,
                            controls=[
                                ft.Text("3", size=28, weight=ft.FontWeight.BOLD, color=INK),
                                ft.Text("Distinct meanings", size=10, color=MUTED),
                            ],
                        ),
                    ],
                ),
                ft.Divider(height=1, color=BORDER_COLOR),
                *[
                    _history_row(
                        f"{r['tag_id']} · {r['meaning']}",
                        f"{r['date']} · {r['time']}",
                        r["meaning"],
                        get_card_color(r["meaning"].upper()),
                    )
                    for r in rfid_history
                ],
            ],
        ),
    )

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
                            ft.Text("Alert History", size=24,
                                    weight=ft.FontWeight.BOLD, color=INK),
                            ft.Text(
                                f"{info.get('room_name', '')} · {info.get('grade_section', '')} · {info.get('wing', '')}",
                                size=11, color=MUTED,
                            ),
                        ],
                    ),
                    ft.Container(
                        padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                        bgcolor="#E8F5F0", border_radius=20,
                        content=ft.Text("Device Connected", size=10,
                                        color=SUCCESS_GREEN, weight=ft.FontWeight.W_600),
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
                        ft.Text("ALERT HISTORY", size=10, color=PRIMARY_RED,
                                weight=ft.FontWeight.BOLD),
                        ft.Text("Review recent SMS and RFID events.", size=10, color=INK),
                    ],
                ),
            ),
            # History cards
            ft.Row(spacing=16, controls=[sms_card, rfid_card]),
        ],
    )

    from ui.screens.admin.shell import build_admin_shell
    return build_admin_shell(
        page,
        active_page="Alert History",
        room_name=info.get("room_name", "Room"),
        on_navigate=on_navigate,
        on_back_to_kiosk=on_exit,
        content=ft.Column(scroll=ft.ScrollMode.AUTO, controls=[content]),
    )