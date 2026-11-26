from services.rfid_listener import RfidListener


class FakePage:
    def __init__(self):
        self.tasks = []

    def run_task(self, task):
        self.tasks.append(task)


def test_start_restarts_listener_after_stop():
    page = FakePage()
    listener = RfidListener(page, lambda _uid: None)
    listener.stop()

    listener.start()

    assert listener.is_running is True
    assert page.tasks == [listener._listen_loop]
