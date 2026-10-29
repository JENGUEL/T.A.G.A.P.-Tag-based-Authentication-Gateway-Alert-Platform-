"""
T.A.G.A.P. - Standby Screen (Kiosk)
Based on user's Flet Studio design with live clock and status.
"""
import asyncio
import flet as ft
from datetime import datetime
from typing import Callable
from config import settings
from ui.theme import *

# --- Helper Functions ---
def status_dot(color: str, size: int = 7) -> ft.Container:
    return ft.Container(
        width=size, height=size, bgcolor=color,
        border_radius=ft.BorderRadius.all(size / 2),
    )

def scanner_badge(diameter: float) -> tuple[ft.Stack, list[ft.Container], ft.Container]:
    ripple_size = diameter * 0.84
    ripples = [
        ft.Container(
            width=ripple_size, height=ripple_size, opacity=0.42, scale=0.72,
            border=ft.Border.all(2, ft.Colors.with_opacity(0.65, PRIMARY_RED_LIGHT)),
            border_radius=ft.BorderRadius.all(ripple_size / 2),
            animate_scale=ft.Animation(duration=1400, curve=ft.AnimationCurve.EASE_OUT),
            animate_opacity=ft.Animation(duration=1400, curve=ft.AnimationCurve.EASE_OUT),
        ) for _ in range(2)
    ]
    scanner_core = ft.Container(
        width=diameter * 0.74, height=diameter * 0.74,
        alignment=ft.Alignment.CENTER,
        border_radius=ft.BorderRadius.all(diameter * 0.37),
        gradient=ft.LinearGradient(
            begin=ft.Alignment.TOP_LEFT, end=ft.Alignment.BOTTOM_RIGHT,
            colors=[PRIMARY_RED_LIGHT, PRIMARY_RED],
        ),
        animate_scale=ft.Animation(duration=1100, curve=ft.AnimationCurve.EASE_IN_OUT),
        content=ft.Column(
            tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.CENTER, spacing=5,
            controls=[
                ft.Icon(ft.Icons.CONTACTLESS, size=32, color=ft.Colors.WHITE),
                ft.Text("Ready to scan", size=16, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
                ft.Text("RFID · ALWAYS ON", size=8, color="#FFE9ED"),
            ],
        ),
    )
    badge = ft.Stack(
        width=diameter, height=diameter, alignment=ft.Alignment.CENTER,
        controls=[
            ft.Container(width=diameter, height=diameter, bgcolor="#F9ECEF", border_radius=ft.BorderRadius.all(diameter / 2)),
            ripples[0], ripples[1],
            ft.Container(width=diameter * 0.88, height=diameter * 0.88, border=ft.Border.all(2, "#EBCAD0"), border_radius=ft.BorderRadius.all(diameter * 0.44)),
            scanner_core,
        ],
    )
    return badge, ripples, scanner_core

async def pulse_ripple(ripple: ft.Container, delay: float):
    await asyncio.sleep(delay)
    while True:
        ripple.scale = 1.0; ripple.opacity = 0.0; ripple.update()
        await asyncio.sleep(1.4)
        ripple.scale = 0.72; ripple.opacity = 0.42; ripple.update()
        await asyncio.sleep(1.4)

async def breathe_scanner(scanner_core: ft.Container):
    while True:
        scanner_core.scale = 1.035; scanner_core.update()
        await asyncio.sleep(1.1)
        scanner_core.scale = 1.0; scanner_core.update()
        await asyncio.sleep(1.1)

def clock_text() -> ft.Text:
    return ft.Text("00:00:00", size=11, weight=ft.FontWeight.BOLD, color=INK)

def gsm_bars() -> ft.Row:
    return ft.Row(
        tight=True,
        spacing=2,
        vertical_alignment=ft.CrossAxisAlignment.END,  # <-- Aligns to bottom baseline
        controls=[
            ft.Container(width=3, height=4, bgcolor=SUCCESS_GREEN, border_radius=1),
            ft.Container(width=3, height=7, bgcolor=SUCCESS_GREEN, border_radius=1),
            ft.Container(width=3, height=10, bgcolor=SUCCESS_GREEN, border_radius=1),
            ft.Container(width=3, height=13, bgcolor=SUCCESS_GREEN, border_radius=1),
        ],
    )

def header(compact: bool) -> tuple[ft.Control, ft.Text]:
    clock = clock_text()

    return ft.Container(
        height=62, padding=ft.Padding.symmetric(horizontal=18 if compact else 30), bgcolor=CARD_WHITE,
        border=ft.Border.only(bottom=ft.BorderSide(1, BORDER_COLOR)),
        content=ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Row(tight=True, spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER, controls=[
                    ft.Container(width=24, height=24, alignment=ft.Alignment.CENTER, bgcolor=PRIMARY_RED, border_radius=6,
                        content=ft.Icon(ft.Icons.VERIFIED_USER, size=15, color=ft.Colors.WHITE)),
                    ft.Text("T.A.G.A.P.", size=14, weight=ft.FontWeight.BOLD, color=INK),
                ]),
                ft.Row(tight=True, spacing=16, vertical_alignment=ft.CrossAxisAlignment.CENTER, controls=[
                    clock,
                    ft.Row(tight=True, spacing=6, controls=[
                        gsm_bars(),
                        ft.Text("GSM", size=10, color=MUTED),
                    ]),
                    ft.Row(tight=True, spacing=6, controls=[
                        status_dot(SUCCESS_GREEN, 6),
                        ft.Text("RFID OK", size=10, color=SUCCESS_GREEN),
                    ]),
                ]),
            ],
        ),
    ), clock

