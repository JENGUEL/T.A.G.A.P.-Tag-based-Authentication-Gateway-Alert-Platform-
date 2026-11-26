"""
T.A.G.A.P. - Real RFID Adapter (Serial)

Reads UID lines from the TAGAP Arduino/RC522 serial protocol.

The adapter discovers USB serial candidates, sends a TAGAP ping, and keeps
only the port that reports the RC522-ready handshake.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from typing import Optional

import serial
from serial.tools import list_ports

from config import settings
from core.exceptions import RfidConnectionError, RfidReadError
from services.interfaces import IRfidService

logger = logging.getLogger(__name__)

READER_READY = "TAGAP_READER/1;RC522=OK"
READER_ERROR = "TAGAP_READER/1;RC522=ERROR"
PING_COMMAND = b"TAGAP_PING\n"
UID_PATTERN = re.compile(r"(?:UID:)?([0-9A-Fa-f]{8}|[0-9A-Fa-f]{14}|[0-9A-Fa-f]{20})")


class SerialRfidService(IRfidService):
    def __init__(
        self,
        port: str,
        baudrate: int = 9600,
        excluded_ports: tuple[str, ...] = (),
    ) -> None:
        self._port = port
        self._baudrate = baudrate
        self._excluded_ports = {self._normalize_port(value) for value in excluded_ports}
        self._serial: Optional[serial.Serial] = None
        self._lock = threading.Lock()

    # --- Lifecycle ---

    def open(self) -> None:
        if self.is_connected():
            return

        candidates = self._candidate_ports()
        failures: list[str] = []
        for port in candidates:
            connection: Optional[serial.Serial] = None
            try:
                connection = serial.Serial(
                    port=port,
                    baudrate=self._baudrate,
                    timeout=0.25,
                    write_timeout=0.5,
                )
                # Opening an Uno serial port resets the board; allow its bootloader to finish.
                time.sleep(2.0)
                connection.reset_input_buffer()
                connection.write(PING_COMMAND)
                connection.flush()
                deadline = time.monotonic() + 2.0
                while time.monotonic() < deadline:
                    response = connection.readline().decode("ascii", errors="ignore").strip()
                    if response == READER_READY:
                        self._serial = connection
                        self._port = port
                        settings.RFID_PORT = port
                        logger.info("TAGAP RC522 reader verified on %s @ %d", port, self._baudrate)
                        return
                    if response == READER_ERROR:
                        failures.append(f"{port}: Arduino found, RC522 not responding")
                        break
                else:
                    failures.append(f"{port}: no TAGAP reader handshake")
            except (serial.SerialException, OSError, ValueError) as exc:
                failures.append(f"{port}: {exc}")
            finally:
                if connection is not None and connection is not self._serial and connection.is_open:
                    connection.close()

        tried = ", ".join(candidates) if candidates else "no eligible USB serial ports"
        detail = "; ".join(failures)
        message = f"TAGAP RC522 reader not detected ({tried})"
        if detail:
            message = f"{message}: {detail}"
        raise RfidConnectionError(message)

    @staticmethod
    def _normalize_port(port: str) -> str:
        return port.strip().upper()

    def _candidate_ports(self) -> list[str]:
        discovered = list(list_ports.comports())
        available = {self._normalize_port(item.device): item for item in discovered}
        configured = self._normalize_port(self._port)
        candidates: list[str] = []

        configured_info = available.get(configured)
        if (
            configured_info is not None
            and configured_info.vid is not None
            and configured not in self._excluded_ports
        ):
            candidates.append(configured_info.device)

        for item in discovered:
            normalized = self._normalize_port(item.device)
            if normalized in self._excluded_ports or normalized == configured:
                continue
            if item.vid is not None:
                candidates.append(item.device)
        return candidates

    def close(self) -> None:
        with self._lock:
            connection = self._serial
            self._serial = None
            if connection and connection.is_open:
                connection.close()
        logger.info("SerialRfidService closed")

    def is_connected(self) -> bool:
        return bool(self._serial and self._serial.is_open)

    # --- Core contract ---

    def read_card(self, timeout_seconds: float = 1.0) -> Optional[str]:
        if not self.is_connected():
            raise RfidConnectionError("RFID serial port is not open")

        deadline = timeout_seconds
        with self._lock:
            self._serial.timeout = deadline
            try:
                raw = self._serial.readline()
            except serial.SerialException as exc:
                raise RfidReadError(f"Serial read failed: {exc}") from exc

        if not raw:
            return None

        uid = self._parse_line(raw)
        if uid:
            logger.info("SerialRfidService read UID: %s", uid)
        return uid

    # --- Protocol ---

    @staticmethod
    def _parse_line(raw: bytes) -> Optional[str]:
        text = raw.decode("ascii", errors="ignore").strip()
        match = UID_PATTERN.fullmatch(text)
        if not match:
            return None
        return match.group(1).upper()