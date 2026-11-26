"""
T.A.G.A.P. - Admin Shell (Sidebar + Content)
"""
import flet as ft
from typing import Callable, Optional
from ui.theme import *


def _nav_item(
    icon: str,
    label: str,
    is_active: bool,
    on_click: Callable,
) -> ft.Container:
    return ft.Container(
        height=42,
        padding=ft.Padding.symmetric(horizontal=12),
        border_radius=8,
        bgcolor=ADMIN_NAV_ACTIVE_BG if is_active else "transparent",
        data=label,
        on_click=lambda _: on_click(label),
        ink=True,
        content=ft.Row(
            tight=True,
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Icon(
                    icon, size=16,
                    color=ADMIN_NAV_ACTIVE_TEXT if is_active else MUTED,
                ),
                ft.Text(
                    label, size=12,
                    color=ADMIN_NAV_ACTIVE_TEXT if is_active else INK,
                    weight=ft.FontWeight.W_600 if is_active else ft.FontWeight.W_400,
                ),
            ],
        ),
    )


def set_active_admin_navigation(view: ft.View, section: str) -> None:
    sidebar = view.controls[0].controls[0]
    for item in sidebar.content.controls:
        if not isinstance(item, ft.Container) or not item.data:
            continue
        active = item.data == section
        item.bgcolor = ADMIN_NAV_ACTIVE_BG if active else "transparent"
        icon, text = item.content.controls
        icon.color = ADMIN_NAV_ACTIVE_TEXT if active else MUTED
        text.color = ADMIN_NAV_ACTIVE_TEXT if active else INK
        text.weight = ft.FontWeight.W_600 if active else ft.FontWeight.W_400


def build_admin_shell(
    page: ft.Page,
    *,
    active_page: str,
    room_name: str,
    on_navigate: Callable[[str], None],
    on_back_to_kiosk: Callable[[], None],
    content: ft.Control,
) -> ft.View:
    """Wraps any admin content in the sidebar + top bar layout."""

    nav_items: dict[str, ft.Container] = {}

    def navigate(section: str):
        for label, item in nav_items.items():
            active = label == section
            item.bgcolor = ADMIN_NAV_ACTIVE_BG if active else "transparent"
            icon, text = item.content.controls
            icon.color = ADMIN_NAV_ACTIVE_TEXT if active else MUTED
            text.color = ADMIN_NAV_ACTIVE_TEXT if active else INK
            text.weight = ft.FontWeight.W_600 if active else ft.FontWeight.W_400
        page.update()
        on_navigate(section)

    nav_definitions = (
        (ft.Icons.HOME_OUTLINED, "Room Device"),
        (ft.Icons.DASHBOARD_OUTLINED, "Main Kiosk"),
        (ft.Icons.WARNING_AMBER_ROUNDED, "Emergency Report"),
        (ft.Icons.HISTORY, "Alert History"),
        (ft.Icons.CABLE, "Reader Monitor"),
        (ft.Icons.SETTINGS_OUTLINED, "Settings"),
    )
    for icon, label in nav_definitions:
        nav_items[label] = _nav_item(
            icon,
            label,
            active_page == label,
            navigate,
        )

    sidebar = ft.Container(
        width=220,
        bgcolor=ADMIN_SIDEBAR_BG,
        border=ft.Border.only(right=ft.BorderSide(1, BORDER_COLOR)),
        padding=ft.Padding.symmetric(horizontal=16, vertical=20),
        content=ft.Column(
            spacing=6,
            controls=[
                # Logo
                ft.Row(
                    tight=True, spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Container(
                            width=28, height=28,
                            alignment=ft.Alignment.CENTER,
                            bgcolor=PRIMARY_RED, border_radius=8,
                            content=ft.Icon(
                                ft.Icons.VERIFIED_USER, size=16, color="white"
                            ),
                        ),
                        ft.Text(
                            "T.A.G.A.P.", size=14, weight=ft.FontWeight.BOLD, color=INK
                        ),
                    ],
                ),
                ft.Container(height=14),
                # Room badge
                ft.Container(
                    padding=ft.Padding.all(10),
                    bgcolor=ADMIN_CONTENT_BG,
                    border_radius=8,
                    content=ft.Column(
                        tight=True, spacing=2,
                        controls=[
                            ft.Text("Room", size=9, color=MUTED),
                            ft.Text(room_name, size=12, weight=ft.FontWeight.W_600, color=INK),
                        ],
                    ),
                ),
                ft.Container(height=14),
                # Nav items
                *nav_items.values(),
                ft.Container(expand=True),
                # Bottom system status
                ft.Container(
                    padding=ft.Padding.all(10),
                    content=ft.Column(
                        tight=True, spacing=4,
                        controls=[
                            ft.Row(
                                tight=True, spacing=6,
                                controls=[
                                    ft.Icon(ft.Icons.FAVORITE, size=12, color=PRIMARY_RED),
                                    ft.Text("System Online", size=10, weight=ft.FontWeight.W_600, color=INK),
                                ],
                            ),
                            ft.Text("All devices connected.", size=9, color=MUTED),
                            ft.Text("T.A.G.A.P. v1.0", size=9, color=MUTED),
                        ],
                    ),
                ),
            ],
        ),
    )

    top_bar = ft.Container(
        height=56,
        padding=ft.Padding.symmetric(horizontal=24),
        bgcolor=ADMIN_SIDEBAR_BG,
        border=ft.Border.only(bottom=ft.BorderSide(1, BORDER_COLOR)),
        content=ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Row(
                    tight=True, spacing=8,
                    controls=[
                        ft.Text("Back to Kiosk", size=11, color=MUTED),
                        ft.Icon(ft.Icons.CHEVRON_RIGHT, size=14, color=MUTED),
                        ft.Text(room_name, size=11, color=INK, weight=ft.FontWeight.W_600),
                    ],
                ),
                ft.Row(
                    tight=True, spacing=10,
                    controls=[
                        ft.TextButton(
                            "Exit to Standby",
                            icon=ft.Icons.LOGOUT,
                            on_click=lambda _: on_back_to_kiosk(),
                        ),
                    ],
                ),
            ],
        ),
    )

    return ft.View(
        route=f"/admin/{active_page.lower().replace(' ', '_')}",
        padding=0,
        bgcolor=ADMIN_CONTENT_BG,
        controls=[
            ft.Row(
                expand=True, spacing=0,
                controls=[
                    sidebar,
                    ft.Column(
                        expand=True, spacing=0,
                        controls=[
                            top_bar,
                            ft.Container(
                                expand=True,
                                padding=ft.Padding.all(24),
                                content=content,
                            ),
                        ],
                    ),
                ],
            )
        ],
    )