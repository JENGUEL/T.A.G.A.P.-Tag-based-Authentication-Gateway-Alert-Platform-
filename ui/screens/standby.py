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
    on_open_reader_monitor: Optional[Callable[[], None]] = None,
    rfid_connected: bool = True,
    on_mode_controls: Optional[
        Callable[[ft.Text, ft.Container, Optional[ft.IconButton]], None]
    ] = None,
    sms_connected: bool = True,
    developer_cards: Optional[list[dict[str, str]]] = None,
) -> tuple[ft.View, ft.Text, list[object]]:
    compact = (page.width or 837) < 600
    available_height = page.height or 620
    diameter = min(356, max(224, available_height * 0.48))
    if compact:
        diameter = min(diameter, (page.width or 360) - 48)

    if developer_mode:
        mode_label = "DEVELOPER MODE"
        mode_color = "#3976D8"
    elif settings.USE_MOCK_RFID and settings.USE_MOCK_SMS:
        mode_label = "SIMULATION MODE"
        mode_color = WARNING_YELLOW
    elif settings.USE_MOCK_RFID or settings.USE_MOCK_SMS:
        mode_label = "MIXED MODE"
        mode_color = WARNING_YELLOW
    elif not rfid_connected:
        mode_label = "READER OFFLINE"
        mode_color = PRIMARY_RED
    elif not sms_connected:
        mode_label = "DEGRADED MODE"
        mode_color = WARNING_YELLOW
    elif rfid_connected:
        mode_label = "REAL HARDWARE"
        mode_color = SUCCESS_GREEN

    scanner, ripples, scanner_core = scanner_badge(diameter)
    clock = ft.Text("00:00:00", size=12, weight=ft.FontWeight.BOLD, color=INK)
    mode_text = ft.Text(mode_label, size=10, color=mode_color, weight=ft.FontWeight.BOLD)
    mode_dot = status_dot(mode_color, 7)

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

    mode_icon = None
    if compact:
        reader_monitor_button = ft.IconButton(
            icon=ft.Icons.CABLE,
            tooltip="Open RFID reader monitor",
            on_click=lambda _: on_open_reader_monitor() if on_open_reader_monitor else None,
        )
        status_button = ft.IconButton(
            icon=ft.Icons.MONITOR_HEART,
            icon_color=mode_color,
            tooltip=f"{mode_label} · System status",
            on_click=lambda _: on_open_status() if on_open_status else None,
        )
        mode_icon = status_button
    else:
        reader_monitor_button = ft.TextButton(
            content="Reader Monitor",
            icon=ft.Icons.CABLE,
            on_click=lambda _: on_open_reader_monitor() if on_open_reader_monitor else None,
        )
        status_button = ft.TextButton(
            content=ft.Row(tight=True, spacing=6, controls=[
                mode_dot,
                mode_text,
            ]),
            on_click=lambda _: on_open_status() if on_open_status else None,
        )

    if on_mode_controls:
        on_mode_controls(mode_text, mode_dot, mode_icon)

    mode_banner = ft.Container()
    if developer_mode:
        banner_text = "DEVELOPER MODE · RFID and SMS are simulated."
        banner_color = "#3976D8"
        banner_bg = "#EAF1FF"
        banner_border = "#C9DAF8"
    elif settings.USE_MOCK_RFID or settings.USE_MOCK_SMS:
        banner_text = (
            f"MIXED MODE · RFID: {'simulated' if settings.USE_MOCK_RFID else 'real'}; "
            f"SMS: {'simulated' if settings.USE_MOCK_SMS else 'real'}."
            if settings.USE_MOCK_RFID != settings.USE_MOCK_SMS
            else "SIMULATION MODE · RFID and SMS are simulated; no real messages are sent."
        )
        banner_color = "#8A5A00"
        banner_bg = "#FFF4D6"
        banner_border = "#F0D98F"
    elif not rfid_connected or not sms_connected:
        banner_text = (
            "DEGRADED MODE · "
            f"RFID {'online' if rfid_connected else 'offline'}; "
            f"GSM {'online' if sms_connected else 'offline'}. "
            "Offline SMS remains queued."
        )
        banner_color = PRIMARY_RED if not rfid_connected else "#8A5A00"
        banner_bg = "#FDEBEC" if not rfid_connected else "#FFF4D6"
        banner_border = "#F4D9DE" if not rfid_connected else "#F0D98F"
    else:
        banner_text = ""

    if banner_text:
        mode_banner = ft.Container(
            padding=ft.Padding.symmetric(horizontal=16, vertical=9),
            bgcolor=banner_bg,
            border=ft.Border.all(1, banner_border),
            content=ft.Row(
                tight=True,
                spacing=8,
                controls=[
                    ft.Icon(
                        ft.Icons.DEVELOPER_MODE if developer_mode else ft.Icons.INFO_OUTLINE,
                        size=15,
                        color=banner_color,
                    ),
                    ft.Text(
                        banner_text,
                        size=10,
                        color=banner_color,
                        weight=ft.FontWeight.BOLD,
                    ),
                ],
            ),
        )

    header = ft.Container(
        height=76,
        padding=ft.Padding.symmetric(horizontal=10 if compact else 34),
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
                ft.Row(tight=True, spacing=6 if compact else 12, controls=[
                    reader_monitor_button,
                    clock,
                    status_button,
                ]),
            ],
        ),
    )

    developer_panel = ft.Container()
    if developer_mode:
        mock_card_uids = {
            card["type"]: card["uid"]
            for card in (developer_cards or [])
        }
        mock_card_uids.setdefault("ADMIN", "CARD-ADMIN-0001")
        developer_buttons = [
            ft.Button(
                card_type,
                on_click=lambda _, uid=uid: on_card_scanned(uid),
                bgcolor=get_card_color(card_type),
                color=ft.Colors.WHITE,
            )
            for card_type, uid in mock_card_uids.items()
        ]
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
                    ft.Row(tight=True, spacing=6, controls=developer_buttons),
                ],
            ),
        )

    view = ft.View(
        route="/standby", padding=0, bgcolor=BG_OFF_WHITE,
        controls=[
            ft.Column(expand=True, spacing=0, controls=[
                header,
                mode_banner,
                ft.Column(
                    expand=True,
                    alignment=ft.MainAxisAlignment.SPACE_EVENLY,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Column(tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=4, controls=[
                            ft.Text("EMERGENCY RFID DRILL STATION", size=12,
                                    color=PRIMARY_RED, weight=ft.FontWeight.BOLD),
                            ft.Text("Emergency Checkpoint A",
                                    size=11, color=MUTED),
                        ]),
                        scanner,
                        ft.Column(tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=7, controls=[
                            ft.Text("Present a lockdown status card to the RFID reader.",
                                    size=17, color=INK, weight=ft.FontWeight.BOLD),
                            ft.Text("Lockdown ongoing  ·  Drill ended",
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