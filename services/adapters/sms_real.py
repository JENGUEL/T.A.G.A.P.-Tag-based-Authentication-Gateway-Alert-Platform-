"""
T.A.G.A.P. - Real SMS Adapter (SIM800 via AT Commands)

Sends SMS through a SIM800 / SIM800L / SIM7600 GSM module over USB-serial.

Key behaviors:
- AT handshake on `open()`.
- Per-message timeout.
- Handles "ERROR" / "NO CARRIER" / missing "OK" responses.
- Parses "+CMGS: <id>" as delivery acknowledgement.
- Never raises on normal send failures (returns SmsResult(success=False)).
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

import serial

from core.exceptions import GsmConnectionError
from services.interfaces import ISmsService, SmsResult

logger = logging.getLogger(__name__)


class Sim800SmsService(ISmsService):
    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        *,
        timeout_seconds: int = 5,
    ) -> None:
        self._port = port
        self._baudrate = baudrate
        self._timeout = timeout_seconds
        self._serial: Optional[serial.Serial] = None
        self._lock = threading.Lock()

    # --- Lifecycle ---

    def open(self) -> None:
        try:
            self._serial = serial.Serial(
                port=self._port,
                baudrate=self._baudrate,
                timeout=1,
            )
        except serial.SerialException as exc:
            raise GsmConnectionError(
                f"Cannot open GSM port {self._port}: {exc}"
            ) from exc

        # AT handshake
        if not self._at_ok("AT"):
            raise GsmConnectionError("GSM module did not respond to AT")
        if not self._at_ok("AT+CMGF=1"):
            raise GsmConnectionError("GSM module failed to enter text mode")
        logger.info("Sim800SmsService opened on %s", self._port)

    def close(self) -> None:
        with self._lock:
            if self._serial and self._serial.is_open:
                self._serial.close()
        logger.info("Sim800SmsService closed")

    def is_connected(self) -> bool:
        return bool(self._serial and self._serial.is_open)

    # --- Core contract ---

    def send_sms(self, phone_number: str, message: str) -> SmsResult:
        if not self.is_connected():
            raise GsmConnectionError("GSM serial port is not open")

        with self._lock:
            try:
                # 1. Set recipient
                self._write_line(f'AT+CMGS="{phone_number}"')
                time.sleep(0.5)

                # 2. Send body + Ctrl-Z
                self._serial.write(message.encode("utf-8") + b"\x1a")

                # 3. Read response
                deadline = time.time() + self._timeout
                response = ""
                while time.time() < deadline:
                    line = self._serial.readline().decode("utf-8", errors="ignore")
                    if line:
                        response += line
                    if "+CMGS:" in response or "ERROR" in response:
                        break
                    time.sleep(0.05)
            except serial.SerialException as exc:
                logger.exception("GSM serial error")
                return SmsResult(
                    success=False,
                    phone_number=phone_number,
                    message=message,
                    reason=f"serial error: {exc}",
                )

        if "+CMGS:" in response:
            logger.info("SMS delivered to %s", phone_number)
            return SmsResult(
                success=True,
                phone_number=phone_number,
                message=message,
                raw_response=response.strip(),
            )

        reason = "no acknowledgement"
        if "ERROR" in response:
            reason = "modem returned ERROR"
        logger.warning("SMS FAILED to %s: %s | response=%r", phone_number, reason, response)
        return SmsResult(
            success=False,
            phone_number=phone_number,
            message=message,
            reason=reason,
            raw_response=response.strip(),
        )

    def signal_strength(self) -> Optional[int]:
        if not self.is_connected():
            return None
        try:
            response = self._at_query("AT+CSQ")
        except Exception:
            return None
        # Response: +CSQ: <rssi>,<ber>
        marker = "+CSQ:"
        if marker not in response:
            return None
        try:
            payload = response.split(marker, 1)[1].strip()
            rssi_str = payload.split(",")[0].strip()
            return int(rssi_str)
        except (ValueError, IndexError):
            return None

    # --- AT helpers ---

    def _write_line(self, line: str) -> None:
        self._serial.write((line + "\r").encode("ascii"))

    def _at_ok(self, cmd: str, wait: float = 2.0) -> bool:
        self._write_line(cmd)
        deadline = time.time() + wait
        buffer = ""
        while time.time() < deadline:
            line = self._serial.readline().decode("utf-8", errors="ignore")
            buffer += line
            if "OK" in buffer:
                return True
            if "ERROR" in buffer:
                return False
        return False

    def _at_query(self, cmd: str, wait: float = 2.0) -> str:
        self._write_line(cmd)
        deadline = time.time() + wait
        buffer = ""
        while time.time() < deadline:
            line = self._serial.readline().decode("utf-8", errors="ignore")
            buffer += line
            if "OK" in buffer or "ERROR" in buffer:
                return buffer
        return buffer