# --- Main Screen Builder ---
def build_standby_screen(page: ft.Page, on_card_scanned: Callable[[str], None]) -> tuple[ft.View, ft.Text]:
    compact = (page.width or 837) < 600
    available_height = page.height or 620
    diameter = min(336, max(208, available_height * 0.46))
    if compact: diameter = min(diameter, (page.width or 360) - 48)

    scanner, ripples, scanner_core = scanner_badge(diameter)
    header_ctrl, clock_ctrl = header(compact)

    # Debug Panel
    debug_panel = ft.Container()
    if settings.is_development:
        debug_panel = ft.Container(
            padding=10, bgcolor="#F0F0F0", border_radius=8,
            content=ft.Column([
                ft.Text("Developer Mock Controls", size=10, color=MUTED),
                ft.Row(spacing=10, controls=[
                    ft.Button("Tap SAFE", on_click=lambda _: on_card_scanned("CARD-SAFE-0001"), bgcolor=COLOR_SAFE, color="white"),
                    ft.Button("Tap ASSIST", on_click=lambda _: on_card_scanned("CARD-ASSIST-0001"), bgcolor=COLOR_ASSIST, color="white"),
                    ft.Button("Tap DANGER", on_click=lambda _: on_card_scanned("CARD-DANGER-0001"), bgcolor=COLOR_DANGER, color="white"),
                    ft.Button("Tap ADMIN", on_click=lambda _: on_card_scanned("CARD-ADMIN-0001"), bgcolor=COLOR_ADMIN, color="white"),
                ])
            ])
        )

    view = ft.View(
        route="/standby", padding=0, bgcolor=BG_OFF_WHITE,
        controls=[
            ft.Column(expand=True, spacing=0, controls=[
                header_ctrl,
                ft.Column(expand=True, alignment=ft.MainAxisAlignment.SPACE_EVENLY, horizontal_alignment=ft.CrossAxisAlignment.CENTER, controls=[
                    ft.Column(tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=3, controls=[
                        ft.Text("EMERGENCY RFID DRILL STATION", size=11, color=MUTED, weight=ft.FontWeight.BOLD),
                        ft.Text("North wing · Emergency Checkpoint A", size=10, color=MUTED),
                    ]),
                    scanner,
                    ft.Column(tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=5, controls=[
                        ft.Text("Present an emergency card to the RFID reader.", size=15, color=INK, weight=ft.FontWeight.BOLD),
                        ft.Text("Use Safe, Need assistance, or Danger. Wait for confirmation.", size=11, color=MUTED),
                    ]),
                    ft.Container(padding=ft.Padding.symmetric(horizontal=14, vertical=8), bgcolor=CARD_WHITE, border=ft.Border.all(1, BORDER_COLOR), border_radius=10,
                        content=ft.Row(tight=True, spacing=12, controls=[
                            ft.Column(tight=True, spacing=2, controls=[
                                ft.Text("GSM module · SIM connected", size=10, color=INK),
                                ft.Text("Network registered · Signal strong", size=9, color=MUTED),
                            ]),
                            ft.Container(padding=ft.Padding.symmetric(horizontal=10, vertical=6), bgcolor="#E8F5F0", border_radius=8,
                                content=ft.Text("Working", size=9, color=SUCCESS_GREEN, weight=ft.FontWeight.BOLD)),
                        ])),
                    debug_panel
                ]),
                ft.Container(padding=ft.Padding.symmetric(horizontal=18, vertical=9), bgcolor=CARD_WHITE, border=ft.Border.only(top=ft.BorderSide(1, BORDER_COLOR)),
                    content=ft.Row(alignment=ft.MainAxisAlignment.SPACE_BETWEEN, controls=[
                        ft.Text("Practice only · Drill records are simulated", size=9, color=MUTED),
                        ft.Text("Lockdown drill · Oct 29, 2026", size=9, color=MUTED),
                    ])),
            ])
        ]
    )

    # Start animations in background
    page.run_task(pulse_ripple, ripples[0], 0.0)
    page.run_task(pulse_ripple, ripples[1], 0.7)
    page.run_task(breathe_scanner, scanner_core)

    return view, clock_ctrl