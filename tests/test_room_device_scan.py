import pytest

from ui import router as router_module


@pytest.fixture
def beep_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(
        router_module.AudioService, "beep", lambda: calls.append("beep")
    )
    return calls


def test_room_device_admin_scan_updates_live_status_without_alerting(
    monkeypatch, beep_calls
):
    router = object.__new__(router_module.AppRouter)
    router.current_alert = None
    router.room_id = 1
    router.in_admin_mode = True
    router.current_admin_section = "Room Device"
    router.reader_monitor_auth_pending = False
    router.card_registration_session = None
    received_uids = []
    router._record_room_device_scan = received_uids.append
    monkeypatch.setattr(
        router_module.AlertService,
        "scan_card",
        lambda _: pytest.fail("Room Device scans must not create alert requests"),
    )

    router.handle_card_scan("A1B2C3D4")

    assert received_uids == ["A1B2C3D4"]
    assert beep_calls == ["beep"]


def test_admin_scans_outside_room_device_are_not_processed(monkeypatch, beep_calls):
    router = object.__new__(router_module.AppRouter)
    router.current_alert = None
    router.room_id = 1
    router.in_admin_mode = True
    router.current_admin_section = "Alert History"
    router.reader_monitor_auth_pending = False
    router.card_registration_session = None
    router._record_room_device_scan = lambda _: pytest.fail(
        "Only Room Device should display the live scan"
    )
    monkeypatch.setattr(
        router_module.AlertService,
        "scan_card",
        lambda _: pytest.fail("Admin scans must not trigger alerts"),
    )

    router.handle_card_scan("A1B2C3D4")
    assert beep_calls == ["beep"]


def test_card_scan_beeps_even_when_an_alert_is_already_open(monkeypatch, beep_calls):
    router = object.__new__(router_module.AppRouter)
    router.current_alert = object()

    router.handle_card_scan("A1B2C3D4")

    assert beep_calls == ["beep"]
