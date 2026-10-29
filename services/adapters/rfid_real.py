"""
T.A.G.A.P. - Real RFID Adapter (Serial)

Reads card UIDs from a serial-attached RFID reader (e.g., RC522
via USB-serial bridge, or PN532 in UART mode).

Protocol assumption:
- The reader emits the card UID as an ASCII line terminated with \r\n.
- If your reader uses a different protocol, adjust `_parse_line()` only.
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

import serial

from core.exceptions import RfidConnectionError, RfidReadError
from services.interfaces import IRfidService

logger = logging.getLogger(__name__)


class SerialRfidService(IRfidService):
    def __init__(self, port: str, baudrate: int = 9600) -> None:
        self._port = port
        self._baudrate = baudrate
        self._serial: Optional[serial.Serial] = None
        self._lock = threading.Lock()

    # --- Lifecycle ---

    def open(self) -> None:
        try:
            self._serial = serial.Serial(
                port=self._port,
                baudrate=self._baudrate,
                timeout=0.1,
            )
            logger.info("SerialRfidService opened on %s @ %d", self._port, self._baudrate)
        except serial.SerialException as exc:
            raise RfidConnectionError(
                f"Cannot open RFID port {self._port}: {exc}"
            ) from exc

    def close(self) -> None:
        with self._lock:
            if self._serial and self._serial.is_open:
                self._serial.close()
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
        try:
            text = raw.decode("ascii", errors="ignore").strip()
        except Exception:
            return None
        if not text:
            return None
        # Adjust this filter to match your reader's output
        return text