"""
T.A.G.A.P. - Standby Screen (Kiosk)
"""
import asyncio
import flet as ft
from typing import Callable, Optional

from config import settings
from ui.theme import *


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
            colors=["#E66C7D", PRIMARY_RED, "#8F2637"],
        ),
        shadow=ft.BoxShadow(blur_radius=34, spread_radius=2, color="#40BA384B"),
        animate_scale=ft.Animation(duration=1100, curve=ft.AnimationCurve.EASE_IN_OUT),
        content=ft.Column(
            tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER, spacing=7,
            controls=[
                ft.Icon(ft.Icons.CONTACTLESS, size=43, color=ft.Colors.WHITE),
                ft.Text("Ready to scan", size=19, color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
                ft.Text("RFID  ·  ALWAYS ON", size=9, color="#FFF1F3", weight=ft.FontWeight.BOLD),
            ],
        ),
    )
    badge = ft.Stack(
        width=diameter, height=diameter, alignment=ft.Alignment.CENTER,
        controls=[
            ft.Container(width=diameter, height=diameter, bgcolor="#F8EDF0",
                         border_radius=ft.BorderRadius.all(diameter / 2)),
            ripples[0], ripples[1],
            ft.Container(width=diameter * 0.88, height=diameter * 0.88,
                         border=ft.Border.all(2, "#E6BDC5"),
                         border_radius=ft.BorderRadius.all(diameter * 0.44)),
            scanner_core,
        ],
    )
    return badge, ripples, scanner_core


async def pulse_ripple(ripple: ft.Container, delay: float):
    await asyncio.sleep(delay)
    while True:
        ripple.scale = 1.0
        ripple.opacity = 0.0
        try:
            ripple.update()
        except RuntimeError:
            return
        await asyncio.sleep(1.4)
        ripple.scale = 0.72
        ripple.opacity = 0.42
        try:
            ripple.update()
        except RuntimeError:
            return
        await asyncio.sleep(1.4)


async def breathe_scanner(scanner_core: ft.Container):
    while True:
        scanner_core.scale = 1.035
        try:
            scanner_core.update()
        except RuntimeError:
            return
        await asyncio.sleep(1.1)
        scanner_core.scale = 1.0
        try:
            scanner_core.update()
        except RuntimeError:
            return
        await asyncio.sleep(1.1)


def gsm_bars() -> ft.Row:
    return ft.Row(tight=True, spacing=2, vertical_alignment=ft.CrossAxisAlignment.END, controls=[
        ft.Container(width=3, height=4, bgcolor=SUCCESS_GREEN, border_radius=1),
        ft.Container(width=3, height=7, bgcolor=SUCCESS_GREEN, border_radius=1),
        ft.Container(width=3, height=10, bgcolor=SUCCESS_GREEN, border_radius=1),
        ft.Container(width=3, height=13, bgcolor=SUCCESS_GREEN, border_radius=1),
    ])


