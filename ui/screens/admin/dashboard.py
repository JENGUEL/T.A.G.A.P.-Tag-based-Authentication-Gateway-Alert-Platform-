"""
T.A.G.A.P. - Admin Dashboard (SPA)
Adopted from the Flet Studio reference code.
"""
import asyncio
import logging
import flet as ft

from ui.components.admin_sidebar import build_admin_sidebar
from ui.components.room_device import build_room_device
from ui.components.scanner import breathe_scanner, pulse_ripple

log = logging.getLogger(__name__)
PRIMARY = "#AE3044"
INK = "#29262B"
MUTED = "#8B858B"
CANVAS = "#F7F5F4"


def _placeholder(section: str, navigate) -> ft.Control:
    descriptions = {
        "Emergency Report": "Review and manage emergency reports for your rooms.",
        "Alert History": "Browse recent reader alerts and drill activity.",
        "Settings": "Manage school, room, and device preferences.",
    }
    return ft.Container(
        expand=True, alignment=ft.Alignment.CENTER,
        content=ft.Column(tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=12, controls=[
            ft.Icon(ft.Icons.CONSTRUCTION, size=38, color=PRIMARY),
            ft.Text(section, size=24, color=INK, weight=ft.FontWeight.BOLD),
            ft.Text(descriptions.get(section, "This section is being prepared."), size=13, color=MUTED),
            ft.Button(content="Return to Room Device", on_click=lambda e: asyncio.create_task(navigate("Room Device"))),
        ]),
    )


def _section_skeleton(section: str, compact: bool) -> ft.Control:
    def block(height: int, width: int | None = None, expand: bool = False):
        return ft.Container(height=height, width=width, expand=expand or None, bgcolor="#EEE9EB", border_radius=8)

    summary_card = ft.Container(expand=True if not compact else None, padding=18, bgcolor="#FFFFFF",
                                border=ft.Border.all(1, "#ECE8EA"), border_radius=16,
                                content=ft.Column(spacing=14, controls=[block(18, 180), block(12, 250),
                                                                        block(120 if compact else 180),
                                                                        ft.Row(spacing=10, controls=[block(30, 110),
                                                                                                     block(30, 110)])]))
    side_card = ft.Container(expand=True if not compact else None, padding=18, bgcolor="#FFFFFF",
                             border=ft.Border.all(1, "#ECE8EA"), border_radius=16,
                             content=ft.Column(spacing=14,
                                               controls=[block(18, 150), block(64), block(14), block(14), block(14)]))

    cards = ft.Column(spacing=14, controls=[summary_card, side_card]) if compact else ft.Row(expand=True, spacing=14,
                                                                                             vertical_alignment=ft.CrossAxisAlignment.STRETCH,
                                                                                             controls=[summary_card,
                                                                                                       side_card])
    return ft.Column(expand=True, spacing=16, controls=[
        ft.Row(tight=True, spacing=10, controls=[ft.ProgressRing(value=None, color=PRIMARY, stroke_width=2),
                                                 ft.Text(f"Loading {section}…", size=13, color=MUTED)]),
        cards,
    ])


def show_admin_panel(page: ft.Page, on_exit_to_kiosk):
    page.title = "T.A.G.A.P. Admin · Room Device"
    page.padding = 0
    page.spacing = 0
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = CANVAS
    page.data = {"screen_tasks": []}

    compact = (page.width or 837) < 1100
    sidebar_compact = (page.width or 837) < 700

    def stop_screen_tasks():
        for task in page.data.get("screen_tasks", []):
            task.cancel()
        page.data = {"screen_tasks": []}

    def start_scanner_animations(ripples, scanner_core):
        page.data["screen_tasks"] = [
            asyncio.create_task(pulse_ripple(ripples[0], 0.0)),
            asyncio.create_task(pulse_ripple(ripples[1], 0.7)),
            asyncio.create_task(breathe_scanner(scanner_core)),
        ]

    def open_room_picker():
        page.show_dialog(ft.AlertDialog(modal=True, title=ft.Text("Rooms"),
                                        content=ft.ListTile(title=ft.Text("Room 101"), on_click=page.pop_dialog),
                                        actions=[ft.TextButton(content="Close", on_click=page.pop_dialog)]))

    current_section = "Room Device"
    transitioning = False

    async def navigate(section: str):
        nonlocal current_section, transitioning
        if section == "Device Settings": section = "Settings"
        if section == "Main Kiosk":
            if not transitioning:
                transitioning = True
                await on_exit_to_kiosk()
            return
        if transitioning or section == current_section: return

        transitioning = True
        try:
            body_host.opacity = 0
            page.update()
            await asyncio.sleep(0.16)
            stop_screen_tasks()

            body_host.content = _section_skeleton(section, compact)
            body_host.opacity = 1
            set_sidebar_active(section)
            page.update()
            await asyncio.sleep(0.28)

            body_host.opacity = 0
            page.update()
            await asyncio.sleep(0.12)

            if section == "Room Device":
                view, ripples, scanner_core = build_room_device(page, compact, None, None)
            else:
                view = _placeholder(section, navigate)
                ripples, scanner_core = None, None

            body_host.content = view
            body_host.opacity = 1
            current_section = section
            page.update()
            if ripples: start_scanner_animations(ripples, scanner_core)
        finally:
            transitioning = False

    # Initial build
    initial_view, ripples, scanner_core = build_room_device(page, compact, None, None)
    sidebar_view, set_sidebar_active = build_admin_sidebar("Room Device", navigate, open_room_picker, sidebar_compact)

    sidebar_slot = ft.Container(width=72 if sidebar_compact else 216, content=sidebar_view)
    body_host = ft.Container(expand=True, opacity=1,
                             animate_opacity=ft.Animation(duration=220, curve=ft.AnimationCurve.EASE_IN_OUT),
                             bgcolor=CANVAS, padding=ft.Padding.all(16 if compact else 24), content=initial_view)

    topbar = ft.Container(height=58, padding=ft.Padding.symmetric(horizontal=18 if compact else 28), bgcolor="#FFFFFF",
                          border=ft.Border.only(bottom=ft.BorderSide(1, "#ECE8EA")),
                          content=ft.Row(alignment=ft.MainAxisAlignment.SPACE_BETWEEN, controls=[
                              ft.Row(tight=True, spacing=10, controls=[
                                  ft.TextButton(content="Back to Rooms", icon=ft.Icons.ARROW_BACK,
                                                on_click=open_room_picker),
                                  ft.Icon(ft.Icons.CHEVRON_RIGHT, size=18, color=MUTED),
                                  ft.Text("Room 101", size=12, color=INK)]),
                          ]))

    admin_root = ft.SafeArea(expand=True,
                             content=ft.Row(expand=True, vertical_alignment=ft.CrossAxisAlignment.STRETCH, spacing=0,
                                            controls=[
                                                sidebar_slot,
                                                ft.Column(expand=True, spacing=0, controls=[topbar, body_host])
                                            ]))

    page.add(admin_root)
    start_scanner_animations(ripples, scanner_core)