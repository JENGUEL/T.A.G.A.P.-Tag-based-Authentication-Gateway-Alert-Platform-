"""
T.A.G.A.P. - Confirmation Screen
"""
import asyncio
import flet as ft
from typing import Callable, Optional
from ui.theme import *
from models.sms_result_dto import AlertResult
from services.audio_service import AudioService
from config import settings


def build_confirmation_screen(
    page: ft.Page,
    alert_result: AlertResult,
    on_confirm: Callable,
    on_cancel: Callable,
) -> ft.View:
    color = get_card_color(alert_result.card_type.value)
    icon = get_card_icon(alert_result.card_type.value)
    timeout_sec = settings.CONFIRMATION_TIMEOUT_SECONDS

    # --- State ---
    state = {
        "mode": "alert",            # "alert" or "cancel"
        "time_left": timeout_sec,   # Counts down for the active timer
        "main_task": None,
        "cancel_task": None,
    }

    countdown_text = ft.Text(
        str(timeout_sec), size=64, weight=ft.FontWeight.BOLD, color="white"
    )
    countdown_label = ft.Text(
        "Sending alert in", size=12, color="white"
    )

    if alert_result.card_type.value == "DANGER":
        AudioService.error()
    else:
        AudioService.beep()

    cancel_btn = ft.Button(
        "CANCEL",
        icon=ft.Icons.CLOSE,
        style=ft.ButtonStyle(bgcolor="white", color=color),
    )

    def _render_timer():
        countdown_text.value = str(state["time_left"])
        if state["mode"] == "cancel":
            countdown_label.value = "Confirm cancel in"
        else:
            countdown_label.value = "Sending alert in"
        page.update()

    # --- Main Alert Timer ---
    async def run_main_timer():
        try:
            while state["time_left"] > 0:
                # If user has armed cancel, pause this timer
                if state["mode"] == "cancel":
                    await asyncio.sleep(0.1)
                    continue

                _render_timer()
                await asyncio.sleep(1)
                state["time_left"] -= 1

            # Time's up — confirm the alert
            on_confirm()
        except asyncio.CancelledError:
            pass

    # --- Cancel Confirmation Timer ---
    async def run_cancel_timer():
        try:
            while state["time_left"] > 0:
                _render_timer()
                await asyncio.sleep(1)
                state["time_left"] -= 1

            # Time's up — disarm cancel and resume main timer
            state["mode"] = "alert"
            state["time_left"] = timeout_sec
            cancel_btn.content = "CANCEL"
            cancel_btn.icon = ft.Icons.CLOSE
            cancel_btn.style = ft.ButtonStyle(bgcolor="white", color=color)
            _render_timer()
        except asyncio.CancelledError:
            pass

    def handle_cancel_click(e):
        if state["mode"] == "alert":
            # FIRST TAP: pause alert timer, arm cancel
            if state["main_task"]:
                state["main_task"].cancel()

            state["mode"] = "cancel"
            state["time_left"] = timeout_sec  # reset countdown to 3

            cancel_btn.content = "TAP AGAIN TO CANCEL"
            cancel_btn.icon = ft.Icons.WARNING_AMBER_ROUNDED
            cancel_btn.style = ft.ButtonStyle(bgcolor="white", color=PRIMARY_RED)

            _render_timer()

            # Start cancel countdown
            state["cancel_task"] = page.run_task(run_cancel_timer)
            return

        # SECOND TAP: actually cancel
        if state["cancel_task"]:
            state["cancel_task"].cancel()
        if state["main_task"]:
            state["main_task"].cancel()
        on_cancel()

    cancel_btn.on_click = handle_cancel_click

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
                        f"{alert_result.card_type.value} DETECTED",
                        size=24, weight=ft.FontWeight.BOLD, color="white",
                    ),
                    ft.Text(f"Room: {alert_result.room_name}", size=16, color="white"),
                    ft.Container(
                        padding=10,
                        bgcolor=ft.Colors.with_opacity(0.15, "white"),
                        border_radius=8,
                        content=ft.Text(
                            "Will notify: Parents + Police Station",
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
                    ft.Container(height=10),
                    cancel_btn,
                ],
            )
        ],
    )

    # Start the main alert timer
    state["main_task"] = page.run_task(run_main_timer)
    page.countdown_task = state["main_task"]
    page.cancel_timer_task = state["cancel_task"]

    return view