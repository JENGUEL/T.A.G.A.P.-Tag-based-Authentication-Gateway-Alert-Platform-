"""
T.A.G.A.P. - Confirmation Screen
"""
import asyncio
import flet as ft
from typing import Callable
from ui.theme import *
from models.sms_result_dto import AlertResult
from services.audio_service import AudioService
from config import settings
from core.constants import card_type_value


def build_confirmation_screen(
    page: ft.Page,
    alert_result: AlertResult,
    on_confirm: Callable,
    on_cancel: Callable,
    on_timeout: Callable,
    on_scan_confirm_ready: Callable[[Callable[[], None]], None] | None = None,
) -> ft.View:
    card_type = card_type_value(alert_result.card_type or "ALERT")
    color = get_card_color(card_type)
    icon = get_card_icon(card_type)
    timeout_sec = settings.CONFIRMATION_TIMEOUT_SECONDS

    state = {
        "decision": "pending",
        "time_left": timeout_sec,
        "timer_task": None,
    }

    countdown_text = ft.Text(
        str(timeout_sec), size=64, weight=ft.FontWeight.BOLD, color="white"
    )
    countdown_label = ft.Text(
        "Confirm within", size=12, color="white"
    )

    AudioService.beep()

    confirm_btn = ft.Button(
        "CONFIRM ALERT",
        icon=ft.Icons.CHECK_CIRCLE_OUTLINE,
        style=ft.ButtonStyle(bgcolor="white", color=color),
    )
    cancel_btn = ft.Button(
        "CANCEL",
        icon=ft.Icons.CLOSE,
        style=ft.ButtonStyle(bgcolor="transparent", color="white"),
    )

    def render_timer():
        countdown_text.value = str(state["time_left"])
        if state["decision"] == "expired":
            countdown_label.value = "Expired · no alert sent"
        else:
            countdown_label.value = "Confirm within"
        page.update()

    async def run_countdown():
        try:
            while state["time_left"] > 0:
                render_timer()
                await asyncio.sleep(1)
                state["time_left"] -= 1

            if state["decision"] == "pending":
                state["decision"] = "expired"
                render_timer()
                on_timeout()
        except asyncio.CancelledError:
            pass

    def resolve(decision: str, callback: Callable) -> None:
        if state["decision"] != "pending":
            return
        state["decision"] = decision
        if state["timer_task"]:
            state["timer_task"].cancel()
        callback()

    confirm_btn.on_click = lambda _: resolve("confirmed", on_confirm)
    cancel_btn.on_click = lambda _: resolve("cancelled", on_cancel)
    if on_scan_confirm_ready is not None:
        on_scan_confirm_ready(lambda: resolve("confirmed", on_confirm))

    # --- Build UI ---
    view = ft.View(
        route="/confirmation",
        padding=0,
        bgcolor=color,
        controls=[
            ft.Column(
                expand=True,
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=20,
                controls=[
                    ft.Icon(icon, size=80, color="white"),
                    ft.Text(
                        f"{card_type} DETECTED",
                        size=24, weight=ft.FontWeight.BOLD, color="white",
                    ),
                    ft.Text(f"Room: {alert_result.room_name}", size=16, color="white"),
                    ft.Container(
                        padding=10,
                        bgcolor=ft.Colors.with_opacity(0.15, "white"),
                        border_radius=8,
                        content=ft.Text(
                            "Will notify: Parents",
                            size=12, color="white",
                        ),
                    ),
                    ft.Container(
                        width=150, height=150,
                        alignment=ft.Alignment.CENTER,
                        border=ft.Border.all(6, "white"),
                        border_radius=75,
                        content=countdown_text,
                    ),
                    countdown_label,
                    ft.Text(
                        "Tap CONFIRM or scan the same card again. "
                        "If time expires, nothing is sent.",
                        size=12,
                        color="white",
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Container(height=10),
                    ft.Row(
                        tight=True,
                        spacing=16,
                        controls=[confirm_btn, cancel_btn],
                    ),
                ],
            )
        ],
    )

    state["timer_task"] = page.run_task(run_countdown)
    page.countdown_task = state["timer_task"]

    return view