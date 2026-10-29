"""
T.A.G.A.P. - UI Router & State Machine
Implements SPA navigation with skeleton loaders.
"""
import asyncio
import flet as ft
from datetime import datetime
from typing import Optional

from core.constants import CardType
from models.sms_result_dto import AlertResult, AlertOutcome
from services.alert_service import AlertService
from services.rfid_listener import RfidListener
from ui.screens.standby import build_standby_screen
from ui.screens.confirmation import build_confirmation_screen
from ui.screens.admin.room_device import build_room_device
from ui.screens.admin.alert_history import build_alert_history
from ui.screens.admin.settings import build_settings
from ui.components.toast import Toast
from ui.theme import *


class AppRouter:
    def __init__(self, page: ft.Page):
        self.page = page
        self.current_alert: Optional[AlertResult] = None
        self.clock_ctrl: Optional[ft.Text] = None
        self.room_id: Optional[int] = 1
        self.in_admin_mode = False

        # Reference to the inner content area of the shell
        self.body_host: Optional[ft.Container] = None
        self.current_admin_section: str = "Room Device"

        self.page.title = "T.A.G.A.P. Kiosk"
        self.page.padding = 0
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.bgcolor = BG_OFF_WHITE
        try:
            self.page.window.full_screen = True
        except Exception:
            pass
        self.page.on_keyboard_event = self._handle_keyboard

        self.rfid_listener = RfidListener(self.page, self.handle_card_scan)
        self.rfid_listener.start()
        self.page.run_task(self._clock_tick_loop)

        self.show_standby()

    def _handle_keyboard(self, e: ft.KeyboardEvent):
        if e.key == "Escape":
            try:
                self.page.window.full_screen = not self.page.window.full_screen
                self.page.update()
            except Exception:
                pass

    async def _clock_tick_loop(self):
        while True:
            if self.clock_ctrl:
                try:
                    self.clock_ctrl.value = datetime.now().strftime("%H:%M:%S")
                    self.clock_ctrl.update()
                except Exception:
                    pass
            await asyncio.sleep(1)

    # ==========================================
    # KIOSK FLOW
    # ==========================================

    def show_standby(self):
        self.in_admin_mode = False
        self.body_host = None
        self.page.views.clear()
        view, self.clock_ctrl = build_standby_screen(self.page, self.handle_card_scan)
        self.page.views.append(view)
        self.page.update()

    def handle_card_scan(self, uid: str):
        if self.current_alert is not None or self.in_admin_mode:
            return

        result = AlertService.scan_card(uid)

        if result.outcome == AlertOutcome.NEEDS_CONFIRMATION:
            self.current_alert = result
            self.show_confirmation(result)
        elif result.outcome == AlertOutcome.ADMIN_ACCESS:
            self.room_id = result.room_id or 1
            self.show_admin("Room Device")
        elif result.outcome == AlertOutcome.REJECTED_DUPLICATE:
            Toast.show(self.page, "Card already scanned. Please wait.", "warning")
        else:
            Toast.show(self.page, f"Unknown card: {uid}", "error")

    def show_confirmation(self, result: AlertResult):
        self.rfid_listener.stop()
        self.page.views.clear()

        def on_confirm():
            exec_result = AlertService.execute_alert(result.card_uid, result.scan_ts)
            if exec_result.outcome == AlertOutcome.ERROR:
                Toast.show(self.page, f"Error: {exec_result.error_message}", "error")
            else:
                Toast.show(self.page, f"{result.card_type.value} Sent to {exec_result.sms_queued} recipients!", "success")
            self.current_alert = None
            self.rfid_listener.start()
            self.show_standby()

        def on_cancel():
            if hasattr(self.page, "countdown_task") and self.page.countdown_task:
                self.page.countdown_task.cancel()
            Toast.show(self.page, "Alert cancelled. No messages were sent.", "warning")
            self.current_alert = None
            self.rfid_listener.start()
            self.show_standby()

        self.page.views.append(build_confirmation_screen(self.page, result, on_confirm, on_cancel))
        self.page.update()

    # ==========================================
    # ADMIN FLOW (SPA)
    # ==========================================

    def show_admin(self, section: str = "Room Device"):
        self.in_admin_mode = True
        self.rfid_listener.stop()

        if hasattr(self.page, "countdown_task") and self.page.countdown_task:
            try:
                self.page.countdown_task.cancel()
            except Exception:
                pass

        # Build the initial view (returns a View with the shell + content)
        view = self._build_view(section)

        # Extract the body_host from the view structure:
        # view.controls[0] -> Row
        # Row.controls[1] -> Column
        # Column.controls[1] -> Container (content area)
        try:
            self.body_host = view.controls[0].controls[1].controls[1]
        except (AttributeError, IndexError):
            self.body_host = None

        self.current_admin_section = section
        self.page.views.clear()
        self.page.views.append(view)
        self.page.update()

    def _build_view(self, section: str) -> ft.View:
        """Builds the full view (shell + content) for a given section."""
        # Rebuilding the view each time is fine because we swap the body_host,
        # not replace the whole view in page.views
        if section == "Alert History":
            return build_alert_history(self.page, self.room_id, self._navigate_admin, self.exit_admin)
        elif section == "Settings":
            return build_settings(self.page, self.room_id, self._navigate_admin, self.exit_admin)
        else:
            return build_room_device(self.page, self.room_id, self._navigate_admin, self.exit_admin)

    def _navigate_admin(self, section: str):
        if section == "Main Kiosk":
            self.exit_admin()
            return

        # If section is the same as current, do nothing
        if section == self.current_admin_section:
            return

        # If we somehow lost body_host, fall back to full reload
        if not self.body_host:
            self.show_admin(section)
            return

        self.page.run_task(self._transition_admin, section)

    async def _transition_admin(self, section: str):
        # 1. Fade out current content
        self.body_host.opacity = 0
        self.page.update()
        await asyncio.sleep(0.15)

        # 2. Show Skeleton loader
        self.body_host.content = self._build_skeleton(section)
        self.body_host.opacity = 1
        self.page.update()
        await asyncio.sleep(0.25)

        # 3. Fade out skeleton
        self.body_host.opacity = 0
        self.page.update()
        await asyncio.sleep(0.1)

        # 4. Build the new view and extract its content
        new_view = self._build_view(section)
        try:
            new_content = new_view.controls[0].controls[1].controls[1].content
        except (AttributeError, IndexError):
            new_content = ft.Container()

        # 5. Swap content and fade in
        self.body_host.content = new_content
        self.body_host.opacity = 1
        self.current_admin_section = section
        self.page.update()

    def _build_skeleton(self, title: str) -> ft.Control:
        def block(height: int, width: int = None) -> ft.Container:
            return ft.Container(height=height, width=width, bgcolor="#EEE9EB", border_radius=8)
        return ft.Column(expand=True, spacing=16, controls=[
            ft.Row(tight=True, spacing=10, controls=[
                ft.ProgressRing(value=None, color=PRIMARY_RED, stroke_width=2),
                ft.Text(f"Loading {title}...", size=13, color=MUTED),
            ]),
            ft.Row(spacing=14, controls=[
                ft.Container(expand=1, padding=18, bgcolor=CARD_WHITE, border_radius=16, content=ft.Column(spacing=14, controls=[block(18, 180), block(12, 250), block(180)])),
                ft.Container(expand=1, padding=18, bgcolor=CARD_WHITE, border_radius=16, content=ft.Column(spacing=14, controls=[block(18, 150), block(64), block(14), block(14)])),
            ])
        ])

    def exit_admin(self):
        self.in_admin_mode = False
        self.body_host = None
        self.rfid_listener.start()
        self.show_standby()