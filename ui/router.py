"""
T.A.G.A.P. - UI Router & State Machine
Implements SPA navigation with skeleton loaders.
"""
import asyncio
import flet as ft
import logging
import queue
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.constants import CardType
from models.sms_result_dto import AlertResult, AlertOutcome
from services.alert_service import AlertService
from services.rfid_listener import RfidListener
from services.sms_worker import SmsWorker
from services import get_rfid_service, get_sms_service, reset_services
from config import settings
from services.boot_service import get_system_status, run_preflight_checks
from ui.screens.standby import build_standby_screen
from ui.screens.confirmation import build_confirmation_screen
from ui.screens.admin.room_device import build_room_device
from ui.screens.admin.alert_history import build_alert_history
from ui.screens.admin.reader_monitor import ReaderMonitor
from ui.screens.admin.settings import build_settings
from ui.components.toast import Toast
from ui.theme import *

logger = logging.getLogger("TAGAP.ui.router")


class AppRouter:
    def __init__(self, page: ft.Page):
        self.page = page
        self.current_alert: Optional[AlertResult] = None
        self.clock_ctrl: Optional[ft.Text] = None
        self.room_id: Optional[int] = 1
        self.in_admin_mode = False

        # Reference to the inner content area of the shell
        self.body_host: Optional[ft.Container] = None
        self.current_admin_section: str = "Room Device"
        self.reader_monitor: Optional[ReaderMonitor] = None
        self.developer_mode = False
        self.reader_connected = False
        self.mode_text_control: Optional[ft.Text] = None
        self.mode_dot_control: Optional[ft.Container] = None
        self.mode_icon_control: Optional[ft.IconButton] = None
        self.command_field: Optional[ft.TextField] = None
        self.command_suggestions: Optional[ft.Text] = None
        self.console_refresh = None
        self.console_output_control: Optional[ft.Column] = None
        self.command_console_open = False
        self.console_output_lines: list[tuple[str, str]] = []
        self.console_popup_column: Optional[ft.Column] = None
        self.console_output_popup_open = False
        self.console_expanded = False
        self.console_dialog: Optional[ft.AlertDialog] = None
        self.console_input_content: Optional[ft.Control] = None
        self.console_output_content: Optional[ft.Control] = None
        self.console_title_text: Optional[ft.Text] = None
        self.console_expand_button: Optional[ft.IconButton] = None
        self.console_back_button: Optional[ft.TextButton] = None
        self.standby_animation_tasks: list[object] = []

        self.page.title = "T.A.G.A.P. Kiosk"
        self.page.padding = 0
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.bgcolor = BG_OFF_WHITE
        try:
            self.page.window.full_screen = True
        except Exception:
            pass
        self.page.on_keyboard_event = self._handle_keyboard

        self.rfid_listener = RfidListener(
            self.page,
            self.handle_card_scan,
            self._on_rfid_connection_changed,
        )
        self.reader_connected = self.rfid_listener.rfid.is_connected()
        self.rfid_listener.start()
        self.sms_worker = SmsWorker()
        self.sms_worker.start()
        self.page.run_task(self._clock_tick_loop)

        self.show_standby()
        if settings.USE_MOCK_RFID:
            self._show_simulation_reminder()

    def _handle_keyboard(self, e: ft.KeyboardEvent):
        if e.key == "Tab" and self.command_console_open and self.command_field is not None:
            text = (self.command_field.value or "").strip()
            match = self._complete_command(text)
            if match:
                self.command_field.value = match
                self.command_field.update()
                return
        if e.key == "Escape":
            try:
                self.page.window.full_screen = not self.page.window.full_screen
                self.page.update()
            except Exception:
                pass

    async def _clock_tick_loop(self):
        while True:
            if self.clock_ctrl:
                try:
                    self.clock_ctrl.value = datetime.now().strftime("%H:%M:%S")
                    self.clock_ctrl.update()
                except Exception:
                    pass
            await asyncio.sleep(1)

    # ==========================================
    # KIOSK FLOW
    # ==========================================

    def show_standby(self):
        self.in_admin_mode = False
        self.body_host = None
        self._stop_standby_animations()
        self.page.views.clear()
        view, self.clock_ctrl, self.standby_animation_tasks = build_standby_screen(
            self.page,
            self.handle_card_scan,
            self.toggle_mock_controls,
            self.show_system_status,
            self.show_command_console,
            self.developer_mode,
            self.show_reader_monitor,
            self.reader_connected,
            self._register_mode_controls,
        )
        self.page.views.append(view)
        self.page.update()

    def _register_mode_controls(
        self,
        mode_text: ft.Text,
        mode_dot: ft.Container,
        mode_icon: Optional[ft.IconButton],
    ):
        self.mode_text_control = mode_text
        self.mode_dot_control = mode_dot
        self.mode_icon_control = mode_icon
        self._refresh_mode_indicator()

    def _on_rfid_connection_changed(self, connected: bool):
        self.reader_connected = connected
        self._refresh_mode_indicator()

    def _refresh_mode_indicator(self):
        if self.developer_mode:
            label, color = "DEVELOPER MODE", "#3976D8"
        elif settings.USE_MOCK_RFID:
            label, color = "SIMULATION MODE", WARNING_YELLOW
        elif self.reader_connected:
            label, color = "REAL RFID", SUCCESS_GREEN
        else:
            label, color = "READER OFFLINE", PRIMARY_RED

        if self.mode_text_control is None or self.mode_dot_control is None:
            return
        self.mode_text_control.value = label
        self.mode_text_control.color = color
        self.mode_dot_control.bgcolor = color
        if self.mode_icon_control is not None:
            self.mode_icon_control.icon_color = color
            self.mode_icon_control.tooltip = f"{label} · System status"
        try:
            self.page.update()
        except RuntimeError:
            self.mode_text_control = None
            self.mode_dot_control = None
            self.mode_icon_control = None

    def _stop_standby_animations(self):
        for task in self.standby_animation_tasks:
            task.cancel()
        self.standby_animation_tasks.clear()

    def toggle_mock_controls(self, enabled: bool):
        """Switch the kiosk RFID and SMS services between mock and real hardware."""
        settings.USE_MOCK_RFID = enabled
        settings.USE_MOCK_SMS = enabled
        reset_services()

        try:
            rfid = get_rfid_service()
            gsm = get_sms_service()
            rfid.open()
            gsm.open()
        except Exception as exc:
            Toast.show(self.page, f"Hardware switch failed: {exc}", "error")
        else:
            Toast.show(
                self.page,
                "Developer mock controls enabled" if enabled else "Real hardware mode enabled",
                "success",
            )

        self.show_standby()
        if enabled:
            self._show_simulation_reminder()

    def _show_simulation_reminder(self):
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                tight=True,
                spacing=8,
                controls=[
                    ft.Icon(ft.Icons.INFO_OUTLINE, color=WARNING_YELLOW),
                    ft.Text("Simulation mode is active", size=18, weight=ft.FontWeight.BOLD),
                ],
            ),
            content=ft.Text(
                "RFID scans and SMS are simulated. No real reader is active and "
                "no messages will be sent.",
                size=12,
                color=INK,
            ),
            actions=[
                ft.TextButton(content="Continue", on_click=lambda _: self.page.pop_dialog())
            ],
        )
        self.page.show_dialog(dialog)

    def _complete_command(self, text: str) -> Optional[str]:
        commands = [
            "/developer enable",
            "/developer disable",
            "/system status",
            "/system check",
            "/mock safe",
            "/mock assist",
            "/mock danger",
            "/mock admin",
            "/help",
            "/clear",
        ]
        matches = [command for command in commands if command.startswith(text)]
        return matches[0] if len(matches) == 1 or text else None

    # ==========================================
    # COMMAND CONSOLE
    # ==========================================

    def show_command_console(self):
        if self.command_console_open:
            return

        commands = [
            "/developer enable",
            "/developer disable",
            "/system status",
            "/system check",
            "/mock safe",
            "/mock assist",
            "/mock danger",
            "/mock admin",
            "/help",
            "/clear",
        ]
        logger_output = ft.Column(
            height=300,
            scroll=ft.ScrollMode.ADAPTIVE,
            spacing=3,
            controls=[ft.Text("Loading TAGAP logger...", size=11, color=MUTED)],
        )
        command_output = ft.Column(
            height=300,
            scroll=ft.ScrollMode.ADAPTIVE,
            auto_scroll=True,
            spacing=5,
            controls=[
                ft.Text("TAGAP Console", size=12, color="#315C9E",
                        weight=ft.FontWeight.BOLD),
                ft.Text("Type /help for commands.", size=11, color=MUTED),
            ],
        )
        self.console_output_control = command_output
        self.command_console_open = True
        self.console_output_lines = [
            ("TAGAP Console", "#315C9E"),
            ("Type /help for commands.", MUTED),
        ]
        suggestion_list = ft.Column(tight=True, spacing=2)
        expanded = {"value": False}
        self.console_expanded = False
        content_host = ft.Container(width=620)

        def read_recent_logs() -> list[str]:
            log_path = settings.log_path
            try:
                text = Path(log_path).read_text(encoding="utf-8", errors="replace")
                return text.splitlines()[-35:]
            except Exception as exc:
                return [f"Unable to read application log: {exc}"]

        def refresh_logger(update_page: bool = False):
            lines = read_recent_logs()
            logger_output.controls = [
                ft.Text(
                    line,
                    size=9,
                    selectable=True,
                    color="#B8CDF5",
                    font_family="Consolas",
                )
                for line in lines
            ]
            if update_page and self.command_console_open:
                try:
                    logger_output.update()
                except Exception:
                    pass

        refresh_logger()

        def rebuild_suggestions(text: str):
            text = text.strip()
            matches = [command for command in commands if command.startswith(text)]
            suggestion_list.controls = [
                ft.Container(
                    padding=ft.Padding.symmetric(horizontal=12, vertical=9),
                    bgcolor="#F7FAFF",
                    border=ft.Border.only(bottom=ft.BorderSide(1, "#EEF2F7")),
                    border_radius=8,
                    on_click=lambda _, command=command: choose_completion(command),
                    content=ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Text(command, size=12, color="#2864C7",
                                    weight=ft.FontWeight.W_600,
                                    font_family="Consolas"),
                            ft.Text("Enter", size=9, color="#91A0B5"),
                        ],
                    ),
                )
                for command in matches[:6]
            ]
            suggestion_list.visible = bool(text and matches)

        def choose_completion(command: str):
            if not self.command_console_open or self.command_field is None:
                return
            self.command_field.value = command
            rebuild_suggestions(command)
            self.command_field.update()
            self.page.run_task(self._focus_console_field, self.command_field)

        def on_change(e):
            rebuild_suggestions(e.control.value or "")

        self.command_field = ft.TextField(
            expand=True,
            value="",
            hint_text="Type a command...",
            multiline=True,
            min_lines=1,
            max_lines=2,
            bgcolor="#FFFFFF",
            border_color="#B9C9E8",
            focused_border_color="#3976D8",
            cursor_color="#3976D8",
            color="#2864C7",
            text_style=ft.TextStyle(
                size=13,
                weight=ft.FontWeight.W_600,
                font_family="Consolas",
            ),
            on_change=on_change,
        )

        def submit_command(_):
            if not self.command_console_open:
                return
            command = (self.command_field.value or "").strip()
            matches = [item for item in commands if item.startswith(command)]
            if command and command not in commands and len(matches) == 1:
                choose_completion(matches[0])
                return

            self.command_field.value = ""
            rebuild_suggestions("")
            if command:
                self._terminal_output(
                    command_output,
                    f"$ {command}",
                    "#2864C7",
                )
            self._run_terminal_command(command, command_output)
            refresh_logger(update_page=True)
            if command and not expanded["value"] and self.command_console_open:
                self.show_console_output_popup()

        self.command_field.on_submit = submit_command
        self.console_refresh = refresh_logger

        command_entry = ft.Container(
            bgcolor="#FFFFFF",
            border=ft.Border.all(1, "#CAD8F2"),
            border_radius=16,
            padding=ft.Padding.only(left=14, right=6, top=6, bottom=6),
            shadow=ft.BoxShadow(
                blur_radius=16,
                spread_radius=1,
                color="#16397612",
            ),
            content=ft.Row(
                tight=False,
                vertical_alignment=ft.CrossAxisAlignment.END,
                controls=[
                    self.command_field,
                    ft.IconButton(
                        icon=ft.Icons.ARROW_UPWARD_ROUNDED,
                        icon_color=ft.Colors.WHITE,
                        bgcolor="#3976D8",
                        tooltip="Complete or run command",
                        on_click=submit_command,
                    ),
                ],
            ),
        )

        split_view = ft.Row(
            expand=True,
            spacing=10,
            controls=[
                ft.Container(
                    expand=1,
                    height=300,
                    bgcolor="#0B1010",
                    border_radius=10,
                    padding=12,
                    content=logger_output,
                ),
                ft.Container(
                    expand=1,
                    height=300,
                    bgcolor="#FFFFFF",
                    border=ft.Border.all(1, "#E7EDF5"),
                    border_radius=10,
                    padding=12,
                    content=command_output,
                ),
            ],
        )

        split_view.visible = False
        dialog_ref = {"dialog": None}

        def toggle_expand(_):
            if not self.command_console_open:
                return
            expanded["value"] = not expanded["value"]
            self.console_expanded = expanded["value"]
            content_host.width = 980 if expanded["value"] else 620
            split_view.visible = expanded["value"]
            logger_output.height = 360 if expanded["value"] else 300
            command_output.height = 360 if expanded["value"] else 300
            split_view.height = 360 if expanded["value"] else 300
            content_host.update()

        title_text = ft.Text(
            "TAGAP Command Console",
            size=16,
            weight=ft.FontWeight.BOLD,
            color="#1F2A44",
        )
        expand_button = ft.IconButton(
            icon=ft.Icons.OPEN_IN_FULL_ROUNDED,
            tooltip="Expand command console",
            icon_color="#3976D8",
            on_click=toggle_expand,
        )
        title_row = ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            controls=[
                ft.Row(tight=True, spacing=8, controls=[
                    ft.Container(
                        width=34,
                        height=34,
                        bgcolor="#EAF1FF",
                        border_radius=10,
                        alignment=ft.Alignment.CENTER,
                        content=ft.Icon(ft.Icons.TERMINAL_ROUNDED,
                                        color="#3976D8", size=20),
                    ),
                    title_text,
                ]),
                expand_button,
            ],
        )
        input_content = ft.Column(
            tight=True,
            spacing=8,
            controls=[
                split_view,
                suggestion_list,
                command_entry,
            ],
        )
        self.console_popup_column = ft.Column(
            height=270,
            scroll=ft.ScrollMode.ADAPTIVE,
            auto_scroll=True,
            spacing=6,
        )
        output_content = ft.Container(
            width=520,
            height=290,
            padding=12,
            bgcolor="#FFFFFF",
            border=ft.Border.all(1, "#E7EDF5"),
            border_radius=12,
            visible=False,
            content=self.console_popup_column,
        )
        content_host.content = ft.Column(
            tight=True,
            spacing=0,
            controls=[input_content, output_content],
        )
        back_button = ft.Button(
            content="Back to console",
            visible=False,
            on_click=lambda _: self._on_console_back(dialog_ref["dialog"]),
        )
        close_button = ft.Button(
            content="Close",
            bgcolor="#EAF1FF",
            color="#2864C7",
            on_click=lambda _: self._force_close_dialog(dialog_ref["dialog"]),
        )
        dialog = ft.AlertDialog(
            modal=True,
            bgcolor="#F8FAFD",
            title=title_row,
            content=content_host,
            actions=[back_button, close_button],
        )
        dialog_ref["dialog"] = dialog
        self.console_dialog = dialog
        self.console_input_content = input_content
        self.console_output_content = output_content
        self.console_title_text = title_text
        self.console_expand_button = expand_button
        self.console_back_button = back_button
        self.page.show_dialog(dialog)
        self.page.run_task(self._focus_console_field, self.command_field)

    async def _focus_console_field(self, field: ft.TextField):
        await asyncio.sleep(0)
        if not self.command_console_open or self.command_field is not field:
            return
        try:
            await field.focus()
        except RuntimeError:
            return

    def _terminal_output(self, output: ft.Column, text: str, color: str = "#26364F"):
        if not self.command_console_open or output is not self.console_output_control:
            return
        self.console_output_lines.append((text, color))
        output.controls.append(
            ft.Text(text, size=11, color=color, font_family="Consolas")
        )
        if not self.console_output_popup_open:
            try:
                output.update()
            except RuntimeError:
                pass
        if self.console_output_popup_open and self.console_popup_column is not None:
            self.console_popup_column.controls.append(
                ft.Text(text, size=11, color=color, font_family="Consolas")
            )
            try:
                self.console_popup_column.update()
            except RuntimeError:
                pass

    def show_console_output_popup(self):
        if (
            not self.command_console_open
            or self.console_output_popup_open
            or self.console_dialog is None
            or self.console_popup_column is None
            or self.console_output_content is None
            or self.console_input_content is None
            or self.console_title_text is None
            or self.console_expand_button is None
            or self.console_back_button is None
        ):
            return

        self.console_popup_column.controls = [
            ft.Text(text, size=11, color=color, font_family="Consolas")
            for text, color in self.console_output_lines
        ]
        self.console_output_popup_open = True
        self.console_input_content.visible = False
        self.console_output_content.visible = True
        self.console_title_text.value = "Command Output"
        self.console_expand_button.visible = False
        self.console_back_button.visible = True
        self.page.update()
        logger.info("Terminal output view opened")

    def close_console_output_popup(self, _=None):
        logger.info(
            "Terminal back button clicked; output_open=%s dialog_present=%s",
            self.console_output_popup_open,
            self.console_dialog is not None,
        )
        if (
            not self.console_output_popup_open
            or self.console_dialog is None
            or self.console_input_content is None
            or self.console_output_content is None
            or self.console_title_text is None
            or self.console_expand_button is None
            or self.console_back_button is None
        ):
            return
        self.console_output_popup_open = False
        self.console_input_content.visible = True
        self.console_output_content.visible = False
        self.console_title_text.value = "TAGAP Command Console"
        self.console_expand_button.visible = True
        self.console_back_button.visible = False
        try:
            self.console_dialog.update()
        except Exception as exc:
            self.console_output_popup_open = True
            self.console_input_content.visible = False
            self.console_output_content.visible = True
            self.console_title_text.value = "Command Output"
            self.console_expand_button.visible = False
            self.console_back_button.visible = True
            logger.exception("Terminal back-to-console update failed")
            Toast.show(self.page, f"Could not return to console: {exc}", "error")
            return
        logger.info("Terminal back-to-console click handled")

    def _reset_console_state(self):
        """Clear every console reference. Safe to call more than once."""
        self.console_output_popup_open = False
        self.console_expanded = False
        self.command_console_open = False
        self.command_field = None
        self.command_suggestions = None
        self.console_refresh = None
        self.console_output_control = None
        self.console_popup_column = None
        self.console_output_lines = []
        self.console_dialog = None
        self.console_input_content = None
        self.console_output_content = None
        self.console_title_text = None
        self.console_expand_button = None
        self.console_back_button = None

    def _dismiss_console_dialog(self):
        """Close the console dialog no matter what the console flags say."""
        self._force_close_dialog(self.console_dialog)

    def _force_close_dialog(self, dialog):
        """Sync entry point for button clicks. Schedules the async close."""
        self.page.run_task(self._force_close_dialog_async, dialog)

    async def _force_close_dialog_async(self, dialog):
        """Close a dialog and let the client finish before touching anything else.

        The dialog is closed with open=False first and is NOT removed from the
        page in the same update. Removing it in the same batch can leave the
        modal route stuck on the client while Python thinks it is gone.
        """
        logger.info("Force close requested; dialog_present=%s", dialog is not None)
        if dialog is not None:
            try:
                dialog.open = False
                dialog.update()
            except Exception:
                logger.exception("Force close: dialog.update failed")
        try:
            self.page.update()
        except Exception:
            pass
        # Let the client actually pop the modal before anything else changes.
        await asyncio.sleep(0.35)
        self._reset_console_state()
        logger.info("Console dialog force-closed")

    def _on_console_back(self, dialog):
        """Back button: return to console, or close if the state is stale."""
        if self.console_output_popup_open and self.console_dialog is not None:
            self.close_console_output_popup()
        else:
            self._force_close_dialog(dialog)

    def close_command_console(self, _=None):
        logger.info(
            "Terminal close button clicked; console_open=%s dialog_present=%s",
            self.command_console_open,
            self.console_dialog is not None,
        )
        # No early return on state: the Close button must always dismiss.
        self._dismiss_console_dialog()

    def _auto_close_console_after_developer_enable(self):
        if self.console_dialog is None and not self.command_console_open:
            logger.warning("Developer activation: console already closed")
            return
        self._dismiss_console_dialog()
        logger.info("Command console auto-closed after developer mode activation")

    def _run_terminal_command(self, command: str, output: ft.Column):
        normalized = command.strip().lower()

        if normalized == "/clear":
            self.console_output_lines.clear()
            output.controls.clear()
            output.update()
            if self.console_output_popup_open and self.console_popup_column is not None:
                self.console_popup_column.controls.clear()
                self.console_popup_column.update()
            return
        if normalized == "/help":
            self._terminal_output(output, "Available commands:")
            for line in (
                "/developer enable  - activate mock controls",
                "/developer disable - return to real hardware",
                "/system status     - open connected-system status",
                "/system check      - run deep preflight checks",
                "/mock safe|assist|danger|admin",
                "/clear",
            ):
                self._terminal_output(output, line)
            return
        if normalized == "/system status":
            self.page.run_task(self._run_terminal_status, output)
            return
        if normalized == "/system check":
            self.page.run_task(self._run_terminal_system_check, output)
            return
        if normalized == "/developer enable":
            self.page.run_task(self._run_terminal_hardware_mode, output, True)
            return
        if normalized == "/developer disable":
            self.page.run_task(self._run_terminal_hardware_mode, output, False)
            return
        if normalized.startswith("/mock ") and self.developer_mode:
            card_type = normalized.split(maxsplit=1)[1].upper()
            uid_map = {
                "SAFE": "CARD-SAFE-0001",
                "ASSIST": "CARD-ASSIST-0001",
                "DANGER": "CARD-DANGER-0001",
                "ADMIN": "CARD-ADMIN-0001",
            }
            if card_type in uid_map:
                self._terminal_output(output, f"Simulating {card_type} card tap...")
                self.close_command_console()
                self.handle_card_scan(uid_map[card_type])
            else:
                self._terminal_output(output, "Unknown mock card. Use safe, assist, danger, or admin.", "#F0A5B0")
            return
        if normalized.startswith("/mock ") and not self.developer_mode:
            self._terminal_output(output, "Developer Mode is disabled. Run /developer enable.", "#F0A5B0")
            return

        self._terminal_output(output, f"Command not found: {command}", "#F0A5B0")

    async def _run_terminal_system_check(self, output: ft.Column):
        self._terminal_output(output, "Starting full system check...", "#3976D8")
        messages: queue.Queue[str] = queue.Queue()
        check_task = asyncio.create_task(
            asyncio.to_thread(run_preflight_checks, messages.put)
        )

        while not check_task.done():
            while not messages.empty():
                self._terminal_output(output, f"Checking: {messages.get_nowait()}")
            await asyncio.sleep(0.1)

        errors = await check_task
        while not messages.empty():
            self._terminal_output(output, f"Checking: {messages.get_nowait()}")

        status = get_system_status()
        for item in status.values():
            connected = bool(item["connected"])
            self._terminal_output(
                output,
                f"[{'OK' if connected else 'FAIL'}] {item['label']}: {item['detail']}",
                "#16805D" if connected else "#C2414B",
            )
        if errors:
            for error in errors:
                self._terminal_output(output, f"[ERROR] {error}", "#C2414B")
            self._terminal_output(output, "System check finished with issues.", "#C2414B")
        else:
            self._terminal_output(output, "System check passed.", "#16805D")
        if self.console_refresh:
            self.console_refresh(update_page=True)

    async def _run_terminal_status(self, output: ft.Column):
        self._terminal_output(output, "Reading current system status...", "#3976D8")
        status = await asyncio.to_thread(get_system_status)
        for item in status.values():
            connected = bool(item["connected"])
            self._terminal_output(
                output,
                f"[{'CONNECTED' if connected else 'OFFLINE'}] "
                f"{item['label']}: {item['detail']}",
                "#16805D" if connected else "#C2414B",
            )
        if self.console_refresh:
            self.console_refresh(update_page=True)

    async def _run_terminal_hardware_mode(self, output: ft.Column, enable: bool):
        desired = "Developer Mode" if enable else "Real Hardware Mode"
        self._terminal_output(output, f"Activating {desired}...", "#3976D8")
        self._terminal_output(output, "Waiting for RFID and GSM services to switch...")
        previous_rfid_mock = settings.USE_MOCK_RFID
        previous_sms_mock = settings.USE_MOCK_SMS
        self.rfid_listener.stop()
        await asyncio.sleep(0.6)
        await asyncio.to_thread(self.sms_worker.stop)

        try:
            await asyncio.to_thread(reset_services)
            settings.USE_MOCK_RFID = enable
            settings.USE_MOCK_SMS = enable
            rfid = get_rfid_service()
            sms = get_sms_service()
            await asyncio.gather(
                asyncio.to_thread(rfid.open),
                asyncio.to_thread(sms.open),
            )

            self.reader_connected = rfid.is_connected()
            self.rfid_listener.rfid = rfid
            self.rfid_listener.is_running = True
            self.rfid_listener.start()
            self.sms_worker = SmsWorker(sms_service=sms)
            self.sms_worker.start()
            self.developer_mode = enable

            self._terminal_output(
                output,
                f"[OK] {desired} active. RFID and GSM services are ready.",
                "#16805D",
            )
            if self.console_refresh:
                self.console_refresh(update_page=True)
            if enable and self.command_console_open and output is self.console_output_control:
                await self._force_close_dialog_async(self.console_dialog)
                logger.info("Command console closed after developer mode activation")
                await asyncio.sleep(0.1)
            self.show_standby()
            if enable:
                self._show_simulation_reminder()
            Toast.show(self.page, f"{desired} activated", "success")
        except Exception as exc:
            self._terminal_output(output, f"[ERROR] Could not activate {desired}: {exc}", "#C2414B")
            settings.USE_MOCK_RFID = previous_rfid_mock
            settings.USE_MOCK_SMS = previous_sms_mock
            try:
                await asyncio.to_thread(reset_services)
                restored_rfid = get_rfid_service()
                restored_sms = get_sms_service()
                await asyncio.gather(
                    asyncio.to_thread(restored_rfid.open),
                    asyncio.to_thread(restored_sms.open),
                )
                self.rfid_listener.rfid = restored_rfid
                self.rfid_listener.is_running = True
                self.rfid_listener.start()
                self.sms_worker = SmsWorker(sms_service=restored_sms)
                self.sms_worker.start()
            except Exception as recovery_error:
                self._terminal_output(
                    output,
                    f"[ERROR] Hardware recovery failed: {recovery_error}",
                    "#C2414B",
                )
            if self.console_refresh:
                self.console_refresh(update_page=True)

    def show_system_status(self):
        status = get_system_status()
        if self.developer_mode:
            status["mode"] = {
                "label": "Operating mode",
                "connected": True,
                "detail": "Developer mode; RFID and SMS are simulated",
                "state": "DEVELOPER MODE",
                "color": "#3976D8",
            }
        rows = []
        for item in status.values():
            connected = bool(item["connected"])
            state = str(item.get("state", "Connected" if connected else "Not connected"))
            state_color = str(item.get(
                "color", SUCCESS_GREEN if connected else PRIMARY_RED
            ))
            rows.append(
                ft.Container(
                    padding=14,
                    bgcolor="#F7F3F4",
                    border=ft.Border.all(1, BORDER_COLOR),
                    border_radius=12,
                    content=ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Column(tight=True, spacing=3, controls=[
                                ft.Text(str(item["label"]), size=13,
                                        weight=ft.FontWeight.BOLD, color=INK),
                                ft.Text(str(item["detail"]), size=10, color=MUTED),
                            ]),
                            ft.Container(
                                padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                                bgcolor=(
                                    "#EAF1FF" if state_color == "#3976D8"
                                    else "#FFF4D6" if state_color == "#D9A05B"
                                    else "#E8F5F0" if connected
                                    else "#FDEBEC"
                                ),
                                border_radius=8,
                                content=ft.Text(
                                    state,
                                    size=10,
                                    color=state_color,
                                    weight=ft.FontWeight.BOLD,
                                ),
                            ),
                        ],
                    ),
                )
            )

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("System Status", size=18, weight=ft.FontWeight.BOLD),
            content=ft.Container(width=430, content=ft.Column(
                tight=True, spacing=10, controls=rows
            )),
            actions=[
                ft.TextButton(content="Close", on_click=lambda _: self.page.pop_dialog())
            ],
        )
        self.page.show_dialog(dialog)

    def handle_card_scan(self, uid: str):
        if self.current_alert is not None or self.in_admin_mode:
            return

        result = AlertService.scan_card(uid)

        if result.outcome == AlertOutcome.NEEDS_CONFIRMATION:
            self.current_alert = result
            self.show_confirmation(result)
        elif result.outcome == AlertOutcome.ADMIN_ACCESS:
            self.room_id = result.room_id or 1
            self.show_admin("Room Device")
        elif result.outcome == AlertOutcome.REJECTED_DUPLICATE:
            Toast.show(self.page, "Card already scanned. Please wait.", "warning")
        else:
            Toast.show(self.page, f"Unknown card: {uid}", "error")

    def show_confirmation(self, result: AlertResult):
        self.rfid_listener.stop()
        self._stop_standby_animations()
        self.page.views.clear()

        def on_confirm():
            exec_result = AlertService.execute_alert(result.card_uid, result.scan_ts)
            if exec_result.outcome == AlertOutcome.ERROR:
                Toast.show(self.page, f"Error: {exec_result.error_message}", "error")
            else:
                Toast.show(self.page, f"{result.card_type.value} Sent to {exec_result.sms_queued} recipients!", "success")
            self.current_alert = None
            self.rfid_listener.start()
            self.show_standby()

        def on_cancel():
            if hasattr(self.page, "countdown_task") and self.page.countdown_task:
                self.page.countdown_task.cancel()
            Toast.show(self.page, "Alert cancelled. No messages were sent.", "warning")
            self.current_alert = None
            self.rfid_listener.start()
            self.show_standby()

        self.page.views.append(build_confirmation_screen(self.page, result, on_confirm, on_cancel))
        self.page.update()

    # ==========================================
    # ADMIN FLOW (SPA)
    # ==========================================

    def show_admin(self, section: str = "Room Device"):
        self.in_admin_mode = True
        self.rfid_listener.stop()
        self._stop_standby_animations()

        if hasattr(self.page, "countdown_task") and self.page.countdown_task:
            try:
                self.page.countdown_task.cancel()
            except Exception:
                pass

        # Build the initial view (returns a View with the shell + content)
        view = self._build_view(section)

        # Extract the body_host from the view structure:
        # view.controls[0] -> Row
        # Row.controls[1] -> Column
        # Column.controls[1] -> Container (content area)
        try:
            self.body_host = view.controls[0].controls[1].controls[1]
        except (AttributeError, IndexError):
            self.body_host = None

        self.current_admin_section = section
        self.page.views.clear()
        self.page.views.append(view)
        self.page.update()

    def show_reader_monitor(self):
        self.show_admin("Reader Monitor")

    def _build_view(self, section: str) -> ft.View:
        """Builds the full view (shell + content) for a given section."""
        # Rebuilding the view each time is fine because we swap the body_host,
        # not replace the whole view in page.views
        if section == "Reader Monitor":
            get_rfid_service().close()
            self.reader_monitor = ReaderMonitor(self.page)
            return self.reader_monitor.build(
                self.room_id or 1, self._navigate_admin, self.exit_admin,
            )
        if self.reader_monitor is not None:
            self.reader_monitor.dispose()
            self.reader_monitor = None
        if section == "Alert History":
            return build_alert_history(self.page, self.room_id, self._navigate_admin, self.exit_admin)
        elif section == "Settings":
            return build_settings(self.page, self.room_id, self._navigate_admin, self.exit_admin)
        else:
            return build_room_device(self.page, self.room_id, self._navigate_admin, self.exit_admin)

    def _navigate_admin(self, section: str):
        if section == "Main Kiosk":
            self.exit_admin()
            return

        # If section is the same as current, do nothing
        if section == self.current_admin_section:
            return

        if self.reader_monitor is not None:
            self.reader_monitor.dispose()
            self.reader_monitor = None

        # If we somehow lost body_host, fall back to full reload
        if not self.body_host:
            self.show_admin(section)
            return

        self.page.run_task(self._transition_admin, section)

    async def _transition_admin(self, section: str):
        # 1. Fade out current content
        self.body_host.opacity = 0
        self.page.update()
        await asyncio.sleep(0.15)

        # 2. Show Skeleton loader
        self.body_host.content = self._build_skeleton(section)
        self.body_host.opacity = 1
        self.page.update()
        await asyncio.sleep(0.25)

        # 3. Fade out skeleton
        self.body_host.opacity = 0
        self.page.update()
        await asyncio.sleep(0.1)

        # 4. Build the new view and extract its content
        new_view = self._build_view(section)
        try:
            new_content = new_view.controls[0].controls[1].controls[1].content
        except (AttributeError, IndexError):
            new_content = ft.Container()

        # 5. Swap content and fade in
        self.body_host.content = new_content
        self.body_host.opacity = 1
        self.current_admin_section = section
        self.page.update()

    def _build_skeleton(self, title: str) -> ft.Control:
        def block(height: int, width: int = None) -> ft.Container:
            return ft.Container(height=height, width=width, bgcolor="#EEE9EB", border_radius=8)
        return ft.Column(expand=True, spacing=16, controls=[
            ft.Row(tight=True, spacing=10, controls=[
                ft.ProgressRing(value=None, color=PRIMARY_RED, stroke_width=2),
                ft.Text(f"Loading {title}...", size=13, color=MUTED),
            ]),
            ft.Row(spacing=14, controls=[
                ft.Container(expand=1, padding=18, bgcolor=CARD_WHITE, border_radius=16, content=ft.Column(spacing=14, controls=[block(18, 180), block(12, 250), block(180)])),
                ft.Container(expand=1, padding=18, bgcolor=CARD_WHITE, border_radius=16, content=ft.Column(spacing=14, controls=[block(18, 150), block(64), block(14), block(14)])),
            ])
        ])

    def exit_admin(self):
        self.in_admin_mode = False
        self.body_host = None
        if self.reader_monitor is not None:
            self.reader_monitor.dispose()
            self.reader_monitor = None
        self.rfid_listener.start()
        self.show_standby()