import asyncio

import flet as ft

from ui.router import AppRouter
from ui.screens.admin.shell import build_admin_shell
from ui.theme import ADMIN_NAV_ACTIVE_BG


class FakePage:
    def __init__(self):
        self.views = []
        self.tasks = []

    def update(self):
        return None

    def run_task(self, handler, *args):
        self.tasks.append((handler, args))


def test_sidebar_active_state_moves_when_navigation_item_is_clicked():
    navigated = []
    view = build_admin_shell(
        FakePage(),
        active_page="Reader Monitor",
        room_name="Room 201",
        on_navigate=navigated.append,
        on_back_to_kiosk=lambda: None,
        content=ft.Container(),
    )
    sidebar = view.controls[0].controls[0]
    nav_items = {
        child.content.controls[1].value: child
        for child in sidebar.content.controls
        if isinstance(child, ft.Container)
        and isinstance(child.content, ft.Row)
        and len(child.content.controls) == 2
        and isinstance(child.content.controls[1], ft.Text)
    }

    nav_items["Alert History"].on_click(None)

    assert navigated == ["Alert History"]
    assert nav_items["Alert History"].bgcolor == ADMIN_NAV_ACTIVE_BG
    assert nav_items["Reader Monitor"].bgcolor == "transparent"


def test_admin_navigation_preserves_shell_and_replaces_only_right_content():
    page = FakePage()
    old_view = build_admin_shell(
        page,
        active_page="Room Device",
        room_name="Room 201",
        on_navigate=lambda _: None,
        on_back_to_kiosk=lambda: None,
        content=ft.Container(content=ft.Text("Old screen")),
    )
    next_view = build_admin_shell(
        page,
        active_page="Alert History",
        room_name="Room 201",
        on_navigate=lambda _: None,
        on_back_to_kiosk=lambda: None,
        content=ft.Container(content=ft.Text("New screen")),
    )
    page.views.append(old_view)
    original_body = AppRouter._admin_body_host(old_view)
    next_body = AppRouter._admin_body_host(next_view)
    router = object.__new__(AppRouter)
    router.page = page
    router.body_host = original_body
    router.current_admin_section = "Room Device"
    router.room_device_controls = {}
    router._build_view = lambda _section: next_view
    router._build_skeleton = lambda _section: ft.Text("Loading")

    asyncio.run(router._transition_admin("Alert History"))

    assert page.views == [old_view]
    assert router.body_host is original_body
    assert original_body.content is next_body.content
    assert router.current_admin_section == "Alert History"
    assert page.tasks == [(router._start_admin_rfid_listener, ())]
    active_item = next(
        item
        for item in old_view.controls[0].controls[0].content.controls
        if isinstance(item, ft.Container) and item.data == "Alert History"
    )
    assert active_item.bgcolor == ADMIN_NAV_ACTIVE_BG


def test_admin_navigation_loader_does_not_expand_into_a_large_gray_panel():
    router = object.__new__(AppRouter)

    loader = router._build_skeleton("Emergency Report")

    assert loader.height == 112
    assert loader.bgcolor != "#EEE9EB"
