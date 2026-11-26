from types import SimpleNamespace

import pytest

from core.exceptions import GsmConnectionError
from services.adapters import sms_real
from services.adapters.sms_real import Sim800SmsService


def test_failed_modem_handshake_closes_serial_port(monkeypatch):
    class FakeSerial:
        is_open = True

        def close(self):
            self.is_open = False

    connection = FakeSerial()
    monkeypatch.setattr(sms_real.serial, "Serial", lambda **_kwargs: connection)
    service = Sim800SmsService("COM4")
    monkeypatch.setattr(service, "_at_ok", lambda _command: False)

    with pytest.raises(GsmConnectionError, match="did not respond to AT"):
        service.open()

    assert connection.is_open is False
    assert service.is_connected() is False


def test_modem_presence_checks_only_configured_port(monkeypatch):
    service = Sim800SmsService("COM4")
    monkeypatch.setattr(
        sms_real.list_ports,
        "comports",
        lambda: [SimpleNamespace(device="COM3"), SimpleNamespace(device="COM4")],
    )

    assert service.is_device_present() is True

    monkeypatch.setattr(
        sms_real.list_ports,
        "comports",
        lambda: [SimpleNamespace(device="COM3")],
    )

    assert service.is_device_present() is False


def test_sms_serial_error_closes_connection_for_disconnect_detection():
    class DisconnectedSerial:
        is_open = True

        def write(self, _data):
            raise sms_real.serial.SerialException("device was removed")

        def close(self):
            self.is_open = False

    service = Sim800SmsService("COM4")
    connection = DisconnectedSerial()
    service._serial = connection

    result = service.send_sms("0000000000", "test")

    assert result.success is False
    assert connection.is_open is False
    assert service.is_connected() is False
