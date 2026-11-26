"""Generate formal PDF reports for Research Instrument 1."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (
    Flowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from config import PROJECT_ROOT, settings
from data.research_reports import get_operational_report_data

REPORT_TIMEZONE = timezone(timedelta(hours=8), "Asia/Manila")
INK = colors.HexColor("#20283A")
MUTED = colors.HexColor("#667085")
BRAND = colors.HexColor("#AE3044")
BLUE = colors.HexColor("#5269A3")
PALE = colors.HexColor("#F3F5F8")
GRID = colors.HexColor("#D7DCE4")


class HorizontalBarChart(Flowable):
    def __init__(self, entries: list[tuple[str, int]], color=BLUE):
        super().__init__()
        self.entries = entries
        self.bar_color = color
        self.height = max(28, 19 * len(entries) + 10)

    def wrap(self, avail_width, avail_height):
        self.width = avail_width
        return avail_width, self.height

    def draw(self):
        canvas = self.canv
        if not self.entries:
            canvas.setFont("Helvetica-Oblique", 8)
            canvas.setFillColor(MUTED)
            canvas.drawString(0, self.height - 12, "No observations in this period.")
            return

        label_width = min(130, self.width * 0.34)
        bar_x = label_width + 7
        value_width = 28
        bar_width = max(25, self.width - bar_x - value_width - 4)
        maximum = max((value for _, value in self.entries), default=0) or 1
        y = self.height - 14
        for label, value in self.entries:
            visible_label = label
            while stringWidth(visible_label, "Helvetica", 8) > label_width and len(
                visible_label
            ) > 4:
                visible_label = visible_label[:-4] + "..."
            canvas.setFont("Helvetica", 8)
            canvas.setFillColor(INK)
            canvas.drawString(0, y, visible_label)
            canvas.setFillColor(PALE)
            canvas.roundRect(bar_x, y - 3, bar_width, 8, 3, stroke=0, fill=1)
            if value:
                canvas.setFillColor(self.bar_color)
                canvas.roundRect(
                    bar_x,
                    y - 3,
                    max(3, bar_width * value / maximum),
                    8,
                    3,
                    stroke=0,
                    fill=1,
                )
            canvas.setFillColor(INK)
            canvas.drawRightString(self.width, y, str(value))
            y -= 19


def _format_percent(value: Any) -> str:
    return "Not available" if value is None else f"{value:.1f}%"


def _format_latency(summary: dict[str, Any]) -> str:
    if not summary["samples"]:
        return "Not available"
    return (
        f"Mean {summary['mean_ms']:,.1f} ms; median "
        f"{summary['median_ms']:,.1f} ms"
    )


def _p(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(text).replace("\n", "<br/>"), style)


def _header_footer(canvas, document):
    canvas.saveState()
    left = document.leftMargin
    right = A4[0] - document.rightMargin
    top = A4[1] - 25 * mm

    shield = canvas.beginPath()
    shield.moveTo(left, top + 8)
    shield.lineTo(left + 20, top + 8)
    shield.lineTo(left + 19, top - 4)
    shield.curveTo(left + 18, top - 12, left + 10, top - 17, left + 10, top - 17)
    shield.curveTo(left + 10, top - 17, left + 2, top - 12, left + 1, top - 4)
    shield.close()
    canvas.setFillColor(BRAND)
    canvas.drawPath(shield, stroke=0, fill=1)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawCentredString(left + 10, top - 5, "T")

    canvas.setFillColor(INK)
    canvas.setFont("Helvetica-Bold", 10)
    canvas.drawString(left + 27, top + 2, "T.A.G.A.P.")
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7)
    canvas.drawString(
        left + 27,
        top - 8,
        "TAG-BASED AUTHENTICATION GATEWAY ALERT PLATFORM",
    )
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawRightString(right, top + 1, "OPERATIONAL PERFORMANCE")
    canvas.setStrokeColor(GRID)
    canvas.setLineWidth(0.6)
    canvas.line(left, top - 22, right, top - 22)

    footer_y = 14 * mm
    canvas.line(left, footer_y + 9, right, footer_y + 9)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(left, footer_y, "Research Instrument 1 | Operational checklist")
    canvas.drawRightString(right, footer_y, f"Page {document.page}")
    canvas.restoreState()


def _build_story(report: dict[str, Any], generated_at: datetime):
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=25,
        alignment=TA_LEFT,
        textColor=INK,
        spaceAfter=5,
    )
    subtitle_style = ParagraphStyle(
        "ReportSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=MUTED,
        spaceAfter=10,
    )
    section_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        textColor=INK,
        spaceBefore=9,
        spaceAfter=6,
        keepWithNext=True,
    )
    body_style = ParagraphStyle(
        "ReportBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=INK,
        spaceAfter=5,
    )
    small_style = ParagraphStyle(
        "ReportSmall",
        parent=body_style,
        fontSize=7.5,
        leading=10,
        textColor=MUTED,
    )
    cell_style = ParagraphStyle(
        "TableCell",
        parent=body_style,
        fontSize=7.5,
        leading=10,
        spaceAfter=0,
    )
    header_style = ParagraphStyle(
        "TableHeader",
        parent=cell_style,
        fontName="Helvetica-Bold",
        textColor=colors.white,
    )
    metadata_label_style = ParagraphStyle(
        "MetadataLabel",
        parent=cell_style,
        fontName="Helvetica-Bold",
        textColor=INK,
    )

    room = report["room"]
    period = report["period"]
    rfid = report["rfid"]
    sms = report["sms"]
    latency = report["latency"]
    generated_label = generated_at.strftime("%B %d, %Y %I:%M %p PHT")
    rfid_mode = "SIMULATION" if settings.USE_MOCK_RFID else "REAL HARDWARE"
    sms_mode = "SIMULATION" if settings.USE_MOCK_SMS else "REAL MODEM"

    story = [
        _p("Operational Performance Report", title_style),
        _p(
            "Research Instrument 1: Researcher-Administered Operational Performance Checklist",
            subtitle_style,
        ),
    ]

    metadata_rows = [
        ["School", str(room["school"]), "Reporting period", f"{period['start']} to {period['end']}"],
        [
            "Room",
            f"{room['name']} | {room['section'] or 'Section not set'}",
            "Generated",
            generated_label,
        ],
        [
            "Location",
            " | ".join(
                part for part in (str(room["wing"]), str(room["floor"])) if part
            )
            or "Not set",
            "Test mode",
            f"RFID: {rfid_mode}; SMS: {sms_mode}",
        ],
    ]
    metadata = Table(
        [
            [
                _p(row[0], metadata_label_style),
                _p(row[1], cell_style),
                _p(row[2], metadata_label_style),
                _p(row[3], cell_style),
            ]
            for row in metadata_rows
        ],
        colWidths=[22 * mm, 59 * mm, 27 * mm, 59 * mm],
    )
    metadata.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), PALE),
                ("BACKGROUND", (2, 0), (2, -1), PALE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.4, GRID),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.extend(
        [
            metadata,
            Spacer(1, 8),
            _p(
                "Scope: This report contains automated operational measurements for Instrument 1 only. "
                "It does not include Instrument 2 student questionnaire responses.",
                body_style,
            ),
            _p(
                "Results are calculated from TAGAP's local event log, alert records, and SMS queue. "
                "No student or parent survey data is collected in this report.",
                body_style,
            ),
            _p("Part I - Features of the T.A.G.A.P. System", section_style),
        ]
    )

    def rate_text(numerator, denominator, percentage):
        if percentage is None:
            return f"{numerator} of {denominator}; rate not available"
        return f"{numerator} of {denominator} ({percentage:.1f}%)"

    cancelled = int(rfid["cancelled"])
    queued_after_cancel = int(rfid["cancelled_with_sms_queued"])
    if not cancelled:
        cancellation_result = "No cancellation trials recorded in this period"
    elif queued_after_cancel == 0:
        cancellation_result = (
            f"0 SMS queues across {cancelled} cancelled scan"
            f"{'s' if cancelled != 1 else ''}"
        )
    else:
        cancellation_result = (
            f"{queued_after_cancel} cancelled scan(s) had an SMS queue; investigate"
        )

    checklist_rows = [
        ["Performance indicator", "Recorded result"],
        ["Successful detection of scanned RFID card", str(rfid["scans_detected"])],
        [
            "Correct identification of corresponding card",
            rate_text(
                int(rfid["cards_identified"]),
                int(rfid["scans_detected"]),
                rfid["identification_rate"],
            ),
        ],
        [
            "Activation of confirmation interface after scanning",
            str(rfid["confirmation_interfaces"]),
        ],
        ["Successful confirmation of selected notification", str(rfid["confirmed"])],
        ["Cancellation of an unintended RFID scan", str(cancelled)],
        ["Prevention of SMS queueing after cancellation", cancellation_result],
    ]
    story.append(
        _table(
            checklist_rows,
            [105 * mm, 62 * mm],
            header_style,
            cell_style,
        )
    )

    story.append(_p("Part II - Operational Performance", section_style))
    story.append(_p("A. End-to-end latency", section_style))
    latency_rows = [
        ["Performance indicator", "Mean / median", "Samples"],
        [
            "Scan to card authentication",
            _format_latency(latency["scan_to_authentication"]),
            str(latency["scan_to_authentication"]["samples"]),
        ],
        [
            "Confirmation to SMS preparation / queue",
            _format_latency(latency["confirmation_to_queue"]),
            str(latency["confirmation_to_queue"]["samples"]),
        ],
        [
            "Confirmation to SMS dispatch start",
            _format_latency(latency["confirmation_to_dispatch"]),
            str(latency["confirmation_to_dispatch"]["samples"]),
        ],
        [
            "SMS dispatch to modem result",
            _format_latency(latency["dispatch_to_modem_result"]),
            str(latency["dispatch_to_modem_result"]["samples"]),
        ],
        [
            "SMS dispatch to receipt by parent",
            "Not captured by the current modem integration",
            "0",
        ],
    ]
    story.append(_table(latency_rows, [71 * mm, 77 * mm, 19 * mm], header_style, cell_style))

    story.extend(
        [
            Spacer(1, 5),
            _p(
                str(sms["receipt_time_note"]),
                small_style,
            ),
            _p("B. SMS transmission reliability", section_style),
        ]
    )
    completed = int(sms["sent"]) + int(sms["failed"])
    consistency = report["trial_success_rate_consistency"]
    consistency_text = "Not available"
    if consistency["mean_percent"] is not None:
        consistency_text = (
            f"Mean {consistency['mean_percent']:.1f}% "
            f"(SD {consistency['stddev_percent']:.1f} percentage points; "
            f"{consistency['trials_with_completed_messages']} trials)"
        )
    sms_rows = [
        ["Measure", "Recorded result"],
        ["Recipient messages queued", str(sms["recipient_count"])],
        ["Successful modem acknowledgements", str(sms["sent"])],
        ["Failed transmissions", str(sms["failed"])],
        ["Pending / retrying messages", str(sms["pending"])],
        [
            "Overall transmission success rate",
            f"{sms['success_rate']:.1f}% of {completed} completed messages"
            if sms["success_rate"] is not None
            else "Not available; no completed messages",
        ],
        ["Consistency across repeated trials", consistency_text],
    ]
    story.append(_table(sms_rows, [75 * mm, 92 * mm], header_style, cell_style))

    type_entries = [
        (str(card_type), int(count))
        for card_type, count in sorted(report["alerts_by_type"].items())
    ]
    outcome_entries = [
        ("Successful", int(sms["sent"])),
        ("Failed", int(sms["failed"])),
        ("Pending", int(sms["pending"])),
    ]
    story.extend(
        [
            _p("Visual summary", section_style),
            KeepTogether(
                [
                    _p("Confirmed RFID alert trials by type", body_style),
                    HorizontalBarChart(type_entries, BRAND),
                ]
            ),
            Spacer(1, 5),
            KeepTogether(
                [
                    _p("SMS transmission outcomes by recipient message", body_style),
                    HorizontalBarChart(outcome_entries, BLUE),
                ]
            ),
        ]
    )

    trial_rows = [
        [
            "Trial date",
            "Type",
            "Recipients",
            "Sent",
            "Failed",
            "Pending",
            "Success rate",
        ]
    ]
    for trial in report["trials"]:
        triggered = trial["triggered_at"]
        if triggered.tzinfo is None:
            triggered = triggered.replace(tzinfo=timezone.utc)
        local_time = triggered.astimezone(REPORT_TIMEZONE)
        trial_rows.append(
            [
                local_time.strftime("%Y-%m-%d %H:%M"),
                str(trial["card_type"]),
                str(trial["recipient_count"]),
                str(trial["sent"]),
                str(trial["failed"]),
                str(trial["pending"]),
                _format_percent(trial["success_rate"]),
            ]
        )
    if len(trial_rows) == 1:
        trial_rows.append(["No alert trials in this period", "", "", "", "", "", ""])
    story.extend(
        [
            _p("Repeated-trial results", section_style),
            _table(
                trial_rows,
                [31 * mm, 18 * mm, 20 * mm, 18 * mm, 18 * mm, 19 * mm, 23 * mm],
                header_style,
                cell_style,
            ),
            Spacer(1, 7),
            _p(
                "Interpretation note: a successful modem acknowledgement confirms the local SMS submission "
                "was accepted for sending; it is not proof of receipt by a parent. Pending messages are "
                "excluded from the overall success-rate denominator. Modem signal strength (RSSI) is not "
                "captured by the current application. SMS status is the current queue state at report "
                "generation; related message outcomes can occur outside the selected alert-trigger dates.",
                small_style,
            ),
        ]
    )
    return story


def _table(rows, widths, header_style, cell_style):
    data = [
        [
            _p(str(value), header_style if row_index == 0 else cell_style)
            for value in row
        ]
        for row_index, row in enumerate(rows)
    ]
    table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), INK),
                ("GRID", (0, 0), (-1, -1), 0.4, GRID),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
            ]
        )
    )
    return table


def generate_operational_pdf(
    report: dict[str, Any],
    output_directory: Path,
) -> Path:
    output_directory.mkdir(parents=True, exist_ok=True)
    room = report["room"]
    period = report["period"]
    room_slug = re.sub(r"[^A-Za-z0-9_-]+", "-", str(room["room_number"])).strip("-")
    generated_at = report.get("generated_at")
    if not isinstance(generated_at, datetime):
        generated_at = datetime.now(REPORT_TIMEZONE)
    generated_stamp = generated_at.strftime("%Y%m%d-%H%M%S-%f")
    output_path = output_directory / (
        f"TAGAP-Operational-Report-Room-{room_slug or room['id']}-"
        f"{period['start']}-to-{period['end']}-{generated_stamp}.pdf"
    )
    document = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=31 * mm,
        bottomMargin=23 * mm,
        title="T.A.G.A.P. Operational Performance Report",
        author="T.A.G.A.P.",
        subject="Research Instrument 1 - Operational Performance Checklist",
    )
    document.build(
        _build_story(report, generated_at),
        onFirstPage=_header_footer,
        onLaterPages=_header_footer,
    )
    return output_path


def generate_operational_report(
    room_id: int,
    start_date: date,
    end_date: date,
) -> Path:
    data = get_operational_report_data(room_id, start_date, end_date)
    return generate_operational_pdf(
        data,
        PROJECT_ROOT / "data" / "generated_reports",
    )
