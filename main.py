"""
T.A.G.A.P. - Main Entry Point & Splash Controller
"""
import asyncio
import logging
import flet as ft

from core.logger import setup_logger
from services.boot_service import run_preflight_checks
from ui.router import AppRouter

# Setup global logging
setup_logger()
log = logging.getLogger(__name__)

# Colors for the splash screen
COLOR_START = "#D45A6B"
COLOR_END = "#AE3044"
INK = "#29262B"
MUTED = "#8B858B"


def animated_title() -> tuple[ft.Row, list[tuple[ft.Container, ft.Text]]]:
    letters = []
    cells = []
    for character in "T.A.G.A.P.":
        base = ft.Text(character, size=40, weight=ft.FontWeight.BOLD, color=INK)
        shine = ft.Text(
            character, size=40, weight=ft.FontWeight.BOLD, color=COLOR_START, opacity=0,
            animate_opacity=ft.Animation(duration=200, curve=ft.AnimationCurve.EASE_IN_OUT),
        )
        cell = ft.Container(
            width=12 if character == "." else 30, height=58, alignment=ft.Alignment.CENTER,
            opacity=0, scale=0.3,
            animate_opacity=ft.Animation(duration=280, curve=ft.AnimationCurve.EASE_OUT),
            animate_scale=ft.Animation(duration=360, curve=ft.AnimationCurve.EASE_OUT_BACK),
            content=ft.Stack(alignment=ft.Alignment.CENTER, controls=[base, shine]),
        )
        letters.append(cell)
        cells.append((cell, shine))
    return ft.Row(tight=True, spacing=0, controls=letters), cells


async def run_boot_sequence(page: ft.Page):
    """Animates splash, runs checks, and routes to next screen."""
    title, title_cells = animated_title()
    progress = ft.ProgressBar(
        width=260, value=0, color=COLOR_END, bgcolor="#E8DEE1",
        bar_height=4, border_radius=4,
    )
    status_text = ft.Text("Initializing secure gateway...", size=11, color=MUTED,
                          weight=ft.FontWeight.W_600)

    shield_glow = ft.Container(
        width=118, height=118, bgcolor="#F1DCE1",
        border_radius=59, border=ft.Border.all(1, "#E8C8CF"),
        alignment=ft.Alignment.CENTER,
        animate_scale=ft.Animation(duration=900, curve=ft.AnimationCurve.EASE_IN_OUT),
        scale=0.94,
        content=ft.Container(
            width=82, height=82, alignment=ft.Alignment.CENTER,
            bgcolor=COLOR_END, border_radius=24,
            shadow=ft.BoxShadow(blur_radius=30, spread_radius=2, color="#55AE3044"),
            content=ft.Icon(ft.Icons.VERIFIED_USER, size=48, color=ft.Colors.WHITE),
        ),
    )

    # Build Splash UI
    page.add(
        ft.SafeArea(
            expand=True,
            content=ft.Container(
                expand=True,
                alignment=ft.Alignment.CENTER,
                gradient=ft.RadialGradient(
                    center=ft.Alignment.CENTER,
                    radius=1.2,
                    colors=["#FFFFFF", "#FAF6F7", "#F2E7EA"],
                ),
                content=ft.Column(
                    tight=True,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=12,
                    controls=[
                        shield_glow,
                        title,
                        ft.Text(
                            "TAG-BASED AUTHENTICATION GATEWAY",
                            size=12,
                            color=INK,
                            weight=ft.FontWeight.BOLD,
                        ),
                        ft.Text(
                            "Emergency Alert Platform",
                            size=15,
                            color=COLOR_END,
                            weight=ft.FontWeight.W_600,
                        ),
                        ft.Container(height=10),
                        progress,
                        status_text,
                        ft.Container(height=8),
                        ft.Container(
                            padding=ft.Padding.symmetric(horizontal=18, vertical=9),
                            bgcolor="#FFFFFF",
                            border=ft.Border.all(1, "#E9DFE2"),
                            border_radius=30,
                            content=ft.Text(
                                "St. Mary's Academy of Palo, Leyte, Inc.",
                                size=11,
                                color=MUTED,
                                weight=ft.FontWeight.BOLD,
                            ),
                        ),
                    ],
                ),
            ),
        )
    )

    # 1. Animate Title
    async def pulse_shield():
        while True:
            shield_glow.scale = 1.08
            try:
                shield_glow.update()
            except RuntimeError:
                return
            await asyncio.sleep(0.9)
            shield_glow.scale = 0.94
            try:
                shield_glow.update()
            except RuntimeError:
                return
            await asyncio.sleep(0.9)

    shield_animation = page.run_task(pulse_shield)

    for cell, _ in title_cells:
        cell.opacity = 1
        cell.scale = 1.0
        page.update()
        await asyncio.sleep(0.055)

    # 2. Animate Progress and RUN CHECKS
    total_steps = 24
    previous_index = None
    errors = []

    for step in range(total_steps):
        current_index = step % len(title_cells)
        if previous_index is not None:
            previous_cell, previous_glow = title_cells[previous_index]
            previous_cell.scale = 1.0
            previous_glow.opacity = 0

        current_cell, current_glow = title_cells[current_index]
        current_cell.scale = 1.16
        current_glow.opacity = 1
        progress.value = (step + 1) / total_steps

        # Trigger the health check on step 5
        if step == 4:
            status_text.value = "Checking database integrity..."
            page.update()
        elif step == 10:
            status_text.value = "Repairing missing records and directories..."
            page.update()
        elif step == 16:
            status_text.value = "Verifying RFID, GSM, and application source..."
            page.update()

        if step == 6:
            errors = await asyncio.to_thread(run_preflight_checks)

        page.update()
        previous_index = current_index
        await asyncio.sleep(0.085)

    # 3. Finish and Route
    progress.value = 1
    page.update()
    await asyncio.sleep(0.3)

    if errors:
        status_text.value = "Boot failed. Please contact admin."
        status_text.color = "red"
        page.update()
        def continue_with_warning(_):
            page.pop_dialog()
            shield_animation.cancel()
            page.clean()
            AppRouter(page)

        error_controls = [
            ft.Container(
                padding=10,
                bgcolor="#FDEBEC",
                border_radius=10,
                content=ft.Text(f"• {error}", size=12, color=COLOR_END),
            )
            for error in errors
        ]
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Row(tight=True, spacing=8, controls=[
                ft.Icon(ft.Icons.ERROR_OUTLINE, color=COLOR_END),
                ft.Text("System needs attention", size=18, weight=ft.FontWeight.BOLD),
            ]),
            content=ft.Container(
                width=520,
                content=ft.Column(tight=True, spacing=8, controls=[
                    ft.Text(
                        "T.A.G.A.P. could not automatically resolve these issues:",
                        size=12,
                        color=MUTED,
                    ),
                    *error_controls,
                ]),
            ),
            actions=[
                ft.TextButton(content="Exit kiosk", on_click=lambda _: page.window.close()),
                ft.TextButton(content="Continue anyway", on_click=continue_with_warning),
            ],
        )
        page.show_dialog(dialog)
    else:
        # Success! Load the Kiosk
        shield_animation.cancel()
        page.clean()
        AppRouter(page)


def main(page: ft.Page):
    # --- KIOSK CONFIGURATION ---
    page.title = "T.A.G.A.P."
    page.padding = 0
    page.spacing = 0
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = "#F7F6F5"

    # Make the app fullscreen immediately
    page.window.full_screen = True

    # Start the async boot sequence
    page.run_task(run_boot_sequence, page)


if __name__ == "__main__":
    ft.run(main)