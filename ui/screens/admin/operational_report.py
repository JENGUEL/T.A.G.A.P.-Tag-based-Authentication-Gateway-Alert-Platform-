"""Admin screen for generating Instrument 1 reports and raw-data workbooks."""

from __future__ import annotations

import asyncio
import logging
import webbrowser
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

import flet as ft

from config import PROJECT_ROOT
from data import queries
from data.research_reports import REPORT_TIMEZONE, get_operational_report_data
from services.operational_report_service import generate_operational_pdf
from services.operational_workbook_service import generate_operational_workbook
from ui.components.toast import Toast
from ui.screens.admin.shell import build_admin_shell
from ui.theme import BORDER_COLOR, CARD_WHITE, INK, MUTED, PRIMARY_RED, SUCCESS_GREEN

logger = logging.getLogger(__name__)
CANVAS = "#F7F5F4"
PALE_RED = "#FBE9EC"
PALE_GREEN = "#E8F5F0"


def build_operational_report(
    page: ft.Page,
    room_id: int,
    on_navigate: Callable[[str], None],
    on_exit: Callable[[], None],
) -> ft.View:
    today = datetime.now(REPORT_TIMEZONE).date()
    room_info = queries.get_room_info(room_id)
    start_date = ft.TextField(
        label="From",
        value=today.replace(day=1).isoformat(),
        hint_text="YYYY-MM-DD",
        width=170,
        dense=True,
    )
    end_date = ft.TextField(
        label="To",
        value=today.isoformat(),
        hint_text="YYYY-MM-DD",
        width=170,
        dense=True,
    )
    status_text = ft.Text(
        "Choose a period to build a PDF report and an auditable Excel workbook.",
        size=11,
        color=MUTED,
    )
    output_text = ft.Text("", size=10, color=INK, selectable=True)
    progress_ring = ft.ProgressRing(
        width=14,
        height=14,
        stroke_width=2,
        visible=False,
        color=PRIMARY_RED,
    )
    generated_pdf: Path | None = None
    generated_workbook: Path | None = None

    metrics = {
        "scans": ft.Text("--", size=23, weight=ft.FontWeight.BOLD, color=INK),
        "confirmations": ft.Text("--", size=23, weight=ft.FontWeight.BOLD, color=INK),
        "sms": ft.Text("--", size=23, weight=ft.FontWeight.BOLD, color=INK),
        "success_rate": ft.Text("--", size=23, weight=ft.FontWeight.BOLD, color=INK),
    }
    metric_details = {
        "scans": ft.Text("Awaiting report data", size=9, color=MUTED),
        "confirmations": ft.Text("Confirmed · cancelled · timed out", size=9, color=MUTED),
        "sms": ft.Text("Sent · failed · pending", size=9, color=MUTED),
        "success_rate": ft.Text("Modem acknowledgement, not receipt", size=9, color=MUTED),
    }
    latency_text = ft.Text(
        "Latency metrics will appear after generation.",
        size=10,
        color=MUTED,
    )
    dataset_text = ft.Text(
        "Workbook tabs: RFID Events · RFID Cards · Alerts · SMS Queue · SMS Attempts · "
        "Audit Trail · Analytics · Latency · Summary",
        size=10,
        color=MUTED,
    )

    def metric_card(label: str, key: str, icon: str) -> ft.Control:
        return ft.Container(
            col={"xs": 6, "md": 3},
            padding=ft.Padding.all(12),
            bgcolor=CARD_WHITE,
            border=ft.Border.all(1, BORDER_COLOR),
            border_radius=10,
            content=ft.Row(
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Container(
                        width=34,
                        height=34,
                        alignment=ft.Alignment.CENTER,
                        border_radius=9,
                        bgcolor=PALE_RED,
                        content=ft.Icon(icon, size=17, color=PRIMARY_RED),
                    ),
                    ft.Column(
                        tight=True,
                        spacing=1,
                        controls=[
                            ft.Text(label, size=9, color=MUTED),
                            metrics[key],
                            metric_details[key],
                        ],
                    ),
                ],
            ),
        )

    def show_summary(report: dict[str, Any]):
        rfid = report["rfid"]
        sms = report["sms"]
        metrics["scans"].value = str(rfid["scans_detected"])
        metrics["confirmations"].value = str(rfid["confirmed"])
        metrics["sms"].value = str(sms["sent"])
        metrics["success_rate"].value = (
            f"{sms['success_rate']:.1f}%" if sms["success_rate"] is not None else "N/A"
        )
        metric_details["scans"].value = f"{rfid['cards_identified']} identified"
        metric_details["confirmations"].value = (
            f"{rfid['cancelled']} cancelled · {rfid['timed_out']} timed out"
        )
        metric_details["sms"].value = f"{sms['failed']} failed · {sms['pending']} pending"
        metric_details["success_rate"].value = "Based on completed modem submissions"

        latency = report["latency"]
        latency_items = (
            ("Scan → identify", latency["scan_to_authentication"]),
            ("Confirm → queue", latency["confirmation_to_queue"]),
            ("Confirm → dispatch", latency["confirmation_to_dispatch"]),
            ("Dispatch → modem result", latency["dispatch_to_modem_result"]),
        )
        latency_text.value = "   |   ".join(
            f"{label}: {summary['mean_ms']:.1f} ms (n={summary['samples']})"
            if summary["samples"]
            else f"{label}: not captured"
            for label, summary in latency_items
        )
        raw = report["raw_data"]
        dataset_text.value = (
            f"Exported records — RFID events: {len(raw['rfid_events'])} · "
            f"registered cards: {len(raw['rfid_cards'])} · "
            f"Alerts: {len(raw['alerts'])} · SMS queue: {len(raw['sms_queue'])} · "
            f"SMS attempts: {len(raw['sms_attempts'])} · Audit events: {len(raw['audit_events'])} · "
            f"Analytics: {len(raw['analytics'])} · Scan latency rows: {len(raw['latency'])}"
        )

    async def generate(_):
        nonlocal generated_pdf, generated_workbook
        try:
            start = date.fromisoformat((start_date.value or "").strip())
            end = date.fromisoformat((end_date.value or "").strip())
            if start > end:
                raise ValueError("The start date must be on or before the end date.")
        except ValueError as exc:
            Toast.show(page, f"Check the reporting dates: {exc}", "error")
            return

        generate_button.disabled = True
        pdf_button.disabled = True
        workbook_button.disabled = True
        progress_ring.visible = True
        status_text.value = "Reading operational records and generating both files..."
        status_text.color = PRIMARY_RED
        output_text.value = ""
        page.update()
        try:
            report, generated_pdf, generated_workbook = await asyncio.to_thread(
                _generate_report_bundle,
                room_id,
                start,
                end,
            )
        except Exception as exc:
            logger.exception(
                "Could not generate operational report package for room %s",
                room_id,
            )
            status_text.value = f"Generation failed: {exc}"
            status_text.color = PRIMARY_RED
            generated_pdf = None
            generated_workbook = None
            Toast.show(page, f"Could not generate reports: {exc}", "error")
        else:
            show_summary(report)
            status_text.value = "PDF and Excel workbook generated from the same data snapshot."
            status_text.color = SUCCESS_GREEN
            output_text.value = (
                f"Saved to data/generated_reports · {start.isoformat()} through {end.isoformat()}"
            )
            pdf_button.disabled = False
            workbook_button.disabled = False
            Toast.show(page, "PDF and raw-data Excel workbook generated.", "success")
        finally:
            generate_button.disabled = False
            progress_ring.visible = False
            page.update()

    def open_file(path: Path | None, file_type: str):
        if path is None or not path.is_file():
            Toast.show(page, f"Generate the {file_type} before opening it.", "warning")
            return
        try:
            opened = webbrowser.open(path.resolve().as_uri())
        except Exception as exc:
            logger.exception("Could not open generated %s: %s", file_type, path)
            Toast.show(page, f"Could not open {file_type}: {exc}", "error")
            return
        if not opened:
            logger.error("No application accepted %s URL %s", file_type, path)
            Toast.show(page, f"No application could open the {file_type}.", "error")

    generate_button = ft.Button(
        content="Generate PDF + Excel",
        icon=ft.Icons.FILE_DOWNLOAD_OUTLINED,
        on_click=generate,
    )
    pdf_button = ft.OutlinedButton(
        content="Open PDF",
        icon=ft.Icons.PICTURE_AS_PDF,
        disabled=True,
        on_click=lambda _: open_file(generated_pdf, "PDF"),
    )
    workbook_button = ft.OutlinedButton(
        content="Open Excel",
        icon=ft.Icons.TABLE_VIEW,
        disabled=True,
        on_click=lambda _: open_file(generated_workbook, "Excel workbook"),
    )

    content = ft.Column(
        expand=True,
        scroll=ft.ScrollMode.AUTO,
        spacing=12,
        controls=[
            ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Column(
                        tight=True,
                        spacing=2,
                        controls=[
                            ft.Text(
                                "Emergency Report",
                                size=23,
                                weight=ft.FontWeight.BOLD,
                                color=INK,
                            ),
                            ft.Text(
                                "Research Instrument 1 · Operational performance and source data",
                                size=10,
                                color=MUTED,
                            ),
                        ],
                    ),
                    ft.Container(
                        padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                        bgcolor=PALE_GREEN,
                        border_radius=20,
                        content=ft.Row(
                            tight=True,
                            spacing=6,
                            controls=[
                                ft.Icon(ft.Icons.VERIFIED_OUTLINED, size=13, color=SUCCESS_GREEN),
                                ft.Text(
                                    room_info.get("room_name", f"Room {room_id}"),
                                    size=10,
                                    color=SUCCESS_GREEN,
                                    weight=ft.FontWeight.W_600,
                                ),
                            ],
                        ),
                    ),
                ],
            ),
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=14, vertical=12),
                bgcolor=CARD_WHITE,
                border=ft.Border.all(1, BORDER_COLOR),
                border_radius=10,
                content=ft.Row(
                    wrap=True,
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Icon(ft.Icons.DATE_RANGE, size=17, color=PRIMARY_RED),
                        start_date,
                        end_date,
                        ft.Text(
                            "Asia/Manila · end date inclusive",
                            size=9,
                            color=MUTED,
                        ),
                        ft.Container(expand=True),
                        generate_button,
                        pdf_button,
                        workbook_button,
                    ],
                ),
            ),
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                bgcolor=PALE_RED,
                border=ft.Border.all(1, "#F4D9DE"),
                border_radius=9,
                content=ft.Row(
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Icon(ft.Icons.INFO_OUTLINE, size=15, color=PRIMARY_RED),
                        ft.Text(
                            "SMS response time ends at the modem result, not parent receipt. Queue status is a "
                            "generation-time snapshot; phone numbers are masked and RFID UIDs pseudonymized.",
                            size=9,
                            color=INK,
                            expand=True,
                        ),
                    ],
                ),
            ),
            ft.ResponsiveRow(
                spacing=10,
                run_spacing=10,
                controls=[
                    metric_card("RFID scans", "scans", ft.Icons.CONTACTLESS),
                    metric_card("Confirmed alerts", "confirmations", ft.Icons.CHECK_CIRCLE_OUTLINE),
                    metric_card("SMS acknowledged", "sms", ft.Icons.SMS_OUTLINED),
                    metric_card("Transmission success", "success_rate", ft.Icons.QUERY_STATS),
                ],
            ),
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=14, vertical=10),
                bgcolor=CARD_WHITE,
                border=ft.Border.all(1, BORDER_COLOR),
                border_radius=9,
                content=ft.Column(
                    tight=True,
                    spacing=6,
                    controls=[
                        ft.Text(
                            "Response-time checks",
                            size=11,
                            weight=ft.FontWeight.W_600,
                            color=INK,
                        ),
                        latency_text,
                    ],
                ),
            ),
            ft.Container(
                padding=ft.Padding.symmetric(horizontal=14, vertical=10),
                bgcolor=CARD_WHITE,
                border=ft.Border.all(1, BORDER_COLOR),
                border_radius=9,
                content=ft.Column(
                    tight=True,
                    spacing=6,
                    controls=[
                        ft.Text(
                            "Excel workbook contents",
                            size=11,
                            weight=ft.FontWeight.W_600,
                            color=INK,
                        ),
                        dataset_text,
                        ft.Text(
                            "Raw records and per-attempt timings are followed by a final Summary tab "
                            "with reconciliation checks. SMS text is retained for local review; RSSI and "
                            "raw serial bytes are not captured.",
                            size=9,
                            color=MUTED,
                        ),
                    ],
                ),
            ),
            ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    progress_ring,
                    status_text,
                    output_text,
                ],
            ),
        ],
    )
    return build_admin_shell(
        page,
        active_page="Emergency Report",
        room_name=room_info.get("room_name", f"Room {room_id}"),
        on_navigate=on_navigate,
        on_back_to_kiosk=on_exit,
        content=content,
    )


def _generate_report_bundle(room_id: int, start: date, end: date):
    report = get_operational_report_data(room_id, start, end)
    output_directory = PROJECT_ROOT / "data" / "generated_reports"
    pdf_path = generate_operational_pdf(report, output_directory)
    workbook_path = generate_operational_workbook(report, output_directory)
    return report, pdf_path, workbook_path
