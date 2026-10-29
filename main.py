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
        base = ft.Text(character, size=30, weight=ft.FontWeight.BOLD, color=INK)
        shine = ft.Text(
            character, size=30, weight=ft.FontWeight.BOLD, color=COLOR_START, opacity=0,
            animate_opacity=ft.Animation(duration=200, curve=ft.AnimationCurve.EASE_IN_OUT),
        )
        cell = ft.Container(
            width=11 if character == "." else 24, height=48, alignment=ft.Alignment.CENTER,
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
        width=144, value=0, color=COLOR_END, bgcolor="#E5E0E2", bar_height=3, border_radius=3,
    )
    status_text = ft.Text("Initializing secure gateway...", size=9, color=MUTED)

    # Build Splash UI
    page.add(
        ft.SafeArea(
            expand=True,
            content=ft.Container(
                expand=True, alignment=ft.Alignment.CENTER, bgcolor="#F7F6F5",
                content=ft.Column(
                    tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10,
                    controls=[
                        ft.Container(width=44, height=48, alignment=ft.Alignment.CENTER, bgcolor=COLOR_END,
                                     border_radius=12,
                                     content=ft.Icon(ft.Icons.VERIFIED_USER, size=25, color=ft.Colors.WHITE)),
                        title,
                        ft.Text("Tag-based Authentication Gateway Alert Platform", size=10, color=MUTED),
                        ft.Container(height=8),
                        progress,
                        status_text,
                    ],
                ),
            ),
        )
    )

    # 1. Animate Title
    for cell, _ in title_cells:
        cell.opacity = 1
        cell.scale = 1.0
        page.update()
        await asyncio.sleep(0.075)

    # 2. Animate Progress and RUN CHECKS
    total_steps = 20
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
        if step == 5:
            status_text.value = "Running diagnostics..."
            page.update()
            # Run in background thread so UI doesn't freeze
            errors = await asyncio.to_thread(run_preflight_checks)

        page.update()
        previous_index = current_index
        await asyncio.sleep(0.1)

    # 3. Finish and Route
    progress.value = 1
    page.update()
    await asyncio.sleep(0.3)

    if errors:
        # Show Error Toast and stay on splash
        status_text.value = "Boot failed. Please contact admin."
        status_text.color = "red"
        page.update()
        for err in errors:
            page.overlay.append(ft.SnackBar(ft.Text(f"❌ {err}", color="white"), bgcolor="red", open=True))
            page.update()
            await asyncio.sleep(1.5)  # Give user time to read the error
    else:
        # Success! Load the Kiosk
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