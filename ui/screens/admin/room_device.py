"""Room Device dashboard and classroom device controls."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Optional

import flet as ft

from config import settings
from data import queries
from data.repositories import RoomRepository
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
    WARNING_YELLOW,
)

logger = logging.getLogger(__name__)

DEFAULT_QUICK_ACTIONS: list[dict[str, object]] = [
    {"key": "contacts", "label": "Manage Students & Contacts", "enabled": True},
    {"key": "alert_history", "label": "View Alert History", "enabled": True},
    {"key": "diagnostics", "label": "Run Device Diagnostics", "enabled": True},
    {"key": "reader_monitor", "label": "Open RFID Monitor", "enabled": True},
]

ACTION_ICONS = {
    "contacts": ft.Icons.GROUPS_2_OUTLINED,
    "alert_history": ft.Icons.HISTORY_ROUNDED,
    "diagnostics": ft.Icons.TROUBLESHOOT_OUTLINED,
    "reader_monitor": ft.Icons.SENSORS_ROUNDED,
}

ACTION_ACCENTS = {
    "contacts": ("#EEF2FF", "#4A62B8"),
    "alert_history": ("#F2EEFF", "#7858B5"),
    "diagnostics": ("#EAF6F3", "#32816B"),
    "reader_monitor": ("#FFF3E8", "#B87538"),
}

ACTION_SUBTITLES = {
    "contacts": "Edit students and parent contacts",
    "alert_history": "Review recent alerts",
    "diagnostics": "Check reader health",
    "reader_monitor": "View live reader activity",
}


def _card(title: str, content: ft.Control, *, col: dict[str, int]) -> ft.Control:
    return ft.Container(
        col=col,
        padding=ft.Padding.all(18),
        bgcolor=CARD_WHITE,
        border=ft.Border.all(1, BORDER_COLOR),
        border_radius=12,
        content=ft.Column(
            tight=True,
            spacing=12,
            controls=[
                ft.Text(title, size=14, weight=ft.FontWeight.W_600, color=INK),
                content,
            ],
        ),
    )


def _display_time(value: object) -> str:
    if value is None:
        return "No scans recorded during this session"
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def build_room_device(
    page: ft.Page,
    room_id: int,
    on_navigate: Callable[[str], None],
    on_exit: Callable[[], None],
    *,
    reader_connected: bool = False,
    reader_port: str = "",
    last_scan_at: object = None,
    last_scan_uid: Optional[str] = None,
    on_scan_test: Optional[Callable[[], None]] = None,
    on_restart_reader: Optional[Callable[[], None]] = None,
    on_disconnect_reader: Optional[Callable[[], None]] = None,
    on_reconnect_reader: Optional[Callable[[], None]] = None,
    on_diagnostics: Optional[Callable[[], None]] = None,
    on_room_updated: Optional[Callable[[], None]] = None,
    register_controls: Optional[Callable[[dict[str, ft.Control]], None]] = None,
) -> ft.View:
    info = queries.get_room_info(room_id)
    stats = queries.get_alert_history_stats()
    dashboard = queries.get_dashboard_data()
    room_number = str(info.get("room_number") or info.get("room_name", ""))
    section = str(info.get("section") or "")
    floor = str(info.get("floor") or "")

    saved_actions = info.get("quick_actions") or []
    saved_by_key = {
        str(action.get("key")): action
        for action in saved_actions
        if isinstance(action, dict) and action.get("key")
    }
    quick_actions = [
        {
            **default_action,
            **saved_by_key.get(str(default_action["key"]), {}),
        }
        for default_action in DEFAULT_QUICK_ACTIONS
    ]

    room_title = ft.Text(
        f"Room {room_number}" if room_number else str(info.get("room_name", "Room")),
        size=27,
        weight=ft.FontWeight.BOLD,
        color=INK,
    )
    location_text = ft.Text(
        " · ".join(value for value in (section, floor) if value),
        size=11,
        color=MUTED,
    )
    reader_dot = ft.Container(
        width=8,
        height=8,
        border_radius=4,
        bgcolor=SUCCESS_GREEN if reader_connected else PRIMARY_RED,
    )
    reader_status = ft.Text(
        "Reader Connected" if reader_connected else "Reader Disconnected",
        size=10,
        color=SUCCESS_GREEN if reader_connected else PRIMARY_RED,
        weight=ft.FontWeight.W_600,
    )
    reader_summary = ft.Text(
        "RFID reader is connected and ready."
        if reader_connected
        else "RFID scans are unavailable until the reader reconnects.",
        size=10,
        color=INK,
    )
    last_scan_text = ft.Text(
        _display_time(last_scan_at or dashboard.get("last_scan_time")),
        size=10,
        color=MUTED,
    )
    last_uid_text = ft.Text(
        last_scan_uid or dashboard.get("last_tag_id") or "No UID captured yet",
        size=10,
        color=INK,
        font_family="Consolas",
    )
    scan_test_status = ft.Text("Ready", size=10, color=MUTED)
    scan_test_button = ft.Button(
        content="Start Scan Test",
        icon=ft.Icons.CONTACTLESS,
        disabled=not reader_connected,
        on_click=lambda _: on_scan_test() if on_scan_test else None,
    )
    restart_button = ft.TextButton(
        content="Restart RFID",
        icon=ft.Icons.REFRESH,
        on_click=lambda _: (
            page.run_task(on_restart_reader) if on_restart_reader else None
        ),
    )
    disconnect_button = ft.TextButton(
        content="Disconnect",
        icon=ft.Icons.CLOSE,
        visible=reader_connected,
        on_click=lambda _: (
            page.run_task(on_disconnect_reader) if on_disconnect_reader else None
        ),
    )
    reconnect_button = ft.TextButton(
        content="Reconnect",
        icon=ft.Icons.PLAY_ARROW,
        visible=not reader_connected,
        on_click=lambda _: (
            page.run_task(on_reconnect_reader) if on_reconnect_reader else None
        ),
    )

    def run_quick_action(action_key: str):
        if action_key == "contacts":
            show_roster_editor(page, room_id)
        elif action_key == "alert_history":
            on_navigate("Alert History")
        elif action_key == "diagnostics" and on_diagnostics:
            page.run_task(on_diagnostics)
        elif action_key == "reader_monitor":
            on_navigate("Reader Monitor")

    quick_actions_grid = ft.ResponsiveRow(
        spacing=8,
        run_spacing=8,
        controls=[],
    )
    edit_quick_actions_button = ft.OutlinedButton(
        content="Customize actions",
        icon=ft.Icons.TUNE_ROUNDED,
    )

    def refresh_quick_actions():
        quick_actions_grid.controls = []
        for action in quick_actions:
            if not bool(action.get("enabled")):
                continue
            action_key = str(action["key"])
            accent_bg, accent_fg = ACTION_ACCENTS[action_key]
            quick_actions_grid.controls.append(
                ft.Container(
                    col={"xs": 12, "sm": 6},
                    padding=12,
                    bgcolor="#FFFFFF",
                    border=ft.Border.all(1, "#E7EAF0"),
                    border_radius=13,
                    ink=True,
                    on_click=lambda _, key=action_key: run_quick_action(key),
                    content=ft.Row(
                        spacing=11,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Container(
                                width=42,
                                height=42,
                                alignment=ft.Alignment.CENTER,
                                bgcolor=accent_bg,
                                border_radius=12,
                                content=ft.Icon(
                                    ACTION_ICONS[action_key],
                                    size=20,
                                    color=accent_fg,
                                ),
                            ),
                            ft.Column(
                                expand=True,
                                tight=True,
                                spacing=3,
                                controls=[
                                    ft.Text(
                                        str(action["label"]),
                                        size=11,
                                        weight=ft.FontWeight.BOLD,
                                        color=INK,
                                    ),
                                    ft.Text(
                                        ACTION_SUBTITLES[action_key],
                                        size=10,
                                        color=MUTED,
                                    ),
                                ],
                            ),
                            ft.Icon(
                                ft.Icons.ARROW_FORWARD_IOS_ROUNDED,
                                size=13,
                                color="#9AA4B2",
                            ),
                        ],
                    ),
                )
            )

    def open_quick_action_editor(_=None):
        editor_state = []
        editor_rows = []
        enabled_summary = ft.Text(size=10, color=MUTED)

        def refresh_enabled_summary() -> None:
            enabled_total = sum(1 for _action, toggle, _label in editor_state if toggle.value)
            enabled_summary.value = f"{enabled_total} of {len(editor_state)} shortcuts visible"
            try:
                enabled_summary.update()
            except RuntimeError:
                pass

        for action in quick_actions:
            action_key = str(action["key"])
            accent_bg, accent_fg = ACTION_ACCENTS[action_key]
            enabled = ft.Switch(
                value=bool(action.get("enabled")),
                active_color=accent_fg,
                on_change=lambda _event: refresh_enabled_summary(),
            )
            label = ft.TextField(
                value=str(action.get("label", "")),
                label="Action label",
                hint_text=f"Name shown for {str(action_key).replace('_', ' ')}",
                max_length=40,
                dense=True,
                filled=True,
                fill_color="#FAFBFD",
                border_color="#E5E9F0",
                focused_border_color="#4169D8",
                border_radius=9,
                content_padding=ft.Padding.symmetric(horizontal=11, vertical=9),
            )
            editor_state.append((action, enabled, label))
            editor_rows.append(
                ft.Container(
                    padding=ft.Padding.all(13),
                    bgcolor="#FFFFFF",
                    border=ft.Border.all(1, "#E7EAF0"),
                    border_radius=13,
                    content=ft.Column(
                        tight=True,
                        spacing=11,
                        controls=[
                            ft.Row(
                                spacing=11,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                controls=[
                                    ft.Container(
                                        width=40,
                                        height=40,
                                        alignment=ft.Alignment.CENTER,
                                        bgcolor=accent_bg,
                                        border_radius=12,
                                        content=ft.Icon(
                                            ACTION_ICONS[action_key],
                                            size=19,
                                            color=accent_fg,
                                        ),
                                    ),
                                    ft.Column(
                                        expand=True,
                                        tight=True,
                                        spacing=3,
                                        controls=[
                                            ft.Text(
                                                ACTION_SUBTITLES[action_key],
                                                size=10,
                                                color=MUTED,
                                            ),
                                            ft.Text(
                                                str(action["key"]).replace("_", " ").title(),
                                                size=12,
                                                weight=ft.FontWeight.BOLD,
                                                color=INK,
                                            ),
                                        ],
                                    ),
                                    ft.Column(
                                        tight=True,
                                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                        spacing=1,
                                        controls=[
                                            ft.Text(
                                                "VISIBLE",
                                                size=8,
                                                color=accent_fg if enabled.value else MUTED,
                                                weight=ft.FontWeight.BOLD,
                                            ),
                                            enabled,
                                        ],
                                    ),
                                ],
                            ),
                            label,
                        ],
                    ),
                )
            )
        refresh_enabled_summary()

        async def save_quick_actions(_event):
            updated_actions = []
            for action, enabled, label in editor_state:
                updated_label = (label.value or "").strip()
                if enabled.value and not updated_label:
                    Toast.show(page, "Enabled quick actions need a label.", "warning")
                    return
                updated_actions.append(
                    {
                        "key": action["key"],
                        "label": updated_label,
                        "enabled": bool(enabled.value),
                    }
                )
            if not any(bool(action["enabled"]) for action in updated_actions):
                Toast.show(page, "Keep at least one quick action enabled.", "warning")
                return

            try:
                await asyncio.to_thread(
                    RoomRepository.update_quick_actions,
                    room_id,
                    updated_actions,
                )
            except Exception as exc:
                logger.exception("Could not save room quick actions")
                Toast.show(page, f"Could not save quick actions: {exc}", "error")
                return

            quick_actions[:] = updated_actions
            page.pop_dialog()
            refresh_quick_actions()
            page.update()
            Toast.show(page, "Quick actions updated.", "success")

        title = ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Row(
                    spacing=11,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Container(
                            width=42,
                            height=42,
                            alignment=ft.Alignment.CENTER,
                            bgcolor="#EEF2FF",
                            border_radius=13,
                            content=ft.Icon(
                                ft.Icons.TUNE_ROUNDED,
                                size=21,
                                color="#4A62B8",
                            ),
                        ),
                        ft.Column(
                            tight=True,
                            spacing=3,
                            controls=[
                                ft.Text(
                                    "Customize Quick Actions",
                                    size=18,
                                    weight=ft.FontWeight.BOLD,
                                    color="#202A3B",
                                ),
                                ft.Text(
                                    "Choose the shortcuts shown on this room dashboard.",
                                    size=10,
                                    color=MUTED,
                                ),
                            ],
                        ),
                    ],
                ),
                ft.IconButton(
                    icon=ft.Icons.CLOSE_ROUNDED,
                    tooltip="Close",
                    icon_color=MUTED,
                    on_click=lambda _: page.pop_dialog(),
                ),
            ],
        )

        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                bgcolor="#F6F7F9",
                title=title,
                content=ft.Container(
                    width=700,
                    height=470,
                    content=ft.Column(
                        expand=True,
                        spacing=12,
                        controls=[
                            ft.Container(
                                padding=ft.Padding.symmetric(horizontal=14, vertical=11),
                                bgcolor="#EEF2FF",
                                border=ft.Border.all(1, "#DFE6FB"),
                                border_radius=11,
                                content=ft.Row(
                                    spacing=9,
                                    controls=[
                                        ft.Icon(
                                            ft.Icons.INFO_OUTLINE_ROUNDED,
                                            color="#4A62B8",
                                            size=17,
                                        ),
                                        ft.Column(
                                            tight=True,
                                            spacing=2,
                                            controls=[
                                                ft.Text(
                                                    "Personalize this dashboard",
                                                    size=11,
                                                    color="#314785",
                                                    weight=ft.FontWeight.BOLD,
                                                ),
                                                ft.Text(
                                                    "Turn shortcuts on or off, then adjust their display names.",
                                                    size=9,
                                                    color="#5F6F9B",
                                                ),
                                            ],
                                        ),
                                        ft.Container(expand=True),
                                        enabled_summary,
                                    ],
                                ),
                            ),
                            ft.Column(
                                expand=True,
                                spacing=9,
                                scroll=ft.ScrollMode.AUTO,
                                controls=editor_rows,
                            ),
                        ],
                    ),
                ),
                actions=[
                    ft.TextButton(
                        content="Cancel",
                        on_click=lambda _: page.pop_dialog(),
                    ),
                    ft.Button(
                        content="Save changes",
                        icon=ft.Icons.SAVE_OUTLINED,
                        bgcolor=PRIMARY_RED,
                        color=ft.Colors.WHITE,
                        on_click=save_quick_actions,
                    ),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
        )

    edit_quick_actions_button.on_click = open_quick_action_editor
    quick_actions_column = ft.Column(
        spacing=8,
        tight=True,
        controls=[quick_actions_grid, edit_quick_actions_button],
    )
    refresh_quick_actions()

    def open_room_info_editor(_=None):
        room_number_field = ft.TextField(
            label="Room Number",
            value=room_number,
            max_length=20,
            autofocus=True,
        )
        section_field = ft.TextField(
            label="Section",
            value=section,
            max_length=100,
        )
        floor_field = ft.TextField(
            label="Floor",
            value=floor,
            max_length=20,
        )

        async def save_room_info(_event):
            updated_number = (room_number_field.value or "").strip()
            updated_section = (section_field.value or "").strip()
            updated_floor = (floor_field.value or "").strip()
            if not updated_number:
                Toast.show(page, "Room number is required.", "warning")
                return
            try:
                await asyncio.to_thread(
                    RoomRepository.update_device_info,
                    room_id,
                    room_number=updated_number,
                    section=updated_section,
                    floor=updated_floor,
                )
            except Exception as exc:
                logger.exception("Could not update room information")
                Toast.show(page, f"Could not save room information: {exc}", "error")
                return

            page.pop_dialog()
            Toast.show(page, "Room information updated.", "success")
            if on_room_updated:
                on_room_updated()

        def close_editor(_event=None):
            page.pop_dialog()

        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        ft.Text("Edit Classroom Device Info", weight=ft.FontWeight.BOLD),
                        ft.IconButton(
                            icon=ft.Icons.CLOSE,
                            tooltip="Close",
                            on_click=close_editor,
                        ),
                    ],
                ),
                content=ft.Container(
                    width=420,
                    content=ft.Column(
                        tight=True,
                        spacing=10,
                        controls=[
                            room_number_field,
                            section_field,
                            floor_field,
                        ],
                    ),
                ),
                actions=[
                    ft.TextButton(
                        content="Cancel",
                        on_click=close_editor,
                    ),
                    ft.Button(content="Save", on_click=save_room_info),
                ],
            )
        )

    reader_port_text = (
        "Simulation reader"
        if settings.USE_MOCK_RFID
        else f"{reader_port or settings.RFID_PORT} · {settings.RFID_BAUDRATE} baud"
    )
    reader_panel = ft.Container(
        padding=14,
        bgcolor=ADMIN_CONTENT_BG,
        border_radius=10,
        content=ft.Column(
            spacing=10,
            controls=[
                ft.Row(
                    spacing=8,
                    controls=[reader_dot, reader_status],
                ),
                ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        ft.Column(
                            tight=True,
                            spacing=2,
                            controls=[
                                ft.Text("DEVICE PORT", size=9, color=MUTED),
                                ft.Text(reader_port_text, size=10, color=INK),
                            ],
                        ),
                        ft.Text(
                            "Ready" if reader_connected else "Offline",
                            size=10,
                            color=SUCCESS_GREEN if reader_connected else PRIMARY_RED,
                        ),
                    ],
                ),
                reader_summary,
                ft.Divider(height=1, color=BORDER_COLOR),
                ft.Row(
                    controls=[
                        ft.Column(
                            tight=True,
                            spacing=4,
                            controls=[
                                ft.Text("Last detected UID", size=9, color=MUTED),
                                last_uid_text,
                            ],
                        ),
                        ft.Container(expand=True),
                        ft.Column(
                            tight=True,
                            spacing=4,
                            controls=[
                                ft.Text("Last scan", size=9, color=MUTED),
                                last_scan_text,
                            ],
                        ),
                    ],
                ),
                ft.Row(
                    tight=True,
                    spacing=8,
                    controls=[
                        scan_test_button,
                        scan_test_status,
                    ],
                ),
            ],
        ),
    )

    edit_info_button = ft.TextButton(
        content="Edit Details",
        icon=ft.Icons.EDIT,
        on_click=open_room_info_editor,
    )
    device_info_panel = ft.Column(
        spacing=10,
        controls=[
            ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                controls=[
                    ft.Column(
                        tight=True,
                        spacing=2,
                        controls=[
                            ft.Text(room_number or "-", size=30, weight=ft.FontWeight.BOLD, color=INK),
                            ft.Text("Room Number", size=9, color=MUTED),
                        ],
                    ),
                    edit_info_button,
                ],
            ),
            ft.Container(
                padding=12,
                bgcolor=ADMIN_CONTENT_BG,
                border_radius=8,
                content=ft.Column(
                    tight=True,
                    spacing=8,
                    controls=[
                        ft.Row(
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            controls=[
                                ft.Column(
                                    tight=True,
                                    spacing=2,
                                    controls=[
                                        ft.Text(section or "Not set", size=11, color=INK),
                                        ft.Text("Section", size=9, color=MUTED),
                                    ],
                                ),
                                ft.Column(
                                    tight=True,
                                    spacing=2,
                                    controls=[
                                        ft.Text(floor or "Not set", size=11, color=INK),
                                        ft.Text("Floor", size=9, color=MUTED),
                                    ],
                                ),
                            ],
                        ),
                        ft.Divider(height=1, color=BORDER_COLOR),
                        ft.Text(f"Device ID: TAGAP-RD-{room_id:03d}", size=10, color=INK),
                        ft.Text(f"Port: {reader_port_text}", size=10, color=INK),
                    ],
                ),
            ),
        ],
    )

    controls_card = ft.Column(
        spacing=8,
        controls=[
            ft.Row(
                controls=[
                    ft.Text("Scan Test", size=11, color=INK),
                    ft.Container(expand=True),
                    scan_test_status,
                ],
            ),
            ft.Row(
                wrap=True,
                spacing=8,
                controls=[
                    restart_button,
                    disconnect_button,
                    reconnect_button,
                    ft.TextButton(
                        content="Run Diagnostics",
                        icon=ft.Icons.TERMINAL_ROUNDED,
                        on_click=lambda _: (
                            page.run_task(on_diagnostics) if on_diagnostics else None
                        ),
                    ),
                ],
            ),
        ],
    )

    emergency_status = ft.Text(
        "No active emergency. RFID listener is ready."
        if reader_connected
        else "RFID reader is offline. Cards will not be processed.",
        size=10,
        color=INK,
    )
    content = ft.Column(
        spacing=16,
        controls=[
            ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Column(
                        tight=True,
                        spacing=2,
                        controls=[
                            ft.Text(
                                "ROOM DEVICE",
                                size=9,
                                weight=ft.FontWeight.W_600,
                                color=MUTED,
                            ),
                            room_title,
                            location_text,
                        ],
                    ),
                    ft.Row(
                        spacing=6,
                        controls=[reader_dot, reader_status],
                    ),
                ],
            ),
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=14, vertical=10),
                bgcolor="#FBE9EC" if not reader_connected else "#E8F5F0",
                border=ft.Border.all(
                    1,
                    "#F4D9DE" if not reader_connected else "#CDE9DE",
                ),
                border_radius=8,
                content=ft.Row(
                    tight=True,
                    spacing=8,
                    controls=[
                        ft.Icon(
                            ft.Icons.SHIELD_OUTLINED,
                            size=14,
                            color=PRIMARY_RED if not reader_connected else SUCCESS_GREEN,
                        ),
                        ft.Text(
                            "DEVICE STATUS",
                            size=10,
                            color=PRIMARY_RED if not reader_connected else SUCCESS_GREEN,
                            weight=ft.FontWeight.BOLD,
                        ),
                        emergency_status,
                    ],
                ),
            ),
            ft.ResponsiveRow(
                spacing=16,
                run_spacing=16,
                controls=[
                    _card("RFID Device", reader_panel, col={"sm": 12, "md": 6}),
                    _card("Room Information", device_info_panel, col={"sm": 12, "md": 6}),
                    _card("Device Controls", controls_card, col={"sm": 12, "md": 6}),
                    _card(
                        "Quick Actions",
                        quick_actions_column,
                        col={"sm": 12, "md": 6},
                    ),
                ],
            ),
        ],
    )

    if register_controls:
        register_controls(
            {
                "reader_dot": reader_dot,
                "reader_status": reader_status,
                "reader_summary": reader_summary,
                "last_scan": last_scan_text,
                "last_uid": last_uid_text,
                "scan_test_status": scan_test_status,
                "scan_test_button": scan_test_button,
                "restart_button": restart_button,
                "disconnect_button": disconnect_button,
                "reconnect_button": reconnect_button,
                "emergency_status": emergency_status,
                "edit_info_button": edit_info_button,
                "quick_actions_grid": quick_actions_grid,
                "edit_quick_actions_button": edit_quick_actions_button,
            }
        )

    return build_admin_shell(
        page,
        active_page="Room Device",
        room_name=f"Room {room_number}" if room_number else str(info.get("room_name", "Room")),
        on_navigate=on_navigate,
        on_back_to_kiosk=on_exit,
        content=ft.Column(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            controls=[content],
        ),
    )
