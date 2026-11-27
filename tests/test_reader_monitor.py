import asyncio

from ui.screens.admin.reader_monitor import ReaderMonitor
from services.adapters.rfid_real import READER_READY


class FakePage:
    def update(self):
        pass


class FakeSerial:
    def __init__(self):
        self.is_open = True
        self.port = "COM-test"

    def readline(self):
        self.is_open = False
        return b"UID:04A1B2C3\r\n"


def test_reader_monitor_displays_uid_from_serial_line():
    monitor = ReaderMonitor(FakePage())
    monitor._serial = FakeSerial()

    asyncio.run(monitor._read_loop(monitor._serial))

    assert monitor.output.controls[-1].value.endswith("UID > 04A1B2C3")


def test_reader_monitor_returns_to_kiosk_when_active_admin_card_is_scanned():
    exits = []
    monitor = ReaderMonitor(
        FakePage(),
        is_admin_card_uid=lambda uid: uid == "04A1B2C3",
        on_admin_card_scanned=lambda: exits.append(True),
    )
    monitor._serial = FakeSerial()

    async def scenario():
        await monitor._read_loop(monitor._serial)
        await asyncio.sleep(0)

    asyncio.run(scenario())

    assert exits == [True]
    assert monitor.output.controls[-1].value.endswith(
        "ADMIN CARD detected · returning to kiosk."
    )


def test_reader_monitor_marks_handshake_verified():
    class HandshakeSerial:
        is_open = True
        port = "COM-test"

        def readline(self):
            self.is_open = False
            return f"{READER_READY}\r\n".encode()

    monitor = ReaderMonitor(FakePage())
    connection = HandshakeSerial()
    monitor._serial = connection
    monitor._handshake_event = asyncio.Event()

    asyncio.run(monitor._read_loop(connection))

    assert monitor.reader_verified is True
    assert monitor.status_text.value == "Reader verified · COM-test"
    assert monitor._handshake_event is None
