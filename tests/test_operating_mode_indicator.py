import pytest

from config import settings
from ui.screens.standby import build_standby_screen


class FakePage:
    width = 837
    height = 800

    def run_task(self, _handler, *_args):
        return None


@pytest.mark.parametrize(
    ("mock_rfid", "developer_mode", "reader_connected", "expected_label", "expected_color"),
    [
        (True, False, False, "SIMULATION MODE", "#D9A05B"),
        (False, False, False, "READER OFFLINE", "#BA384B"),
        (False, False, True, "REAL RFID", "#397E68"),
        (True, True, True, "DEVELOPER MODE", "#3976D8"),
    ],
)
def test_standby_indicator_distinguishes_operating_modes(
    monkeypatch,
    mock_rfid,
    developer_mode,
    reader_connected,
    expected_label,
    expected_color,
):
    monkeypatch.setattr(settings, "USE_MOCK_RFID", mock_rfid)
    controls = []

    build_standby_screen(
        FakePage(),
        lambda _uid: None,
        developer_mode=developer_mode,
        rfid_connected=reader_connected,
        on_mode_controls=lambda text, dot, icon: controls.extend([text, dot, icon]),
    )

    assert controls[0].value == expected_label
    assert controls[0].color == expected_color
    assert controls[1].bgcolor == expected_color
