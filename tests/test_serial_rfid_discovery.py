from types import SimpleNamespace

import pytest
import serial

from core.exceptions import RfidConnectionError
from services.adapters import rfid_real
from services.adapters.rfid_real import READER_READY, SerialRfidService


def test_parser_accepts_only_supported_uid_lines():
    assert SerialRfidService._parse_line(b"UID:04a1b2c3\r\n") == "04A1B2C3"
    assert SerialRfidService._parse_line(b"04A1B2C3\r\n") == "04A1B2C3"
    assert SerialRfidService._parse_line(READER_READY.encode()) is None
    assert SerialRfidService._parse_line(b"not-a-uid\r\n") is None


def test_candidate_ports_excludes_gsm_and_includes_usb_serial(monkeypatch):
    ports = [
        SimpleNamespace(device="COM3", vid=0x2341),
        SimpleNamespace(device="COM4", vid=0x10C4),
        SimpleNamespace(device="COM5", vid=0x1A86),
        SimpleNamespace(device="COM7", vid=None),
    ]
    monkeypatch.setattr(
        "services.adapters.rfid_real.list_ports.comports",
        lambda: ports,
    )
    service = SerialRfidService("COM3", excluded_ports=("com4",))

    assert service._candidate_ports() == ["COM3", "COM5"]


def test_device_presence_tracks_the_verified_reader_port(monkeypatch):
    ports = [SimpleNamespace(device="COM8", vid=0x2341)]
    monkeypatch.setattr(
        "services.adapters.rfid_real.list_ports.comports",
        lambda: ports,
    )
    service = SerialRfidService("COM8")

    assert service.is_device_present() is True

    ports.clear()
    assert service.is_device_present() is False


def test_open_keeps_only_port_that_completes_reader_handshake(monkeypatch):
    class FakeSerial:
        is_open = True

        def __init__(self, **_kwargs):
            self.written = b""

        def reset_input_buffer(self):
            pass

        def write(self, payload):
            self.written += payload

        def flush(self):
            pass

        def readline(self):
            return f"{READER_READY}\r\n".encode()

        def close(self):
            self.is_open = False

    monkeypatch.setattr(
        "services.adapters.rfid_real.list_ports.comports",
        lambda: [SimpleNamespace(device="COM8", vid=0x2341)],
    )
    monkeypatch.setattr("services.adapters.rfid_real.serial.Serial", FakeSerial)
    monkeypatch.setattr("services.adapters.rfid_real.time.sleep", lambda _seconds: None)
    monkeypatch.setattr(rfid_real.settings, "RFID_PORT", "COM3")
    service = SerialRfidService("COM3")

    service.open()

    assert service.is_connected()
    assert service._port == "COM8"
    assert rfid_real.settings.RFID_PORT == "COM8"
    assert service._serial.written == rfid_real.PING_COMMAND
    service.close()


def test_read_failure_closes_and_invalidates_serial_handle():
    class FailedReadSerial:
        is_open = True
        timeout = None

        def readline(self):
            raise serial.SerialException(
                "GetOverlappedResult failed (PermissionError: Access is denied)"
            )

        def close(self):
            self.is_open = False

    service = SerialRfidService("COM8")
    connection = FailedReadSerial()
    service._serial = connection

    with pytest.raises(RfidConnectionError, match="connection was interrupted"):
        service.read_card()

    assert service.is_connected() is False
    assert service._serial is None
    assert connection.is_open is False
