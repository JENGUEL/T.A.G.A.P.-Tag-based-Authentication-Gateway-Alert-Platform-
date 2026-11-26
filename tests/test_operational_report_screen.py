import flet as ft

from ui.screens.admin.operational_report import build_operational_report


def test_operational_report_screen_uses_existing_admin_shell(monkeypatch):
    monkeypatch.setattr(
        "ui.screens.admin.operational_report.queries.get_room_info",
        lambda room_id: {"room_name": "Room 201"},
    )

    view = build_operational_report(
        object(),
        1,
        lambda _: None,
        lambda: None,
    )

    assert isinstance(view, ft.View)
    assert view.route == "/admin/emergency_report"

    pending = list(view.controls)
    while pending:
        control = pending.pop()
        assert not (
            isinstance(control, ft.Container)
            and control.height is not None
            and control.height >= 300
        )
        pending.extend(getattr(control, "controls", []) or [])
        content = getattr(control, "content", None)
        if content is not None:
            pending.append(content)
