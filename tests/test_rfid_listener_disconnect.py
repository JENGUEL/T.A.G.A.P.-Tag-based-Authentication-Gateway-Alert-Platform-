import asyncio
import logging

from core.exceptions import RfidConnectionError
from services.rfid_listener import RfidListener


class FakePage:
    def run_task(self, handler, *args):
        return asyncio.create_task(handler(*args))


class DisconnectedReader:
    def __init__(self):
        self.connected = True
        self.device_present = True
        self.open_calls = 0
        self.close_calls = 0
        self.read_calls = 0

    def is_connected(self):
        return self.connected

    def is_device_present(self):
        return self.device_present

    def read_card(self, _timeout):
        self.read_calls += 1
        raise OSError("reader unplugged")

    def close(self):
        self.close_calls += 1
        self.connected = False

    def open(self):
        self.open_calls += 1
        self.connected = True


def test_rfid_listener_reports_runtime_disconnect_without_auto_reopening():
    reader = DisconnectedReader()
    changes = []
    listener = RfidListener(
        FakePage(),
        lambda _uid: None,
        changes.append,
    )
    listener.rfid = reader

    asyncio.run(listener._listen_loop())

    assert changes == [False]
    assert reader.close_calls == 1
    assert reader.open_calls == 0
    assert listener.is_running is False


def test_rfid_listener_detects_missing_usb_device_even_if_handle_is_open():
    reader = DisconnectedReader()
    reader.device_present = False
    changes = []
    listener = RfidListener(
        FakePage(),
        lambda _uid: None,
        changes.append,
    )
    listener.rfid = reader

    asyncio.run(listener._listen_loop())

    assert changes == [False]
    assert reader.close_calls == 1
    assert reader.read_calls == 0
    assert listener.is_running is False


def test_rfid_listener_reports_serial_read_access_denied_as_disconnect(caplog):
    class AccessDeniedReader(DisconnectedReader):
        def read_card(self, _timeout):
            raise RfidConnectionError(
                "Serial read failed; the reader connection was interrupted: "
                "GetOverlappedResult failed (PermissionError: Access is denied)"
            )

    reader = AccessDeniedReader()
    changes = []
    listener = RfidListener(FakePage(), lambda _uid: None, changes.append)
    listener.rfid = reader

    with caplog.at_level(logging.WARNING, logger="services.rfid_listener"):
        asyncio.run(listener._listen_loop())

    assert changes == [False]
    assert reader.close_calls == 1
    assert reader.open_calls == 0
    assert listener.is_running is False
    assert "RFID reader disconnected during read" in caplog.text
