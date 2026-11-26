"""Serial terminal for testing the Arduino-connected RC522 reader."""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import Future
from datetime import datetime
from typing import Callable, Optional

import flet as ft
import serial

from config import settings
from data import queries
from services.adapters.rfid_real import READER_ERROR, READER_READY, PING_COMMAND
from ui.screens.admin.shell import build_admin_shell
from ui.theme import BORDER_COLOR, CARD_WHITE, INK, MUTED, SUCCESS_GREEN

logger = logging.getLogger(__name__)


class ReaderMonitor:
    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self._serial: Optional[serial.Serial] = None
        self._read_task: Optional[Future[None]] = None
        self._handshake_event: Optional[asyncio.Event] = None
        self._connection_generation = 0
        self.reader_verified = False
        self._output_lines: list[ft.Text] = []

        self.port_field = ft.TextField(
            label="Serial port",
            value=settings.RFID_PORT,
            width=190,
            dense=True,
        )
        self.baud_field = ft.TextField(
            label="Baud rate",
            value=str(settings.RFID_BAUDRATE),
            width=150,
            dense=True,
        )
        self.status_text = ft.Text("Disconnected", size=11, color=MUTED)
        self.activity_text = ft.Text("", size=10, color="#F6C177", font_family="Consolas")
        self.activity_panel = ft.Container(
            visible=False,
            padding=ft.Padding.symmetric(horizontal=8, vertical=4),
            content=ft.Row(
                tight=True,
                spacing=8,
                controls=[
                    ft.ProgressRing(width=15, height=15, stroke_width=2, color="#F6C177"),
                    self.activity_text,
                ],
            ),
        )
        self.output = ft.Column(
            expand=True,
            spacing=5,
            scroll=ft.ScrollMode.AUTO,
            auto_scroll=True,
        )
        self.connect_button = ft.TextButton(
            content="Connect",
            icon=ft.Icons.PLAY_ARROW,
            on_click=self.connect,
        )
        self.clear_button = ft.TextButton(
            content="Clear",
            icon=ft.Icons.DELETE_OUTLINE,
            on_click=self.clear_output,
        )

    def build(self, room_id: int, on_navigate: Callable, on_exit: Callable) -> ft.View:
        info = queries.get_room_info(room_id)
        content = ft.Column(
            expand=True,
            spacing=16,
            controls=[
                ft.Column(
                    tight=True,
                    spacing=3,
                    controls=[
                        ft.Text("RFID Reader Monitor", size=24, weight=ft.FontWeight.BOLD, color=INK),
                        ft.Text(
                            "Connect to the Arduino serial port and scan a card to verify its UID.",
                            size=11,
                            color=MUTED,
                        ),
                    ],
                ),
                ft.Container(
                    padding=ft.Padding.all(16),
                    bgcolor=CARD_WHITE,
                    border=ft.Border.all(1, BORDER_COLOR),
                    border_radius=10,
                    content=ft.Row(
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            self.port_field,
                            self.baud_field,
                            self.connect_button,
                            self.clear_button,
                            ft.Container(expand=True),
                            self.status_text,
                        ],
                    ),
                ),
                ft.Container(
                    expand=True,
                    padding=ft.Padding.all(14),
                    bgcolor="#15191E",
                    border_radius=10,
                    content=ft.Column(
                        expand=True,
                        spacing=8,
                        controls=[
                            ft.Row(
                                controls=[
                                    ft.Text("TAGAP SERIAL TERMINAL", size=10, color="#AAB4BE",
                                            font_family="Consolas", weight=ft.FontWeight.BOLD),
                                    ft.Container(expand=True),
                                    ft.Text("ASCII UID · one line per scan", size=10, color="#77828D",
                                            font_family="Consolas"),
                                ],
                            ),
                            ft.Divider(height=1, color="#343B43"),
                            self.activity_panel,
                            self.output,
                        ],
                    ),
                ),
                ft.Text(
                    "Close Arduino IDE Serial Monitor before connecting; a serial port can only be used by one app at a time.",
                    size=10,
                    color=MUTED,
                ),
            ],
        )
        self._append_line("Waiting for serial connection...", "#AAB4BE")
        return build_admin_shell(
            self.page,
            active_page="Reader Monitor",
            room_name=info.get("room_name", "Room"),
            on_navigate=on_navigate,
            on_back_to_kiosk=on_exit,
            content=content,
        )

    async def connect(self, _event) -> None:
        if self._serial and self._serial.is_open:
            await self.disconnect()
            return

        port = (self.port_field.value or "").strip()
        baud_text = (self.baud_field.value or "").strip()
        if not port:
            self._append_line("ERROR: Enter the Arduino serial port (for example, COM3).", "#F28B82")
            return
        try:
            baudrate = int(baud_text)
            if baudrate <= 0:
                raise ValueError("baud rate must be positive")
        except ValueError as exc:
            self._append_line(f"ERROR: Invalid baud rate: {exc}", "#F28B82")
            return

        self._connection_generation += 1
        generation = self._connection_generation
        self.reader_verified = False
        self._start_activity(f"Opening {port} at {baudrate} baud...")
        self._append_line(f"CONNECT  {port} @ {baudrate}", "#AAB4BE")
        self.connect_button.disabled = True
        self.status_text.value = f"Connecting to {port}..."
        self.status_text.color = MUTED
        self.page.update()
        try:
            connection = await asyncio.to_thread(
                serial.Serial,
                port=port,
                baudrate=baudrate,
                timeout=0.25,
            )
        except (serial.SerialException, OSError, ValueError) as exc:
            if generation != self._connection_generation:
                return
            self._stop_activity()
            self._append_line(f"ERROR: Could not open {port}: {exc}", "#F28B82")
            self.status_text.value = "Disconnected"
            self.connect_button.content = "Connect"
            self.connect_button.icon = ft.Icons.PLAY_ARROW
            self.connect_button.disabled = False
            self.page.update()
            return

        if generation != self._connection_generation:
            await asyncio.to_thread(connection.close)
            return
        self._serial = connection
        self.status_text.value = f"Connected · {port} @ {baudrate}"
        self.status_text.color = SUCCESS_GREEN
        self.connect_button.content = "Disconnect"
        self.connect_button.icon = ft.Icons.STOP
        self.connect_button.disabled = False
        self._append_line(f"PORT OPEN  {port} @ {baudrate}", "#81C995")
        self._start_activity("Waiting for Arduino reboot...")
        self.page.update()
        # Opening an Uno serial port commonly resets the board.
        await asyncio.sleep(2)
        if generation != self._connection_generation or self._serial is not connection:
            return

        handshake_event = asyncio.Event()
        self._handshake_event = handshake_event
        try:
            self._start_activity("Sending TAGAP_PING; checking Arduino and RC522...")
            await asyncio.to_thread(self._write_ping, connection)
        except (serial.SerialException, OSError) as exc:
            if self._serial is connection:
                self._stop_activity()
                self._append_line(f"ERROR: Could not send handshake: {exc}", "#F28B82")
                self.status_text.value = "Handshake request failed"
                self.status_text.color = "#F28B82"
                self.page.update()
            return

        if self._serial is not connection:
            return
        self._append_line("PING SENT  Waiting for Arduino/RC522 response...", "#F6C177")
        self.page.update()
        self._read_task = self.page.run_task(self._read_loop, connection)
        try:
            await asyncio.wait_for(handshake_event.wait(), timeout=3.0)
        except asyncio.TimeoutError:
            if self._serial is connection:
                self._stop_activity()
                self._append_line(
                    "TIMEOUT  No handshake. Check firmware, 9600 baud, Newline, and COM-port ownership.",
                    "#F28B82",
                )
                self.status_text.value = "Arduino connected · handshake not verified"
                self.status_text.color = "#F28B82"
                self.page.update()

    def _start_activity(self, message: str) -> None:
        self.activity_text.value = message
        self.activity_panel.visible = True
        try:
            self.activity_panel.update()
        except RuntimeError:
            pass

    def _stop_activity(self) -> None:
        self.activity_panel.visible = False
        try:
            self.activity_panel.update()
        except RuntimeError:
            pass

    @staticmethod
    def _write_ping(connection: serial.Serial) -> None:
        connection.write(PING_COMMAND)
        connection.flush()

    async def disconnect(self) -> None:
        self._connection_generation += 1
        connection = self._serial
        self._serial = None
        if self._handshake_event is not None:
            self._handshake_event.set()
            self._handshake_event = None
        if self._read_task is not None:
            self._read_task.cancel()
            self._read_task = None
        if connection and connection.is_open:
            self.connect_button.disabled = True
            self._start_activity("Closing serial connection...")
            self._append_line("DISCONNECT  Closing serial port...", "#AAB4BE")
            self.page.update()
            await asyncio.to_thread(connection.close)
        self._stop_activity()
        self.status_text.value = "Disconnected"
        self.status_text.color = MUTED
        self.connect_button.content = "Connect"
        self.connect_button.icon = ft.Icons.PLAY_ARROW
        self.connect_button.disabled = False
        self._append_line("Disconnected.", "#AAB4BE")
        self.page.update()

    def dispose(self) -> None:
        self._connection_generation += 1
        connection = self._serial
        self._serial = None
        if self._handshake_event is not None:
            self._handshake_event.set()
            self._handshake_event = None
        if self._read_task is not None:
            self._read_task.cancel()
            self._read_task = None
        if connection and connection.is_open:
            connection.close()

    async def _read_loop(self, connection: serial.Serial) -> None:
        while connection and self._serial is connection and connection.is_open:
            try:
                raw = await asyncio.to_thread(connection.readline)
            except serial.SerialException as exc:
                if self._serial is not connection:
                    return
                logger.error("RFID monitor serial read failed: %s", exc)
                self._stop_activity()
                if self._handshake_event is not None:
                    self._handshake_event.set()
                    self._handshake_event = None
                self._append_line(f"ERROR: Serial read failed: {exc}", "#F28B82")
                self._serial = None
                self._read_task = None
                self.status_text.value = "Connection lost"
                self.status_text.color = "#F28B82"
                self.connect_button.content = "Connect"
                self.connect_button.icon = ft.Icons.PLAY_ARROW
                self.connect_button.disabled = False
                self.page.update()
                return

            uid = raw.decode("ascii", errors="ignore").strip()
            if uid:
                if uid == READER_READY:
                    self.reader_verified = True
                    if self._handshake_event is not None:
                        self._handshake_event.set()
                        self._handshake_event = None
                    self._stop_activity()
                    self._append_line("HANDSHAKE OK · Arduino and RC522 verified.", "#81C995")
                    self.status_text.value = f"Reader verified · {connection.port}"
                    self.status_text.color = SUCCESS_GREEN
                elif uid == READER_ERROR:
                    if self._handshake_event is not None:
                        self._handshake_event.set()
                        self._handshake_event = None
                    self._stop_activity()
                    self._append_line("Arduino found, but RC522 is not responding.", "#F28B82")
                    self.status_text.value = "RC522 not responding"
                    self.status_text.color = "#F28B82"
                elif uid.startswith("UID:"):
                    self._append_line(f"UID > {uid[4:]}", "#81C995")
                else:
                    self._append_line(f"SERIAL > {uid}", "#AAB4BE")
                self.page.update()

    async def clear_output(self, _event) -> None:
        self._start_activity("Clearing terminal history...")
        await asyncio.sleep(0.15)
        self._output_lines.clear()
        self.output.controls.clear()
        self._append_line("Terminal cleared.", "#AAB4BE")
        self._stop_activity()
        self.page.update()

    def _append_line(self, text: str, color: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = ft.Text(f"[{timestamp}] {text}", size=11, color=color, font_family="Consolas")
        self._output_lines.append(line)
        self.output.controls.append(line)
        if len(self._output_lines) > 200:
            self._output_lines.pop(0)
            self.output.controls.pop(0)
