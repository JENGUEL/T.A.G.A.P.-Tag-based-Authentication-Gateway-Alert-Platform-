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
from typing import Callable, Optional
from uuid import uuid4

from core.constants import (
    EVENT_ALERT_CANCELLED,
    EVENT_ALERT_CONFIRMED,
    EVENT_CONFIRMATION_SHOWN,
    EVENT_CONFIRMATION_TIMEOUT,
    EVENT_DEVICE_CONNECTION_CHANGED,
    EVENT_RFID_SCAN_DETECTED,
    CardType,
    card_type_value,
)
from models.sms_result_dto import AlertResult, AlertOutcome
from services.alert_service import AlertService
from services.audio_service import AudioService
from services.rfid_listener import RfidListener
from services.sms_worker import SmsWorker
from services import get_rfid_service, get_sms_service, reset_services
from config import settings
from data.repositories import CardCategoryRepository, CardRepository
from services.boot_service import get_system_status, run_preflight_checks
from ui.screens.standby import build_standby_screen
from ui.screens.confirmation import build_confirmation_screen
from ui.screens.admin.room_device import build_room_device
from ui.screens.admin.alert_history import build_alert_history
from ui.screens.admin.operational_report import build_operational_report
from ui.screens.admin.reader_monitor import ReaderMonitor
from ui.screens.admin.shell import set_active_admin_navigation
from ui.screens.admin.settings import build_settings
from ui.components.toast import Toast
from ui.theme import *

logger = logging.getLogger("TAGAP.ui.router")


