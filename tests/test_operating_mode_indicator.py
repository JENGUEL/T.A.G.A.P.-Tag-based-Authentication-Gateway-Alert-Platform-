import pytest

from config import settings
from ui.screens.standby import build_standby_screen


class FakePage:
    width = 837
    height = 800

    def run_task(self, _handler, *_args):
        return None


@pytest.mark.parametrize(
    (
        "mock_rfid",
        "mock_sms",
        "developer_mode",
        "reader_connected",
        "sms_connected",
        "expected_label",
        "expected_color",
    ),
    [
        (True, True, False, False, False, "SIMULATION MODE", "#D9A05B"),
        (False, False, False, False, False, "READER OFFLINE", "#BA384B"),
        (False, False, False, True, False, "DEGRADED MODE", "#D9A05B"),
        (False, False, False, True, True, "REAL HARDWARE", "#397E68"),
        (True, True, True, True, True, "DEVELOPER MODE", "#3976D8"),
        (True, False, False, False, True, "MIXED MODE", "#D9A05B"),
    ],
)
def test_standby_indicator_distinguishes_operating_modes(
    monkeypatch,
    mock_rfid,
    mock_sms,
    developer_mode,
    reader_connected,
    sms_connected,
    expected_label,
    expected_color,
):
    monkeypatch.setattr(settings, "USE_MOCK_RFID", mock_rfid)
    monkeypatch.setattr(settings, "USE_MOCK_SMS", mock_sms)
    controls = []

    build_standby_screen(
        FakePage(),
        lambda _uid: None,
        developer_mode=developer_mode,
        rfid_connected=reader_connected,
        sms_connected=sms_connected,
        on_mode_controls=lambda text, dot, icon: controls.extend([text, dot, icon]),
    )

    assert controls[0].value == expected_label
    assert controls[0].color == expected_color
    assert controls[1].bgcolor == expected_color
