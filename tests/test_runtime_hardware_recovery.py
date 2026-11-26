import asyncio

from ui.router import AppRouter


class FakePage:
    def __init__(self):
        self.shown_dialog = None
        self.closed_dialogs = 0

    def show_dialog(self, dialog):
        self.shown_dialog = dialog

    def pop_dialog(self):
        self.closed_dialogs += 1

    def update(self):
        return None

    def run_task(self, handler, *args):
        return asyncio.create_task(handler(*args))


def test_runtime_disconnect_dialog_shows_both_devices_and_continue_option(monkeypatch):
    router = object.__new__(AppRouter)
    router.page = FakePage()
    router.reader_connected = False
    router.sms_connected = True
    router.developer_mode = False
    router.mode_text_control = None
    router.mode_dot_control = None
    router.mode_icon_control = None
    router.runtime_hardware_dialog = None
    router.runtime_hardware_log = None
    router.runtime_hardware_status_controls = {}
    monkeypatch.setattr("ui.router.Toast.show", lambda *_args, **_kwargs: None)

    async def exercise_dialog():
        await router._apply_runtime_hardware_connection("RFID reader", False)

        assert router.page.shown_dialog is router.runtime_hardware_dialog
        assert router.runtime_hardware_status_controls["rfid"].value == "DISCONNECTED"
        assert router.runtime_hardware_status_controls["gsm"].value == "CONNECTED"
        assert len(router.runtime_hardware_dialog.actions) == 2
        terminal_lines = [
            line.value for line in router.runtime_hardware_log.controls
        ]
        assert any("CONNECTED] GSM modem" in line for line in terminal_lines)
        assert any("RFID reader disconnected" in line for line in terminal_lines)

        dialog = router.runtime_hardware_dialog
        router.sms_connected = False
        await router._apply_runtime_hardware_connection("GSM modem", False)
        assert router.runtime_hardware_dialog is dialog
        assert router.runtime_hardware_status_controls["gsm"].value == "DISCONNECTED"

        continue_task = router.runtime_hardware_dialog.actions[0].on_click(None)
        await continue_task

        assert router.page.closed_dialogs == 1
        assert router.runtime_hardware_dialog is None

    asyncio.run(exercise_dialog())


def test_runtime_recovery_closes_dialog_after_both_devices_reconnect(monkeypatch):
    router = object.__new__(AppRouter)
    router.page = FakePage()
    router.reader_connected = False
    router.sms_connected = False
    router.developer_mode = False
    router.mode_text_control = None
    router.mode_dot_control = None
    router.mode_icon_control = None
    router.runtime_hardware_dialog = None
    router.runtime_hardware_log = None
    router.runtime_hardware_status_controls = {}
    monkeypatch.setattr("ui.router.Toast.show", lambda *_args, **_kwargs: None)

    async def exercise_recovery():
        await router._apply_runtime_hardware_connection("RFID reader", False)

        router.reader_connected = True
        await router._apply_runtime_hardware_connection("RFID reader", True)
        assert router.runtime_hardware_dialog is not None

        router.sms_connected = True
        completed = await router._apply_runtime_hardware_connection("GSM modem", True)

        assert completed is True
        assert router.runtime_hardware_dialog is None
        assert router.page.closed_dialogs == 1

    asyncio.run(exercise_recovery())