class AppRouter:
    def __init__(self, page: ft.Page):
        self.page = page
        self.current_alert: Optional[AlertResult] = None
        self.confirmation_scan_action: Optional[Callable[[], None]] = None
        self.clock_ctrl: Optional[ft.Text] = None
        self.room_id: Optional[int] = 1
        self.in_admin_mode = False
        self.admin_authorized = False

        # Reference to the inner content area of the shell
        self.body_host: Optional[ft.Container] = None
        self.current_admin_section: str = "Room Device"
        self.reader_monitor: Optional[ReaderMonitor] = None
        self.developer_mode = False
        self.reader_connected = False
        self.sms_connected = False
        self.last_room_scan_at: Optional[datetime] = None
        self.last_room_scan_uid: Optional[str] = None
        self.room_device_controls: dict[str, ft.Control] = {}
        self.room_device_scan_test_armed = False
        self.card_registration_session: Optional[dict[str, object]] = None
        self.reader_monitor_auth_pending = False
        self.reader_monitor_auth_dialog: Optional[ft.AlertDialog] = None
        self.reader_monitor_auth_status: Optional[ft.Text] = None
        self.mode_text_control: Optional[ft.Text] = None
        self.mode_dot_control: Optional[ft.Container] = None
        self.mode_icon_control: Optional[ft.IconButton] = None
        self.runtime_hardware_dialog: Optional[ft.AlertDialog] = None
        self.runtime_hardware_log: Optional[ft.Column] = None
        self.runtime_hardware_status_controls: dict[str, ft.Text] = {}
        self.runtime_reconnect_in_progress = False
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
        self._record_device_connection_change(
            "RFID reader",
            self.reader_connected,
            settings.RFID_PORT,
        )
        self.rfid_listener.start()
        self.sms_worker = SmsWorker(
            on_connection_changed=self._on_sms_connection_changed
        )
        self.sms_worker.start()
        self.sms_connected = get_sms_service().is_connected()
        self._record_device_connection_change(
            "GSM modem",
            self.sms_connected,
            settings.GSM_PORT,
        )
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
            sms_connected=self.sms_connected,
            developer_cards=[
                {"type": str(card["type"]), "uid": str(card["uid"])}
                for card in CardRepository.get_for_room(self.room_id or 1)
                if bool(card["active"])
            ],
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
        if self.reader_connected != connected:
            self._record_device_connection_change(
                "RFID reader",
                connected,
                settings.RFID_PORT,
            )
        self.reader_connected = connected
        self._refresh_room_device_controls()
        if not connected:
            self.rfid_listener.stop()
        self.page.run_task(
            self._apply_runtime_hardware_connection,
            "RFID reader",
            connected,
        )

    def _register_room_device_controls(self, controls: dict[str, ft.Control]):
        self.room_device_controls = controls

    def _refresh_room_device_controls(self):
        controls = self.room_device_controls
        if not controls:
            return

        connected = self.reader_connected
        status_text = controls.get("reader_status")
        if isinstance(status_text, ft.Text):
            status_text.value = "Reader Connected" if connected else "Reader Disconnected"
            status_text.color = SUCCESS_GREEN if connected else PRIMARY_RED

        reader_dot = controls.get("reader_dot")
        if isinstance(reader_dot, ft.Container):
            reader_dot.bgcolor = SUCCESS_GREEN if connected else PRIMARY_RED

        reader_summary = controls.get("reader_summary")
        if isinstance(reader_summary, ft.Text):
            reader_summary.value = (
                "RFID reader is connected and ready."
                if connected
                else "RFID scans are unavailable until the reader reconnects."
            )

        scan_button = controls.get("scan_test_button")
        if isinstance(scan_button, ft.Button):
            scan_button.disabled = not connected

        disconnect_button = controls.get("disconnect_button")
        if isinstance(disconnect_button, ft.TextButton):
            disconnect_button.visible = connected
        reconnect_button = controls.get("reconnect_button")
        if isinstance(reconnect_button, ft.TextButton):
            reconnect_button.visible = not connected

        emergency_status = controls.get("emergency_status")
        if isinstance(emergency_status, ft.Text):
            emergency_status.value = (
                "No active emergency. RFID listener is ready."
                if connected
                else "RFID reader is offline. Cards will not be processed."
            )
            emergency_status.color = INK

        try:
            self.page.update()
        except RuntimeError:
            self.room_device_controls = {}

    def _start_room_device_scan_test(self):
        if not self.reader_connected:
            Toast.show(self.page, "Connect the RFID reader before starting a scan test.", "warning")
            return

        self.room_device_scan_test_armed = not self.room_device_scan_test_armed
        test_status = self.room_device_controls.get("scan_test_status")
        if isinstance(test_status, ft.Text):
            test_status.value = (
                "Waiting for a card - no alert will be sent"
                if self.room_device_scan_test_armed
                else "Ready"
            )
            test_status.color = WARNING_YELLOW if self.room_device_scan_test_armed else MUTED
            test_status.update()
        Toast.show(
            self.page,
            "Tap a card to test the reader. This will not send an alert."
            if self.room_device_scan_test_armed
            else "Scan test cancelled.",
            "info",
        )

    def _record_room_device_scan(self, uid: str):
        self.last_room_scan_at = datetime.now()
        self.last_room_scan_uid = uid
        last_scan = self.room_device_controls.get("last_scan")
        if isinstance(last_scan, ft.Text):
            last_scan.value = self.last_room_scan_at.strftime("%Y-%m-%d %H:%M:%S")
        last_uid = self.room_device_controls.get("last_uid")
        if isinstance(last_uid, ft.Text):
            last_uid.value = uid
        if self.room_device_scan_test_armed:
            self.room_device_scan_test_armed = False
            test_status = self.room_device_controls.get("scan_test_status")
            if isinstance(test_status, ft.Text):
                test_status.value = f"Read UID {uid}"
                test_status.color = SUCCESS_GREEN
            Toast.show(
                self.page,
                f"RFID scan test passed. UID: {uid}",
                "success",
            )
        try:
            self.page.update()
        except RuntimeError:
            self.room_device_controls = {}

    async def _restart_room_device_reader(self):
        await self._connect_room_device_reader(restart=True)

    async def _reconnect_room_device_reader(self):
        await self._connect_room_device_reader(restart=False)

    async def _connect_room_device_reader(self, *, restart: bool):
        self.rfid_listener.stop()
        await asyncio.sleep(0.6)
        rfid = get_rfid_service()
        try:
            if restart:
                await asyncio.to_thread(rfid.close)
            await asyncio.to_thread(rfid.open)
        except Exception as exc:
            logger.exception("Could not reconnect RFID reader")
            self.reader_connected = rfid.is_connected()
            self._refresh_room_device_controls()
            Toast.show(self.page, f"RFID connection failed: {exc}", "error")
            if not self.reader_connected:
                self.page.run_task(
                    self._apply_runtime_hardware_connection,
                    "RFID reader",
                    False,
                )
            return

        self.reader_connected = rfid.is_connected()
        if self.reader_connected:
            self.rfid_listener.rfid = rfid
            self.rfid_listener.start()
            self._refresh_room_device_controls()
            self._refresh_mode_indicator()
            Toast.show(
                self.page,
                "RFID reader restarted and is ready." if restart else "RFID reader connected.",
                "success",
            )
        else:
            self._refresh_room_device_controls()
            Toast.show(self.page, "Reader did not complete its connection handshake.", "error")

    async def _disconnect_room_device_reader(self):
        decision = asyncio.get_running_loop().create_future()

        def choose(disconnect: bool):
            if not decision.done():
                self.page.pop_dialog()
                decision.set_result(disconnect)

        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("Disconnect RFID Reader?", weight=ft.FontWeight.BOLD),
                content=ft.Text(
                    "Card scans will be unavailable until the reader is reconnected.",
                    size=12,
                ),
                actions=[
                    ft.TextButton(content="Cancel", on_click=lambda _: choose(False)),
                    ft.Button(
                        content="Disconnect",
                        on_click=lambda _: choose(True),
                    ),
                ],
            )
        )
        if not await decision:
            return

        self.rfid_listener.stop()
        await asyncio.sleep(0.6)
        try:
            await asyncio.to_thread(get_rfid_service().close)
        except Exception as exc:
            logger.exception("Could not disconnect RFID reader")
            Toast.show(self.page, f"Could not disconnect reader: {exc}", "error")
            return
        self.reader_connected = False
        self._refresh_room_device_controls()
        self._refresh_mode_indicator()
        Toast.show(self.page, "RFID reader disconnected by operator.", "warning")

    async def _show_room_device_diagnostics(self):
        rfid = get_rfid_service()
        try:
            present = await asyncio.to_thread(rfid.is_device_present)
        except Exception as exc:
            logger.exception("RFID device diagnostics failed")
            Toast.show(self.page, f"Device check failed: {exc}", "error")
            return

        state = "CONNECTED" if rfid.is_connected() else "DISCONNECTED"
        presence = "DETECTED" if present else "NOT DETECTED"
        mode = "SIMULATION" if settings.USE_MOCK_RFID else "REAL HARDWARE"
        lines = [
            f"[INFO] Operating mode: {mode}",
            f"[{'OK' if present else 'FAIL'}] Configured port {settings.RFID_PORT}: {presence}",
            f"[{'OK' if rfid.is_connected() else 'FAIL'}] Serial handle: {state}",
            f"[INFO] Baud rate: {settings.RFID_BAUDRATE}",
            f"[INFO] Last scanned UID: {self.last_room_scan_uid or 'None'}",
        ]
        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Row(
                    spacing=8,
                    controls=[
                        ft.Icon(ft.Icons.TERMINAL_ROUNDED, color="#3976D8"),
                        ft.Text("RFID Device Diagnostics", weight=ft.FontWeight.BOLD),
                    ],
                ),
                content=ft.Container(
                    width=520,
                    padding=12,
                    bgcolor="#15191E",
                    border_radius=8,
                    content=ft.Column(
                        tight=True,
                        spacing=7,
                        controls=[
                            ft.Text(line, size=11, color="#B8CDF5", font_family="Consolas")
                            for line in lines
                        ],
                    ),
                ),
                actions=[
                    ft.TextButton(content="Close", on_click=lambda _: self.page.pop_dialog())
                ],
            )
        )

    def _on_sms_connection_changed(self, connected: bool):
        self.page.run_task(self._apply_sms_connection_changed, connected)

    async def _apply_sms_connection_changed(self, connected: bool):
        if self.sms_connected != connected:
            self._record_device_connection_change(
                "GSM modem",
                connected,
                settings.GSM_PORT,
            )
        self.sms_connected = connected
        dialog_was_open = self.runtime_hardware_dialog is not None
        completed = await self._apply_runtime_hardware_connection(
            "GSM modem",
            connected,
        )
        if connected and not dialog_was_open and not completed:
            Toast.show(
                self.page,
                "GSM modem connected. Queued SMS delivery has resumed.",
                "success",
            )

    async def _apply_runtime_hardware_connection(
        self,
        device_label: str,
        connected: bool,
    ) -> bool:
        self._refresh_mode_indicator()
        if not connected:
            self._show_runtime_hardware_dialog(device_label)
            return False

        if self.runtime_hardware_dialog is None:
            return False

        self._refresh_runtime_hardware_dialog()
        self._append_runtime_hardware_log(f"[CONNECTED] {device_label}", SUCCESS_GREEN)
        if self.reader_connected and self.sms_connected:
            self._close_runtime_hardware_dialog()
            Toast.show(self.page, "All real hardware devices are reconnected.", "success")
            return True
        return False

    def _record_device_connection_change(
        self,
        device: str,
        connected: bool,
        port: str,
    ) -> None:
        mock_mode = (
            settings.USE_MOCK_RFID
            if device == "RFID reader"
            else settings.USE_MOCK_SMS
        )
        AlertService.record_operational_event(
            EVENT_DEVICE_CONNECTION_CHANGED,
            {
                "room_id": self.room_id or 1,
                "device": device,
                "connected": connected,
                "port": port,
                "mode": "SIMULATION" if mock_mode else "REAL HARDWARE",
            },
        )

    def _show_runtime_hardware_dialog(self, disconnected_device: str):
        if self.runtime_hardware_dialog is not None:
            self._refresh_runtime_hardware_dialog()
            for key, label, port in (
                ("rfid", "RFID reader", settings.RFID_PORT),
                ("gsm", "GSM modem", settings.GSM_PORT),
            ):
                is_connected = self.reader_connected if key == "rfid" else self.sms_connected
                self._append_runtime_hardware_log(
                    f"[{'CONNECTED' if is_connected else 'DISCONNECTED'}] "
                    f"{label} ({port})",
                    SUCCESS_GREEN if is_connected else PRIMARY_RED,
                )
            self._append_runtime_hardware_log(
                f"[EVENT] {disconnected_device} disconnected during operation",
                PRIMARY_RED,
            )
            return

        self.runtime_hardware_log = ft.Column(
            height=130,
            scroll=ft.ScrollMode.ADAPTIVE,
            auto_scroll=True,
            spacing=4,
            controls=[],
        )
        status_rows = []
        for key, label, port in (
            ("rfid", "RFID reader", settings.RFID_PORT),
            ("gsm", "GSM modem", settings.GSM_PORT),
        ):
            is_connected = self.reader_connected if key == "rfid" else self.sms_connected
            state_text = ft.Text(
                "CONNECTED" if is_connected else "DISCONNECTED",
                size=10,
                weight=ft.FontWeight.BOLD,
                color=SUCCESS_GREEN if is_connected else PRIMARY_RED,
                font_family="Consolas",
            )
            self.runtime_hardware_status_controls[key] = state_text
            status_rows.append(
                ft.Container(
                    padding=8,
                    bgcolor="#FFFFFF",
                    border=ft.Border.all(1, "#E7EDF5"),
                    border_radius=8,
                    content=ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Text(f"{label} ({port})", size=11, color=INK),
                            state_text,
                        ],
                    ),
                )
            )

        terminal = ft.Container(
            height=150,
            padding=10,
            bgcolor="#0B1010",
            border_radius=8,
            content=self.runtime_hardware_log,
        )
        self.runtime_hardware_dialog = ft.AlertDialog(
            modal=True,
            bgcolor="#F8FAFD",
            title=ft.Row(
                tight=True,
                spacing=8,
                controls=[
                    ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color=PRIMARY_RED),
                    ft.Text(
                        "Hardware connection lost",
                        size=17,
                        weight=ft.FontWeight.BOLD,
                        color="#1F2A44",
                    ),
                ],
            ),
            content=ft.Container(
                width=560,
                content=ft.Column(
                    tight=True,
                    spacing=9,
                    controls=[
                        ft.Text(
                            "A device disconnected during operation. Review both device states.",
                            size=11,
                            color=MUTED,
                        ),
                        *status_rows,
                        ft.Text("Connection terminal", size=10, color=MUTED),
                        terminal,
                    ],
                ),
            ),
            actions=[
                ft.TextButton(
                    content="Continue in degraded mode",
                    on_click=lambda _: self.page.run_task(
                        self._continue_runtime_hardware_dialog
                    ),
                ),
                ft.Button(
                    content="Reconnect",
                    bgcolor="#3976D8",
                    color=ft.Colors.WHITE,
                    on_click=lambda _: self.page.run_task(
                        self._reconnect_runtime_hardware
                    ),
                ),
            ],
        )
        for key, label, port in (
            ("rfid", "RFID reader", settings.RFID_PORT),
            ("gsm", "GSM modem", settings.GSM_PORT),
        ):
            is_connected = self.reader_connected if key == "rfid" else self.sms_connected
            self._append_runtime_hardware_log(
                f"[{'CONNECTED' if is_connected else 'DISCONNECTED'}] "
                f"{label} ({port})",
                SUCCESS_GREEN if is_connected else PRIMARY_RED,
            )
        self._append_runtime_hardware_log(
            f"[EVENT] {disconnected_device} disconnected during operation",
            PRIMARY_RED,
        )
        self.page.show_dialog(self.runtime_hardware_dialog)
        self._refresh_runtime_hardware_dialog()

    def _refresh_runtime_hardware_dialog(self):
        states = {
            "rfid": self.reader_connected,
            "gsm": self.sms_connected,
        }
        for key, connected in states.items():
            state_text = self.runtime_hardware_status_controls.get(key)
            if state_text is not None:
                state_text.value = "CONNECTED" if connected else "DISCONNECTED"
                state_text.color = SUCCESS_GREEN if connected else PRIMARY_RED
        if self.runtime_hardware_dialog is not None:
            self.page.update()

    def _append_runtime_hardware_log(self, text: str, color: str):
        if self.runtime_hardware_log is None:
            return
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.runtime_hardware_log.controls.append(
            ft.Text(
                f"[{timestamp}] {text}",
                size=10,
                color=color,
                font_family="Consolas",
            )
        )
        if len(self.runtime_hardware_log.controls) > 30:
            self.runtime_hardware_log.controls.pop(0)
        try:
            self.runtime_hardware_log.update()
        except RuntimeError:
            pass

    async def _continue_runtime_hardware_dialog(self):
        self._append_runtime_hardware_log(
            "[WARN] Continuing with the unavailable device(s)",
            WARNING_YELLOW,
        )
        self._close_runtime_hardware_dialog()
        Toast.show(
            self.page,
            "Continuing in degraded mode. Missing hardware functions remain unavailable.",
            "warning",
        )

    async def _reconnect_runtime_hardware(self):
        if self.runtime_reconnect_in_progress:
            return
        self.runtime_reconnect_in_progress = True
        try:
            self._append_runtime_hardware_log(
                "[INFO] Reconnecting missing devices...",
                "#3976D8",
            )
            self.rfid_listener.stop()
            await asyncio.sleep(0.6)
            await asyncio.to_thread(self.sms_worker.stop)

            rfid = self.rfid_listener.rfid
            sms = get_sms_service()
            devices = []
            if not self.reader_connected:
                devices.append(("RFID reader", rfid))
            if not self.sms_connected:
                devices.append(("GSM modem", sms))

            results = await asyncio.gather(
                *[asyncio.to_thread(service.open) for _, service in devices],
                return_exceptions=True,
            )
            for (label, _), result in zip(devices, results):
                if isinstance(result, Exception):
                    self._append_runtime_hardware_log(
                        f"[ERROR] {label}: {result}",
                        PRIMARY_RED,
                    )
                else:
                    self._append_runtime_hardware_log(
                        f"[CONNECTED] {label}",
                        SUCCESS_GREEN,
                    )

            self.reader_connected = rfid.is_connected()
            self.sms_connected = sms.is_connected()
            if self.reader_connected:
                self.rfid_listener.rfid = rfid
                self.rfid_listener.start()
            self.sms_worker = SmsWorker(
                sms_service=sms,
                wait_for_device_reconnect=not self.sms_connected,
                on_connection_changed=self._on_sms_connection_changed,
            )
            self.sms_worker.start()
            self._refresh_runtime_hardware_dialog()
            self._refresh_mode_indicator()

            if self.reader_connected and self.sms_connected:
                self._close_runtime_hardware_dialog()
                Toast.show(
                    self.page,
                    "All real hardware devices are reconnected.",
                    "success",
                )
            else:
                self._append_runtime_hardware_log(
                    "[WARN] Missing devices remain offline. Retry or continue in degraded mode.",
                    WARNING_YELLOW,
                )
        except Exception as exc:
            logger.exception("Runtime hardware reconnect failed")
            self._append_runtime_hardware_log(
                f"[ERROR] Reconnect could not complete: {exc}",
                PRIMARY_RED,
            )
            if not self.sms_worker.is_running:
                self.sms_worker.start()
        finally:
            self.runtime_reconnect_in_progress = False

    def _close_runtime_hardware_dialog(self):
        if self.runtime_hardware_dialog is None:
            return
        self.page.pop_dialog()
        self.runtime_hardware_dialog = None
        self.runtime_hardware_log = None
        self.runtime_hardware_status_controls = {}

    def _refresh_mode_indicator(self):
        if self.developer_mode:
            label, color = "DEVELOPER MODE", "#3976D8"
        elif settings.USE_MOCK_RFID:
            label, color = (
                ("SIMULATION MODE", WARNING_YELLOW)
                if settings.USE_MOCK_SMS
                else ("MIXED MODE", WARNING_YELLOW)
            )
        elif settings.USE_MOCK_SMS:
            label, color = "MIXED MODE", WARNING_YELLOW
        elif self.reader_connected:
            label, color = (
                ("REAL HARDWARE", SUCCESS_GREEN)
                if self.sms_connected
                else ("DEGRADED MODE", WARNING_YELLOW)
            )
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
                "/mock ongoing|end|admin (or another registered card type)",
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
                str(card["type"]).upper(): str(card["uid"])
                for card in CardRepository.get_for_room(self.room_id or 1)
                if bool(card["active"])
            }
            uid_map.setdefault("ADMIN", "CARD-ADMIN-0001")
            if card_type in uid_map:
                self._terminal_output(output, f"Simulating {card_type} card tap...")
                self.close_command_console()
                self.handle_card_scan(uid_map[card_type])
            else:
                self._terminal_output(
                    output,
                    f"No active {card_type} card is registered for this room.",
                    "#F0A5B0",
                )
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

    async def _confirm_degraded_hardware_mode(self, failures: list[str]) -> bool:
        decision = asyncio.get_running_loop().create_future()

        def choose(continue_mode: bool):
            if decision.done():
                return
            self.page.pop_dialog()
            decision.set_result(continue_mode)

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                tight=True,
                spacing=8,
                controls=[
                    ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color=WARNING_YELLOW),
                    ft.Text("Some hardware is unavailable", size=18, weight=ft.FontWeight.BOLD),
                ],
            ),
            content=ft.Container(
                width=520,
                content=ft.Column(
                    tight=True,
                    spacing=10,
                    controls=[
                        ft.Text(
                            "Real hardware mode cannot use every device right now:",
                            size=12,
                            color=INK,
                        ),
                        *[
                            ft.Container(
                                padding=10,
                                bgcolor="#FFF4D6",
                                border_radius=8,
                                content=ft.Text(f"• {failure}", size=11, color="#8A5A00"),
                            )
                            for failure in failures
                        ],
                        ft.Text(
                            "If RFID is offline, cards cannot be scanned until it reconnects. "
                            "If GSM is offline, alerts remain queued locally and sending retries "
                            "when the modem reconnects.",
                            size=11,
                            color=MUTED,
                        ),
                        ft.Text(
                            "Continue in degraded real-hardware mode?",
                            size=12,
                            weight=ft.FontWeight.BOLD,
                            color=INK,
                        ),
                    ],
                ),
            ),
            actions=[
                ft.TextButton(
                    content="Cancel",
                    on_click=lambda _: choose(False),
                ),
                ft.TextButton(
                    content="Continue with unavailable device",
                    on_click=lambda _: choose(True),
                ),
            ],
        )
        self.page.show_dialog(dialog)
        return await decision

    async def _run_terminal_hardware_mode(self, output: ft.Column, enable: bool):
        desired = "Developer Mode" if enable else "Real Hardware Mode"
        self._terminal_output(output, f"Activating {desired}...", "#3976D8")
        self._terminal_output(output, "Waiting for RFID and GSM services to switch...")
        previous_rfid_mock = settings.USE_MOCK_RFID
        previous_sms_mock = settings.USE_MOCK_SMS
        previous_developer_mode = self.developer_mode
        self.rfid_listener.stop()
        await asyncio.sleep(0.6)
        await asyncio.to_thread(self.sms_worker.stop)

        try:
            await asyncio.to_thread(reset_services)
            settings.USE_MOCK_RFID = enable
            settings.USE_MOCK_SMS = enable
            rfid = get_rfid_service()
            sms = get_sms_service()
            open_results = await asyncio.gather(
                asyncio.to_thread(rfid.open),
                asyncio.to_thread(sms.open),
                return_exceptions=True,
            )
            failures = [
                f"{label}: {result}"
                for label, result in zip(("RFID reader", "GSM modem"), open_results)
                if isinstance(result, Exception)
            ]

            if failures and enable:
                raise RuntimeError("; ".join(failures))

            if failures:
                for failure in failures:
                    self._terminal_output(output, f"[WARN] {failure}", "#C48A18")
                if not await self._confirm_degraded_hardware_mode(failures):
                    self._terminal_output(
                        output,
                        "[CANCELLED] Staying in the previous operating mode.",
                        "#C48A18",
                    )
                    settings.USE_MOCK_RFID = previous_rfid_mock
                    settings.USE_MOCK_SMS = previous_sms_mock
                    await asyncio.to_thread(reset_services)
                    restored_rfid = get_rfid_service()
                    restored_sms = get_sms_service()
                    restore_results = await asyncio.gather(
                        asyncio.to_thread(restored_rfid.open),
                        asyncio.to_thread(restored_sms.open),
                        return_exceptions=True,
                    )
                    for label, restore_result in zip(
                        ("RFID", "GSM"), restore_results
                    ):
                        if isinstance(restore_result, Exception):
                            self._terminal_output(
                                output,
                                f"[WARN] Could not restore {label}: {restore_result}",
                                "#C2414B",
                            )
                    self.reader_connected = restored_rfid.is_connected()
                    self.sms_connected = restored_sms.is_connected()
                    self.rfid_listener.rfid = restored_rfid
                    self.rfid_listener.is_running = True
                    self.rfid_listener.start()
                    self.sms_worker = SmsWorker(
                        sms_service=restored_sms,
                        wait_for_device_reconnect=not self.sms_connected,
                        on_connection_changed=self._on_sms_connection_changed,
                    )
                    self.sms_worker.start()
                    self.developer_mode = previous_developer_mode
                    if self.console_refresh:
                        self.console_refresh(update_page=True)
                    return

                self._terminal_output(
                    output,
                    "[DEGRADED] Continuing; unavailable hardware will remain offline.",
                    "#C48A18",
                )

            self.reader_connected = rfid.is_connected()
            self.sms_connected = sms.is_connected()
            self.rfid_listener.rfid = rfid
            self.rfid_listener.is_running = True
            self.rfid_listener.start()
            self.sms_worker = SmsWorker(
                sms_service=sms,
                wait_for_device_reconnect=not self.sms_connected,
                on_connection_changed=self._on_sms_connection_changed,
            )
            self.sms_worker.start()
            self.developer_mode = enable

            self._terminal_output(
                output,
                (
                    f"[OK] {desired} active. RFID and GSM services are ready."
                    if not failures
                    else f"[WARN] {desired} active with {len(failures)} unavailable device(s)."
                ),
                "#16805D" if not failures else "#C48A18",
            )
            if self.console_refresh:
                self.console_refresh(update_page=True)
            if self.command_console_open and output is self.console_output_control:
                await self._force_close_dialog_async(self.console_dialog)
                logger.info("Command console closed after hardware mode activation")
                await asyncio.sleep(0.1)
            self.show_standby()
            if enable:
                self._show_simulation_reminder()
            if failures:
                Toast.show(self.page, "Real hardware mode active with unavailable device(s).", "warning")
            else:
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
                self.sms_connected = restored_sms.is_connected()
                self.sms_worker = SmsWorker(
                    sms_service=restored_sms,
                    wait_for_device_reconnect=not self.sms_connected,
                    on_connection_changed=self._on_sms_connection_changed,
                )
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
        AudioService.beep()
        if self.current_alert is not None:
            pending_uid = (getattr(self.current_alert, "card_uid", None) or "").strip()
            scan_action = getattr(self, "confirmation_scan_action", None)
            if (
                scan_action is not None
                and uid.strip().casefold() == pending_uid.casefold()
            ):
                scan_action()
            return
        scan_id = uuid4().hex
        AlertService.record_operational_event(
            EVENT_RFID_SCAN_DETECTED,
            {
                "room_id": self.room_id,
                "uid": uid,
                "scan_id": scan_id,
            },
        )
        if self.reader_monitor_auth_pending:
            try:
                is_admin = CardRepository.is_active_admin_uid(self.room_id or 1, uid)
            except Exception:
                AudioService.error()
                logger.exception("Could not verify scanned admin card")
                if self.reader_monitor_auth_status is not None:
                    self.reader_monitor_auth_status.value = (
                        "Card verification failed. Check the database and try again."
                    )
                    self.reader_monitor_auth_status.color = PRIMARY_RED
                    self.page.update()
                return
            if is_admin:
                self.reader_monitor_auth_pending = False
                self.reader_monitor_auth_dialog = None
                self.reader_monitor_auth_status = None
                self.admin_authorized = True
                self.page.pop_dialog()
                self.show_admin("Reader Monitor")
            else:
                AudioService.error()
                if self.reader_monitor_auth_status is not None:
                    self.reader_monitor_auth_status.value = (
                        "That card is not an active admin card. Scan an authorized admin card."
                    )
                    self.reader_monitor_auth_status.color = PRIMARY_RED
                    self.page.update()
            return

        if self.card_registration_session is not None:
            self._handle_card_registration_scan(uid)
            return

        if self.in_admin_mode:
            if self.current_admin_section == "Room Device":
                self._record_room_device_scan(uid)
            return

        if (
            uid == "CARD-ADMIN-0001"
            and settings.USE_MOCK_RFID
            and not CardRepository.has_active_admin_card(self.room_id or 1)
        ):
            Toast.show(self.page, "Open Settings to register your first admin card.", "warning")
            self.show_admin("Settings")
            return

        result = AlertService.scan_card(
            uid,
            scan_id=scan_id,
            kiosk_room_id=self.room_id,
        )

        if result.outcome == AlertOutcome.NEEDS_CONFIRMATION:
            self.current_alert = result
            self.show_confirmation(result)
        elif result.outcome == AlertOutcome.ADMIN_ACCESS:
            self.room_id = result.room_id or 1
            self.admin_authorized = True
            self.show_admin("Room Device")
        elif result.outcome == AlertOutcome.REJECTED_DUPLICATE:
            AudioService.error()
            Toast.show(self.page, "Card already scanned. Please wait.", "warning")
        else:
            AudioService.error()
            Toast.show(self.page, f"Unknown card: {uid}", "error")

    def show_confirmation(self, result: AlertResult):
        self._stop_standby_animations()
        self.page.views.clear()

        def on_confirm():
            self.confirmation_scan_action = None
            AlertService.record_operational_event(
                EVENT_ALERT_CONFIRMED,
                {
                    "room_id": result.room_id,
                    "card_type": card_type_value(result.card_type) if result.card_type else "",
                    "scan_id": result.scan_id,
                },
            )
            exec_result = AlertService.execute_alert(
                result.card_uid,
                result.scan_ts,
                scan_id=result.scan_id,
            )
            if exec_result.outcome == AlertOutcome.ERROR:
                Toast.show(self.page, f"Error: {exec_result.error_message}", "error")
            else:
                Toast.show(
                    self.page,
                    f"{card_type_value(result.card_type or 'ALERT')} sent to "
                    f"{exec_result.sms_queued} recipients!",
                    "success",
                )
            self.current_alert = None
            self.show_standby()

        def on_cancel():
            self.confirmation_scan_action = None
            AlertService.record_operational_event(
                EVENT_ALERT_CANCELLED,
                {
                    "room_id": result.room_id,
                    "card_type": card_type_value(result.card_type) if result.card_type else "",
                    "scan_id": result.scan_id,
                },
            )
            if hasattr(self.page, "countdown_task") and self.page.countdown_task:
                self.page.countdown_task.cancel()
            Toast.show(self.page, "Alert cancelled. No messages were sent.", "warning")
            self.current_alert = None
            self.show_standby()

        def on_timeout():
            self.confirmation_scan_action = None
            AlertService.record_operational_event(
                EVENT_CONFIRMATION_TIMEOUT,
                {
                    "room_id": result.room_id,
                    "card_type": card_type_value(result.card_type) if result.card_type else "",
                    "scan_id": result.scan_id,
                },
            )
            logger.info(
                "Confirmation timed out for card %s; no alert or SMS queued",
                result.card_uid,
            )
            self.current_alert = None
            self.show_standby()
            Toast.show(
                self.page,
                "Confirmation timed out. No alert was sent.",
                "warning",
            )

        self.page.views.append(
            build_confirmation_screen(
                self.page,
                result,
                on_confirm,
                on_cancel,
                on_timeout,
                lambda action: setattr(self, "confirmation_scan_action", action),
            )
        )
        AlertService.record_operational_event(
            EVENT_CONFIRMATION_SHOWN,
            {
                "room_id": result.room_id,
                "card_type": card_type_value(result.card_type) if result.card_type else "",
                "scan_id": result.scan_id,
            },
        )
        self.page.update()

    # ==========================================
    # ADMIN FLOW (SPA)
    # ==========================================

    def show_admin(self, section: str = "Room Device"):
        self.in_admin_mode = True
        self.rfid_listener.stop()
        self._stop_standby_animations()
        self.room_device_scan_test_armed = False
        if section != "Room Device":
            self.room_device_controls = {}

        if hasattr(self.page, "countdown_task") and self.page.countdown_task:
            try:
                self.page.countdown_task.cancel()
            except Exception:
                pass

        # Build the initial view (returns a View with the shell + content)
        view = self._build_view(section)

        self.body_host = self._admin_body_host(view)
        self.current_admin_section = section
        self.page.views.clear()
        self.page.views.append(view)
        self.page.update()
        if section in ("Room Device", "Settings"):
            self.page.run_task(self._start_room_device_listener)

    @staticmethod
    def _admin_body_host(view: ft.View) -> Optional[ft.Container]:
        try:
            return view.controls[0].controls[1].controls[1]
        except (AttributeError, IndexError):
            return None

    async def _start_room_device_listener(self):
        await asyncio.sleep(0.6)
        if (
            self.in_admin_mode
            and self.current_admin_section in ("Room Device", "Settings")
            and self.reader_monitor is None
            and not self.rfid_listener.is_running
        ):
            self.rfid_listener.start()

    def show_reader_monitor(self):
        room_id = self.room_id or 1
        try:
            has_admin_card = CardRepository.has_active_admin_card(room_id)
        except Exception as exc:
            logger.exception("Could not verify reader-monitor admin access")
            Toast.show(self.page, f"Could not verify admin card: {exc}", "error")
            return

        if not has_admin_card:
            Toast.show(
                self.page,
                "No admin card is registered. Settings opened for first-time enrollment.",
                "warning",
            )
            self.show_admin("Settings")
            return

        self.reader_monitor_auth_pending = True
        self.reader_monitor_auth_status = ft.Text(
            "Scan an active ADMIN card to open Reader Monitor.",
            size=11,
            color=MUTED,
        )

        def cancel(_event=None) -> None:
            self.reader_monitor_auth_pending = False
            self.reader_monitor_auth_dialog = None
            self.reader_monitor_auth_status = None
            self.page.pop_dialog()
            if self.in_admin_mode and self.page.views:
                set_active_admin_navigation(
                    self.page.views[-1],
                    self.current_admin_section,
                )

        self.reader_monitor_auth_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Admin verification", weight=ft.FontWeight.BOLD),
            content=ft.Container(
                width=380,
                content=ft.Column(
                    tight=True,
                    spacing=10,
                    controls=[
                        ft.Icon(ft.Icons.ADMIN_PANEL_SETTINGS, size=34, color=PRIMARY_RED),
                        self.reader_monitor_auth_status,
                    ],
                ),
            ),
            actions=[
                ft.TextButton(content="Cancel", on_click=cancel),
            ],
        )
        self.page.show_dialog(self.reader_monitor_auth_dialog)

    def _begin_card_registration(self, card_type_value: str) -> None:
        if not self.in_admin_mode or self.current_admin_section != "Settings":
            Toast.show(self.page, "Open Settings before registering a card.", "warning")
            return
        card_type = card_type_value.strip().upper()
        if (
            card_type != CardType.ADMIN.value
            and card_type not in CardCategoryRepository.get_active()
        ):
            Toast.show(self.page, f"Unsupported card type: {card_type_value}", "error")
            return

        status = ft.Text(
            f"Scan the card to register as {card_type}.",
            size=11,
            color=INK,
        )
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"Register {card_type.title()} Card", weight=ft.FontWeight.BOLD),
            content=ft.Container(
                width=420,
                content=ft.Column(
                    tight=True,
                    spacing=10,
                    controls=[
                        ft.Row(
                            spacing=8,
                            controls=[
                                ft.Icon(ft.Icons.CONTACTLESS, color=PRIMARY_RED),
                                ft.Text(
                                    "Card enrollment · Step 1 of 3",
                                    size=11,
                                    weight=ft.FontWeight.W_600,
                                    color=MUTED,
                                ),
                            ],
                        ),
                        status,
                    ],
                ),
            ),
            actions=[
                ft.TextButton(
                    content="Cancel",
                    on_click=lambda _: self._cancel_card_registration(),
                )
            ],
        )
        self.card_registration_session = {
            "card_type": card_type,
            "stage": "scan_first",
            "first_uid": None,
            "status": status,
            "dialog": dialog,
        }
        self.page.show_dialog(dialog)

    def _cancel_card_registration(self) -> None:
        self.card_registration_session = None
        self.page.pop_dialog()

    def _handle_card_registration_scan(self, uid: str) -> None:
        session = self.card_registration_session
        if session is None:
            return

        status = session["status"]
        dialog = session["dialog"]
        stage = str(session["stage"])
        if stage == "scan_first":
            session["first_uid"] = uid
            session["stage"] = "confirm_first"
            status.value = (
                f"Detected UID {uid} for {session['card_type']}. Confirm this assignment, "
                "then scan the same card again."
            )
            dialog.content.content.controls[0].controls[1].value = "Card enrollment · Step 2 of 3"
            dialog.actions = [
                ft.TextButton(
                    content="Cancel",
                    on_click=lambda _: self._cancel_card_registration(),
                ),
                ft.Button(
                    content="Confirm and Scan Again",
                    on_click=self._confirm_card_registration_scan,
                ),
            ]
        elif stage == "scan_second":
            if uid != session["first_uid"]:
                AudioService.error()
                status.value = (
                    "The second scan did not match. Scan the same card again to continue."
                )
                status.color = PRIMARY_RED
                self.page.update()
                return
            session["stage"] = "ready"
            status.value = (
                f"Both scans match ({uid}). Review the {session['card_type']} assignment "
                "and save it to the database."
            )
            status.color = SUCCESS_GREEN
            dialog.content.content.controls[0].controls[1].value = "Card enrollment · Step 3 of 3"
            dialog.actions = [
                ft.TextButton(
                    content="Cancel",
                    on_click=lambda _: self._cancel_card_registration(),
                ),
                ft.Button(
                    content="Save Card",
                    icon=ft.Icons.SAVE_OUTLINED,
                    on_click=self._save_registered_card,
                ),
            ]
        self.page.update()

    def _confirm_card_registration_scan(self, _event=None) -> None:
        session = self.card_registration_session
        if session is None or session["stage"] != "confirm_first":
            return
        session["stage"] = "scan_second"
        status = session["status"]
        status.value = "Scan the same card a second time to verify the UID before saving."
        status.color = INK
        session["dialog"].content.content.controls[0].controls[1].value = (
            "Card enrollment · Step 2 of 3"
        )
        session["dialog"].actions = [
            ft.TextButton(
                content="Cancel",
                on_click=lambda _: self._cancel_card_registration(),
            )
        ]
        self.page.update()

    async def _save_registered_card(self, _event=None) -> None:
        session = self.card_registration_session
        if session is None or session["stage"] != "ready":
            return
        try:
            await asyncio.to_thread(
                CardRepository.register,
                self.room_id or 1,
                str(session["first_uid"]),
                session["card_type"],
            )
        except Exception as exc:
            logger.exception("Could not register RFID card")
            Toast.show(self.page, f"Could not register card: {exc}", "error")
            return

        self.card_registration_session = None
        self.page.pop_dialog()
        Toast.show(self.page, "Card registered and saved.", "success")
        self._refresh_admin_content("Settings")

    def _build_view(self, section: str) -> ft.View:
        """Builds the full view (shell + content) for a given section."""
        # Rebuilding the view each time is fine because we swap the body_host,
        # not replace the whole view in page.views
        if section == "Reader Monitor":
            rfid = get_rfid_service()
            rfid.close()
            self.reader_connected = rfid.is_connected()
            self.reader_monitor = ReaderMonitor(self.page)
            return self.reader_monitor.build(
                self.room_id or 1, self._navigate_admin, self.exit_admin,
            )
        if self.reader_monitor is not None:
            self.reader_monitor.dispose()
            self.reader_monitor = None
        if section == "Alert History":
            return build_alert_history(self.page, self.room_id, self._navigate_admin, self.exit_admin)
        elif section == "Emergency Report":
            return build_operational_report(
                self.page,
                self.room_id or 1,
                self._navigate_admin,
                self.exit_admin,
            )
        elif section == "Settings":
            return build_settings(
                self.page,
                self.room_id or 1,
                self._navigate_admin,
                self.exit_admin,
                on_register_card=self._begin_card_registration,
                on_card_updated=lambda: self._refresh_admin_content("Settings"),
            )
        else:
            return build_room_device(
                self.page,
                self.room_id,
                self._navigate_admin,
                self.exit_admin,
                reader_connected=self.reader_connected,
                reader_port=settings.RFID_PORT,
                last_scan_at=self.last_room_scan_at,
                last_scan_uid=self.last_room_scan_uid,
                on_scan_test=self._start_room_device_scan_test,
                on_restart_reader=self._restart_room_device_reader,
                on_disconnect_reader=self._disconnect_room_device_reader,
                on_reconnect_reader=self._reconnect_room_device_reader,
                on_diagnostics=self._show_room_device_diagnostics,
                on_room_updated=lambda: self._refresh_admin_content("Room Device"),
                register_controls=self._register_room_device_controls,
            )

    def _refresh_admin_content(self, section: str):
        if self.body_host is None:
            logger.error("Cannot refresh %s because the admin content host is missing", section)
            return

        view = self._build_view(section)
        body_host = self._admin_body_host(view)
        if body_host is None:
            logger.error("Cannot refresh %s because its content host could not be built", section)
            return

        self.body_host.content = body_host.content
        self.current_admin_section = section
        self.page.update()

    def _navigate_admin(self, section: str):
        if section == "Main Kiosk":
            self.exit_admin()
            return
        if section == "Reader Monitor" and not self.admin_authorized:
            self.show_reader_monitor()
            return

        # If section is the same as current, do nothing
        if section == self.current_admin_section:
            return

        if section not in ("Room Device", "Settings"):
            self.rfid_listener.stop()
            self.room_device_scan_test_armed = False

        if self.reader_monitor is not None:
            self.reader_monitor.dispose()
            self.reader_monitor = None

        # If we somehow lost body_host, fall back to full reload
        if not self.body_host:
            self.show_admin(section)
            return

        self.page.run_task(self._transition_admin, section)

    async def _transition_admin(self, section: str):
        if self.page.views:
            set_active_admin_navigation(self.page.views[-1], section)

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

        # Build the next screen and move only its content into the existing shell.
        new_view = self._build_view(section)
        new_body_host = self._admin_body_host(new_view)
        self.body_host.content = (
            new_body_host.content if new_body_host is not None else ft.Container()
        )
        self.current_admin_section = section
        if section != "Room Device":
            self.room_device_controls = {}
        self.page.update()
        await asyncio.sleep(0.1)
        self.body_host.opacity = 1
        self.page.update()
        if section in ("Room Device", "Settings"):
            self.page.run_task(self._start_room_device_listener)

    def _build_skeleton(self, title: str) -> ft.Control:
        return ft.Container(
            height=112,
            alignment=ft.Alignment.CENTER,
            bgcolor=CARD_WHITE,
            border=ft.Border.all(1, BORDER_COLOR),
            border_radius=12,
            content=ft.Row(
                tight=True,
                spacing=10,
                alignment=ft.MainAxisAlignment.CENTER,
                controls=[
                    ft.ProgressRing(
                        value=None,
                        width=18,
                        height=18,
                        color=PRIMARY_RED,
                        stroke_width=2,
                    ),
                    ft.Text(f"Loading {title}...", size=12, color=MUTED),
                ],
            ),
        )

    def exit_admin(self):
        self.in_admin_mode = False
        self.admin_authorized = False
        self.body_host = None
        self.room_device_controls = {}
        self.room_device_scan_test_armed = False
        if self.reader_monitor is not None:
            self.reader_monitor.dispose()
            self.reader_monitor = None
        self.rfid_listener.start()
        self.show_standby()