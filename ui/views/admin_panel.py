"""
T.A.G.A.P. - Admin Dashboard View
Based on the Flet Studio reference design, wired to the real backend.
"""
import asyncio
import flet as ft
from typing import Callable

from ui.theme import *
from data import queries

PRIMARY = PRIMARY_RED
CANVAS = "#F7F5F4"
BORDER = "#EAE6E8"


# --- Sidebar Components ---
def _nav_item(label: str, icon: str, active: bool, on_click: Callable) -> ft.Container:
    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=12, vertical=10),
        border_radius=10,
        bgcolor="#F8EAEE" if active else ft.Colors.TRANSPARENT,
        on_click=lambda _: on_click(label),
        content=ft.Row(
            tight=True, spacing=12,
            controls=[
                ft.Icon(icon, size=20, color=PRIMARY if active else "#6D6970"),
                ft.Text(label, size=13, color=PRIMARY if active else "#6D6970",
                        weight=ft.FontWeight.W_600 if active else ft.FontWeight.NORMAL),
            ],
        ),
    )


def _build_sidebar(active_section: str, on_navigate: Callable) -> ft.Container:
    menu = [
        ("Room Device", ft.Icons.DEVICES),
        ("Main Kiosk", ft.Icons.GROUPS),
        ("Emergency Report", ft.Icons.SHIELD),
        ("Alert History", ft.Icons.HISTORY),
        ("Settings", ft.Icons.SETTINGS),
    ]
    return ft.Container(
        width=216, bgcolor="#FFFFFF",
        border=ft.Border.only(right=ft.BorderSide(1, BORDER)),
        padding=ft.Padding.symmetric(horizontal=16, vertical=20),
        content=ft.Column(
            expand=True, spacing=8,
            controls=[
                ft.Row(tight=True, spacing=10, controls=[
                    ft.Container(width=42, height=42, alignment=ft.Alignment.CENTER, bgcolor=PRIMARY, border_radius=12,
                                 content=ft.Icon(ft.Icons.VERIFIED_USER, size=25, color=ft.Colors.WHITE)),
                    ft.Text("T.A.G.A.P.", size=21, weight=ft.FontWeight.BOLD, color=INK),
                ]),
                ft.Container(height=10),
                ft.Container(
                    padding=ft.Padding.all(12),
                    border=ft.Border.all(1, "#E8E4E6"),
                    border_radius=12,
                    content=ft.Row(tight=True, spacing=10, controls=[
                        ft.Icon(ft.Icons.SCHOOL, size=22, color=PRIMARY),
                        ft.Column(tight=True, spacing=2, controls=[
                            ft.Text("Room 101", size=13, color=INK, weight=ft.FontWeight.BOLD),
                            ft.Text("Grade 7 – Section A", size=10, color=MUTED),
                        ]),
                    ]),
                ),
                ft.Container(height=10),
                ft.Text("MAIN MENU", size=9, color=MUTED, weight=ft.FontWeight.BOLD),
                *[_nav_item(label, icon, active_section == label, on_navigate) for label, icon in menu],
                ft.Container(expand=True),
                ft.Column(tight=True, spacing=4, controls=[
                    ft.Row(tight=True, spacing=8, controls=[
                        ft.Icon(ft.Icons.FAVORITE_BORDER, size=20, color=PRIMARY),
                        ft.Text("System Online", size=12, color=INK, weight=ft.FontWeight.BOLD),
                    ]),
                    ft.Text("All devices connected.\nT.A.G.A.P. v1.0", size=10, color=MUTED),
                ]),
            ],
        ),
    )


# --- Dashboard Components ---
def _card(title: str, content: ft.Control, expand: bool = True) -> ft.Container:
    return ft.Container(
        expand=expand,
        padding=18,
        bgcolor="#FFFFFF",
        border=ft.Border.all(1, BORDER),
        border_radius=18,
        content=ft.Column(
            tight=True, spacing=12,
            controls=[
                ft.Text(title, size=17, color=INK, weight=ft.FontWeight.BOLD),
                content,
            ],
        ),
    )


