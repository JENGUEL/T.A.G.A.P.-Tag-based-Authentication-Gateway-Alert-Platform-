from services.sms_worker import SmsWorker


class OfflineSmsService:
    def __init__(self):
        self.open_calls = 0
        self.device_present = True

    def is_connected(self):
        return False

    def is_device_present(self):
        return self.device_present

    def open(self):
        self.open_calls += 1
        raise OSError("modem is not connected")


def test_sms_worker_leaves_queue_untouched_while_gsm_is_offline(monkeypatch):
    sms = OfflineSmsService()

    def unexpected_database_access():
        raise AssertionError("offline worker must not fetch or consume queued SMS")

    monkeypatch.setattr("services.sms_worker.get_db", unexpected_database_access)

    worker = SmsWorker(sms_service=sms, wait_for_device_reconnect=True)

    assert worker._ensure_sms_connected() is False
    assert sms.open_calls == 0

    sms.device_present = False
    worker._next_device_check_at = 0
    assert worker._ensure_sms_connected() is False

    sms.device_present = True
    worker._next_device_check_at = 0
    assert worker._ensure_sms_connected() is False
    worker._process_batch()

    assert sms.open_calls == 1


def test_sms_worker_notifies_when_modem_connects_after_replug():
    class ReconnectedSmsService(OfflineSmsService):
        def __init__(self):
            super().__init__()
            self.connected = False

        def is_connected(self):
            return self.connected

        def open(self):
            self.open_calls += 1
            self.connected = True

    sms = ReconnectedSmsService()
    notified = []
    worker = SmsWorker(sms_service=sms, on_connection_changed=notified.append)

    assert worker._ensure_sms_connected() is True
    assert notified == [True]


def test_sms_worker_reports_a_connected_modem_disappearing():
    class DisconnectedSmsService(OfflineSmsService):
        def __init__(self):
            super().__init__()
            self.connected = True
            self.device_present = False
            self.close_calls = 0

        def is_connected(self):
            return self.connected

        def close(self):
            self.close_calls += 1
            self.connected = False

    sms = DisconnectedSmsService()
    notified = []
    worker = SmsWorker(sms_service=sms, on_connection_changed=notified.append)

    assert worker._ensure_sms_connected() is False
    assert sms.close_calls == 1
    assert notified == [False]
