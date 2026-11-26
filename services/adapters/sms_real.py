"""
T.A.G.A.P. - Real SMS Adapter (SIM800 via AT Commands)

Sends SMS through a SIM800 / SIM800L / SIM7600 GSM module over USB-serial.

Key behaviors:
- AT handshake on `open()`.
- PDU mode with UCS-2 multipart support for long SMS templates.
- Per-message timeout.
- Handles "ERROR" / "NO CARRIER" / missing "OK" responses.
- Parses "+CMGS: <id>" as delivery acknowledgement.
- Never raises on normal send failures (returns SmsResult(success=False)).
"""

from __future__ import annotations

import logging
import re
import secrets
import threading
import time
from typing import Optional

import serial
from serial.tools import list_ports

from core.exceptions import GsmConnectionError
from services.interfaces import ISmsService, SmsResult

logger = logging.getLogger(__name__)

_UCS2_SINGLE_PART_UNITS = 70
_UCS2_MULTIPART_UNITS = 67
_MAX_SMS_PARTS = 255


def _ucs2_parts(message: str) -> list[bytes]:
    if not message:
        raise ValueError("SMS message cannot be empty.")

    encoded_chars = [character.encode("utf-16-be") for character in message]
    total_units = sum(len(character) // 2 for character in encoded_chars)
    if total_units <= _UCS2_SINGLE_PART_UNITS:
        return [b"".join(encoded_chars)]

    parts: list[bytes] = []
    current_part = bytearray()
    current_units = 0
    for encoded_character in encoded_chars:
        character_units = len(encoded_character) // 2
        if current_units + character_units > _UCS2_MULTIPART_UNITS:
            parts.append(bytes(current_part))
            current_part.clear()
            current_units = 0
        current_part.extend(encoded_character)
        current_units += character_units
    if current_part:
        parts.append(bytes(current_part))
    if len(parts) > _MAX_SMS_PARTS:
        raise ValueError(f"SMS message exceeds {_MAX_SMS_PARTS} parts.")
    return parts


def _semi_octet_address(phone_number: str) -> tuple[int, int, bytes]:
    phone_number = phone_number.strip()
    if not re.fullmatch(r"\+?[\d ()-]+", phone_number):
        raise ValueError("Phone number contains unsupported characters.")

    international = phone_number.startswith("+") or phone_number.startswith("00")
    digits = "".join(
        character for character in phone_number if character in "0123456789"
    )
    if phone_number.startswith("00"):
        digits = digits[2:]
    if not digits or len(digits) > 20:
        raise ValueError("Phone number must contain between 1 and 20 digits.")

    semi_octets = bytearray()
    for index in range(0, len(digits), 2):
        pair = digits[index:index + 2]
        if len(pair) == 1:
            pair += "F"
        semi_octets.append(int(pair[1] + pair[0], 16))
    return len(digits), (0x91 if international else 0x81), bytes(semi_octets)


def _encode_submit_pdu(
    phone_number: str,
    user_data: bytes,
    *,
    part_number: int,
    part_count: int,
    reference: int,
) -> tuple[str, int]:
    address_length, toa, address = _semi_octet_address(phone_number)
    multipart = part_count > 1
    user_data_header = (
        bytes((5, 0, 3, reference, part_count, part_number))
        if multipart
        else b""
    )
    payload = user_data_header + user_data
    if len(payload) > 140:
        raise ValueError("SMS part exceeds the 140-byte payload limit.")

    pdu = bytes((0, 0x41 if multipart else 0x01, 0, address_length))
    pdu += bytes((toa,)) + address + bytes((0, 8, len(payload))) + payload
    return pdu.hex().upper(), len(pdu) - 1


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
        self.close()
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

        try:
            if not self._at_ok("AT"):
                raise GsmConnectionError("GSM module did not respond to AT")
            if not self._at_ok("AT+CMGF=0"):
                raise GsmConnectionError("GSM module failed to enter PDU mode")
            logger.info("Sim800SmsService opened on %s", self._port)
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        with self._lock:
            if self._serial and self._serial.is_open:
                self._serial.close()
        logger.info("Sim800SmsService closed")

    def is_connected(self) -> bool:
        return bool(self._serial and self._serial.is_open)

    def is_device_present(self) -> bool:
        return any(
            port.device.casefold() == self._port.casefold()
            for port in list_ports.comports()
        )

    # --- Core contract ---

    def send_sms(self, phone_number: str, message: str) -> SmsResult:
        if not self.is_connected():
            raise GsmConnectionError("GSM serial port is not open")

        try:
            parts = _ucs2_parts(message)
            _semi_octet_address(phone_number)
        except ValueError as exc:
            return SmsResult(
                success=False,
                phone_number=phone_number,
                message=message,
                reason=str(exc),
            )

        reference = secrets.randbelow(256)
        responses: list[str] = []
        with self._lock:
            try:
                for part_number, user_data in enumerate(parts, start=1):
                    pdu, tpdu_length = _encode_submit_pdu(
                        phone_number,
                        user_data,
                        part_number=part_number,
                        part_count=len(parts),
                        reference=reference,
                    )
                    self._write_line(f"AT+CMGS={tpdu_length}")
                    prompt_response = self._read_response({">", "ERROR"})
                    responses.append(prompt_response)
                    if ">" not in prompt_response:
                        reason = (
                            f"modem returned ERROR before part {part_number}"
                            if "ERROR" in prompt_response
                            else f"no PDU prompt for part {part_number}"
                        )
                        logger.warning(
                            "SMS FAILED to %s: %s | response=%r",
                            phone_number,
                            reason,
                            "".join(responses),
                        )
                        return SmsResult(
                            success=False,
                            phone_number=phone_number,
                            message=message,
                            reason=reason,
                            raw_response="".join(responses).strip(),
                        )

                    self._serial.write(pdu.encode("ascii") + b"\x1a")
                    send_response = self._read_response({"+CMGS:", "ERROR"})
                    responses.append(send_response)
                    if "+CMGS:" not in send_response:
                        reason = (
                            f"modem returned ERROR for part {part_number}"
                            if "ERROR" in send_response
                            else f"no acknowledgement for part {part_number}"
                        )
                        logger.warning(
                            "SMS FAILED to %s: %s | response=%r",
                            phone_number,
                            reason,
                            "".join(responses),
                        )
                        return SmsResult(
                            success=False,
                            phone_number=phone_number,
                            message=message,
                            reason=reason,
                            raw_response="".join(responses).strip(),
                        )
            except serial.SerialException as exc:
                logger.exception("GSM serial error")
                connection = self._serial
                self._serial = None
                if connection is not None and connection.is_open:
                    try:
                        connection.close()
                    except serial.SerialException:
                        logger.exception("Could not close disconnected GSM serial port")
                return SmsResult(
                    success=False,
                    phone_number=phone_number,
                    message=message,
                    reason=f"serial error: {exc}",
                )

        logger.info("SMS submitted to modem for %s in %d part(s)", phone_number, len(parts))
        return SmsResult(
            success=True,
            phone_number=phone_number,
            message=message,
            raw_response="".join(responses).strip(),
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

    def _read_response(self, markers: set[str]) -> str:
        deadline = time.time() + self._timeout
        response = ""
        while time.time() < deadline:
            line = self._serial.readline().decode("utf-8", errors="ignore")
            if line:
                response += line
            if any(marker in response for marker in markers):
                break
            time.sleep(0.05)
        return response