def build_standby_screen(
    page: ft.Page,
    on_card_scanned: Callable[[str], None],
    on_toggle_mocks: Optional[Callable[[bool], None]] = None,
    on_open_status: Optional[Callable[[], None]] = None,
    on_open_terminal: Optional[Callable[[], None]] = None,
    developer_mode: bool = False,
) -> tuple[ft.View, ft.Text, list[object]]:
    compact = (page.width or 837) < 600
    available_height = page.height or 620
    diameter = min(356, max(224, available_height * 0.48))
    if compact:
        diameter = min(diameter, (page.width or 360) - 48)

    scanner, ripples, scanner_core = scanner_badge(diameter)
    clock = ft.Text("00:00:00", size=12, weight=ft.FontWeight.BOLD, color=INK)

    async def animate_terminal_press(button: ft.Container):
        button.scale = 0.86
        try:
            button.update()
        except RuntimeError:
            return
        await asyncio.sleep(0.09)
        button.scale = 1.0
        try:
            button.update()
        except RuntimeError:
            return
        if on_open_terminal:
            on_open_terminal()

    def open_terminal(_):
        page.run_task(animate_terminal_press, terminal_button)

    terminal_button = ft.Container(
        width=44,
        height=44,
        alignment=ft.Alignment.CENTER,
        bgcolor="#EAF1FF",
        border=ft.Border.all(1, "#D6E3FA"),
        border_radius=14,
        shadow=ft.BoxShadow(blur_radius=12, color="#183976D8"),
        scale=1.0,
        animate_scale=ft.Animation(duration=130, curve=ft.AnimationCurve.EASE_OUT_BACK),
        ink=True,
        tooltip="Open command console",
        on_click=open_terminal,
        content=ft.Icon(
            ft.Icons.TERMINAL_ROUNDED,
            size=20,
            color="#3976D8",
        ),
    )

    header = ft.Container(
        height=76,
        padding=ft.Padding.symmetric(horizontal=18 if compact else 34),
        bgcolor=CARD_WHITE,
        border=ft.Border.only(bottom=ft.BorderSide(1, BORDER_COLOR)),
        content=ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Row(tight=True, spacing=11, controls=[
                    ft.Container(
                        width=46, height=46, alignment=ft.Alignment.CENTER,
                        bgcolor=PRIMARY_RED, border_radius=12,
                        shadow=ft.BoxShadow(blur_radius=14, color="#25BA384B"),
                        content=ft.Icon(ft.Icons.VERIFIED_USER, size=27, color=ft.Colors.WHITE),
                    ),
                    ft.Column(tight=True, spacing=1, controls=[
                        ft.Text("T.A.G.A.P.", size=24 if not compact else 19,
                                weight=ft.FontWeight.BOLD, color=INK),
                        ft.Text("St. Mary's Academy of Palo, Leyte, Inc.",
                                size=9 if compact else 11, color=MUTED,
                                weight=ft.FontWeight.W_600),
                    ]),
                ]),
                ft.Row(tight=True, spacing=12, controls=[
                    clock,
                    ft.TextButton(
                        content=ft.Row(tight=True, spacing=6, controls=[
                            status_dot(SUCCESS_GREEN, 7),
                            ft.Text("System status", size=11, color=INK),
                        ]),
                        on_click=lambda _: on_open_status() if on_open_status else None,
                    ),
                ]),
            ],
        ),
    )

    developer_panel = ft.Container()
    if developer_mode:
        developer_panel = ft.Container(
            padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            bgcolor="#F8F4F5",
            border=ft.Border.all(1, BORDER_COLOR),
            border_radius=12,
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                controls=[
                    ft.Row(tight=True, spacing=7, controls=[
                        ft.Icon(ft.Icons.DEVELOPER_MODE, size=16, color=PRIMARY_RED),
                        ft.Text("Developer mock controls", size=10, color=INK,
                                weight=ft.FontWeight.BOLD),
                    ]),
                    ft.Row(tight=True, spacing=6, controls=[
                        ft.Button("SAFE", on_click=lambda _: on_card_scanned("CARD-SAFE-0001"),
                                  bgcolor=COLOR_SAFE, color=ft.Colors.WHITE),
                        ft.Button("ASSIST", on_click=lambda _: on_card_scanned("CARD-ASSIST-0001"),
                                  bgcolor=COLOR_ASSIST, color=ft.Colors.WHITE),
                        ft.Button("DANGER", on_click=lambda _: on_card_scanned("CARD-DANGER-0001"),
                                  bgcolor=COLOR_DANGER, color=ft.Colors.WHITE),
                        ft.Button("ADMIN", on_click=lambda _: on_card_scanned("CARD-ADMIN-0001"),
                                  bgcolor=COLOR_ADMIN, color=ft.Colors.WHITE),
                    ]),
                ],
            ),
        )

    view = ft.View(
        route="/standby", padding=0, bgcolor=BG_OFF_WHITE,
        controls=[
            ft.Column(expand=True, spacing=0, controls=[
                header,
                ft.Column(
                    expand=True,
                    alignment=ft.MainAxisAlignment.SPACE_EVENLY,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Column(tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=4, controls=[
                            ft.Text("EMERGENCY RFID DRILL STATION", size=12,
                                    color=PRIMARY_RED, weight=ft.FontWeight.BOLD),
                            ft.Text("North Wing  ·  Emergency Checkpoint A",
                                    size=11, color=MUTED),
                        ]),
                        scanner,
                        ft.Column(tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=7, controls=[
                            ft.Text("Present an emergency card to the RFID reader.",
                                    size=17, color=INK, weight=ft.FontWeight.BOLD),
                            ft.Text("Safe  ·  Assistance  ·  Danger",
                                    size=12, color=MUTED),
                        ]),
                        developer_panel,
                    ],
                ),
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=18, vertical=10),
                    bgcolor=CARD_WHITE,
                    border=ft.Border.only(top=ft.BorderSide(1, BORDER_COLOR)),
                    content=ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Text("Practice mode · Drill records are simulated",
                                    size=10, color=MUTED),
                            ft.Row(tight=True, spacing=10, controls=[
                                ft.Text("T.A.G.A.P.  /  2026",
                                        size=10, color=MUTED, weight=ft.FontWeight.BOLD),
                                terminal_button,
                            ]),
                        ],
                    ),
                ),
            ])
        ],
    )

    animation_tasks = [
        page.run_task(pulse_ripple, ripples[0], 0.0),
        page.run_task(pulse_ripple, ripples[1], 0.7),
        page.run_task(breathe_scanner, scanner_core),
    ]

    return view, clock, animation_tasks