def _build_room_device_dashboard(room_id: int) -> ft.Control:
    # Pull REAL data from our database
    info = queries.get_room_info(room_id)
    stats = queries.get_alert_history_stats()
    queue = queries.get_queue_stats()

    # Left Column (RFID Device)
    reader_card = _card(
        "RFID Device",
        ft.Column(spacing=12, controls=[
            ft.Container(
                height=200, alignment=ft.Alignment.CENTER, bgcolor=CANVAS, border_radius=12,
                content=ft.Column(tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=6, controls=[
                    ft.Icon(ft.Icons.SENSORS, size=42, color=PRIMARY),
                    ft.Text("Reader Online", size=14, weight=ft.FontWeight.BOLD, color=INK),
                    ft.Text(f"TAGAP-RD-{room_id:03d} · Active", size=10, color=MUTED),
                ]),
            ),
            ft.Text("Last scan: No recent scans", size=12, color=INK),
        ])
    )

    # Right Column (Device Info)
    info_card = _card(
        "Classroom Device Info",
        ft.Column(spacing=16, controls=[
            ft.Row(alignment=ft.MainAxisAlignment.SPACE_BETWEEN, controls=[
                ft.Column(tight=True, spacing=2, controls=[
                    ft.Text(str(room_id), size=46, color=INK, weight=ft.FontWeight.BOLD),
                    ft.Text("Room Number", size=11, color=MUTED),
                ]),
                ft.Container(width=86, height=86, alignment=ft.Alignment.CENTER, border=ft.Border.all(4, PRIMARY),
                             border_radius=43,
                             content=ft.Text("Online", size=14, color=PRIMARY, weight=ft.FontWeight.BOLD)),
            ]),
            ft.Container(
                padding=ft.Padding.all(12), bgcolor=CANVAS, border_radius=12,
                content=ft.Row(alignment=ft.MainAxisAlignment.SPACE_BETWEEN, controls=[
                    ft.Column(tight=True, spacing=3, controls=[
                        ft.Text("Active", size=16, color=INK, weight=ft.FontWeight.BOLD),
                        ft.Text("Status", size=10, color=MUTED),
                    ]),
                    ft.Column(tight=True, spacing=3, horizontal_alignment=ft.CrossAxisAlignment.END, controls=[
                        ft.Text(info.get("floor", "1st Floor"), size=16, color=INK, weight=ft.FontWeight.BOLD),
                        ft.Text(info.get("wing", "Building A"), size=10, color=MUTED),
                    ]),
                ]),
            ),
        ])
    )

    return ft.Column(
        spacing=16,
        controls=[
            # Header
            ft.Row(alignment=ft.MainAxisAlignment.SPACE_BETWEEN, controls=[
                ft.Column(tight=True, spacing=3, controls=[
                    ft.Text(info.get("room_name", "Room"), size=25, color=INK, weight=ft.FontWeight.BOLD),
                    ft.Text(f"{info.get('grade_section', '')} · {info.get('wing', '')} · {info.get('floor', '')}",
                            size=11, color=MUTED),
                ]),
                ft.Container(padding=ft.Padding.symmetric(horizontal=12, vertical=8), bgcolor="#F8EAEE",
                             border_radius=20,
                             content=ft.Row(tight=True, spacing=6, controls=[
                                 ft.Icon(ft.Icons.VERIFIED_USER, size=14, color=PRIMARY),
                                 ft.Text("Device Connected", size=11, color=PRIMARY, weight=ft.FontWeight.BOLD),
                             ])),
            ]),
            # Warning Strip
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=14, vertical=12), bgcolor="#F8EAEE", border_radius=12,
                content=ft.Row(tight=True, spacing=10, controls=[
                    ft.Icon(ft.Icons.SHIELD, size=20, color=PRIMARY),
                    ft.Text("EMERGENCY STATUS", size=11, color=PRIMARY, weight=ft.FontWeight.BOLD),
                    ft.Text("No active emergency. The RFID reader is connected.", size=11, color=PRIMARY),
                ]),
            ),
            # Main Grid
            ft.Row(spacing=16, controls=[reader_card, info_card]),
        ]
    )


# --- Main Admin View Builder ---
def build_admin_view(page: ft.Page, on_exit_to_kiosk: Callable) -> ft.Control:
    state = {"current": "Room Device"}
    body_host = ft.Container(expand=True, bgcolor=CANVAS, padding=ft.Padding.all(24))

    def set_active(section):
        state["current"] = section
        if section == "Room Device":
            body_host.content = _build_room_device_dashboard(1)
        else:
            body_host.content = ft.Column(
                expand=True, alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(ft.Icons.CONSTRUCTION, size=48, color=PRIMARY),
                    ft.Text(f"{section} Screen", size=24, weight=ft.FontWeight.BOLD, color=INK),
                    ft.Text("This section is under construction for Sprint 6.5.", size=14, color=MUTED),
                ]
            )
        page.update()

    async def navigate(section: str):
        if section == "Main Kiosk":
            on_exit_to_kiosk()
            return
        body_host.opacity = 0
        page.update()
        await asyncio.sleep(0.15)
        set_active(section)
        body_host.opacity = 1
        page.update()

    # Initial load
    set_active("Room Device")

    topbar = ft.Container(
        height=58, padding=ft.Padding.symmetric(horizontal=24), bgcolor="#FFFFFF",
        border=ft.Border.only(bottom=ft.BorderSide(1, BORDER)),
        content=ft.Row(alignment=ft.MainAxisAlignment.SPACE_BETWEEN, controls=[
            ft.Row(tight=True, spacing=10, controls=[
                ft.TextButton(content="Back to Rooms", icon=ft.Icons.ARROW_BACK,
                              on_click=lambda _: asyncio.create_task(navigate("Main Kiosk"))),
                ft.Icon(ft.Icons.CHEVRON_RIGHT, size=18, color=MUTED),
                ft.Text("Room 101", size=12, color=INK),
            ]),
        ]),
    )

    return ft.Row(
        expand=True,
        vertical_alignment=ft.CrossAxisAlignment.STRETCH,
        spacing=0,
        controls=[
            _build_sidebar("Room Device", lambda s: asyncio.create_task(navigate(s))),
            ft.Column(expand=True, spacing=0, controls=[topbar, body_host]),
        ],
    )