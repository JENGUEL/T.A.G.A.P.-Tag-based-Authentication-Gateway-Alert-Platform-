"""Export auditable Instrument 1 source records to a formatted Excel workbook."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from config import PROJECT_ROOT
from data.research_reports import REPORT_TIMEZONE

INK = "20283A"
MUTED = "667085"
BRAND = "AE3044"
BLUE = "5269A3"
PALE = "F3F5F8"
GRID = "D7DCE4"
WHITE = "FFFFFF"
GREEN = "2D806B"
RED = "B54747"
AMBER = "A96C20"

_RFID_EVENT_TYPES = {
    "RFID_SCAN_DETECTED",
    "CARD_SCANNED",
    "CARD_REJECTED_DUPLICATE",
    "ADMIN_ACCESS",
    "CONFIRMATION_SHOWN",
    "ALERT_CONFIRMED",
    "ALERT_CANCELLED",
    "CONFIRMATION_TIMEOUT",
}


def _utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    aware = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    return aware.astimezone(timezone.utc).replace(tzinfo=None)


def _local_datetime(value: datetime | None) -> datetime | None:
    utc_value = _utc_datetime(value)
    if utc_value is None:
        return None
    return utc_value.replace(tzinfo=timezone.utc).astimezone(REPORT_TIMEZONE).replace(
        tzinfo=None
    )


def _uid_reference(value: Any) -> str:
    if value is None or value == "":
        return ""
    digest = hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:12].upper()
    return f"RFID-{digest}"


def _mask_phone(value: Any) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if not digits:
        return ""
    return f"****{digits[-4:]}" if len(digits) > 4 else "****"


def _safe_payload(value: Any) -> Any:
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            normalized_key = str(key).lower()
            if "phone" in normalized_key:
                redacted[key] = _mask_phone(item)
            elif normalized_key in {"uid", "card_uid"}:
                redacted[key] = _uid_reference(item)
            else:
                redacted[key] = _safe_payload(item)
        return redacted
    if isinstance(value, list):
        return [_safe_payload(item) for item in value]
    return value


def _excel_safe(value: Any) -> Any:
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def _json_text(value: Any) -> str:
    return json.dumps(_safe_payload(value), ensure_ascii=False, sort_keys=True, default=str)


def _timestamp_pair(value: datetime | None) -> tuple[datetime | None, datetime | None]:
    return _utc_datetime(value), _local_datetime(value)


def _build_rfid_rows(raw: dict[str, Any]) -> list[list[Any]]:
    headers = [
        "Audit ID",
        "Timestamp (UTC)",
        "Timestamp (Asia/Manila)",
        "Event",
        "Scan ID",
        "Card type",
        "Card UID reference (pseudonymized)",
        "Event payload (phone/UID fields masked)",
    ]
    rows = []
    for event in raw["rfid_events"]:
        payload = event["payload"] or {}
        uid = payload.get("uid", payload.get("card_uid"))
        rows.append(
            [
                event["event_id"],
                *_timestamp_pair(event["created_at"]),
                event["event_type"],
                payload.get("scan_id"),
                payload.get("card_type"),
                _uid_reference(uid),
                _json_text(payload) if payload else event["payload_error"],
            ]
        )
    return [headers, *rows]


def _build_alert_rows(raw: dict[str, Any]) -> list[list[Any]]:
    headers = [
        "Alert ID",
        "Room ID",
        "Card type",
        "Card UID reference (pseudonymized)",
        "Triggered (UTC)",
        "Triggered (Asia/Manila)",
        "Confirmed (UTC)",
        "Confirmed (Asia/Manila)",
        "Confirmation response time (ms)",
        "Created (UTC)",
        "Updated (UTC)",
    ]
    rows = []
    for alert in raw["alerts"]:
        triggered = alert["triggered_at"]
        confirmed = alert["confirmed_at"]
        response_ms = None
        if triggered and confirmed:
            response_ms = max(
                0,
                int(
                    (
                        _utc_datetime(confirmed) - _utc_datetime(triggered)
                    ).total_seconds()
                    * 1000
                ),
            )
        rows.append(
            [
                alert["id"],
                alert["room_id"],
                alert["card_type"],
                _uid_reference(alert["card_uid"]),
                *_timestamp_pair(triggered),
                *_timestamp_pair(confirmed),
                response_ms,
                _utc_datetime(alert["created_at"]),
                _utc_datetime(alert["updated_at"]),
            ]
        )
    return [headers, *rows]


def _build_card_rows(raw: dict[str, Any]) -> list[list[Any]]:
    headers = [
        "Card ID",
        "Room ID",
        "Card type",
        "Active",
        "Card UID reference (pseudonymized)",
        "Created (UTC)",
        "Updated (UTC)",
    ]
    rows = [
        [
            card["id"],
            card["room_id"],
            card["card_type"],
            card["active"],
            _uid_reference(card["uid"]),
            _utc_datetime(card["created_at"]),
            _utc_datetime(card["updated_at"]),
        ]
        for card in raw["rfid_cards"]
    ]
    return [headers, *rows]


def _build_sms_rows(raw: dict[str, Any]) -> list[list[Any]]:
    headers = [
        "SMS ID",
        "Alert ID",
        "Recipient type",
        "Recipient phone (last 4 only)",
        "SMS message text",
        "Message characters",
        "Queue status",
        "Attempts",
        "Failure reason",
        "Queued (UTC)",
        "Queued (Asia/Manila)",
        "Updated (UTC)",
        "Sent / modem acknowledged (UTC)",
        "Sent / modem acknowledged (Asia/Manila)",
        "Next attempt (UTC)",
    ]
    rows = []
    for sms in raw["sms_queue"]:
        message = str(sms["message"] or "")
        rows.append(
            [
                sms["id"],
                sms["alert_id"],
                sms["recipient_type"],
                _mask_phone(sms["phone_number"]),
                message,
                len(message),
                sms["status"],
                sms["attempts"],
                sms["failure_reason"],
                *_timestamp_pair(sms["created_at"]),
                _utc_datetime(sms["updated_at"]),
                *_timestamp_pair(sms["sent_at"]),
                _utc_datetime(sms["next_attempt_at"]),
            ]
        )
    return [headers, *rows]


def _build_attempt_rows(raw: dict[str, Any]) -> list[list[Any]]:
    headers = [
        "SMS ID",
        "Alert ID",
        "Recipient type",
        "Attempt",
        "Dispatch event ID",
        "Dispatch audit time (UTC)",
        "Dispatch audit time (Asia/Manila)",
        "Send call started (UTC)",
        "Send call started (Asia/Manila)",
        "Result event ID",
        "Modem result event",
        "Result time (UTC)",
        "Result time (Asia/Manila)",
        "Response time (ms)",
        "Audit timestamp delta (ms)",
        "Timing source",
    ]
    rows = []
    for attempt in raw["sms_attempts"]:
        rows.append(
            [
                attempt["sms_id"],
                attempt["alert_id"],
                attempt["recipient_type"],
                attempt["attempt"],
                attempt["dispatch_event_id"],
                *_timestamp_pair(attempt["dispatch_started_at"]),
                *_timestamp_pair(attempt["send_started_at"]),
                attempt["outcome_event_id"],
                attempt["outcome_type"],
                *_timestamp_pair(attempt["outcome_at"]),
                attempt["response_time_ms"],
                attempt["audit_elapsed_ms"],
                attempt["response_time_source"],
            ]
        )
    return [headers, *rows]


def _build_audit_rows(raw: dict[str, Any]) -> list[list[Any]]:
    headers = [
        "Audit ID",
        "Timestamp (UTC)",
        "Timestamp (Asia/Manila)",
        "Event type",
        "Room ID",
        "Alert ID",
        "SMS ID",
        "Scan ID",
        "Payload (phone/UID fields masked)",
        "Payload status",
    ]
    rows = []
    for event in raw["audit_events"]:
        payload = event["payload"]
        payload = payload if isinstance(payload, dict) else {}
        sms_id = payload.get("sms_id", payload.get("id"))
        rows.append(
            [
                event["event_id"],
                *_timestamp_pair(event["created_at"]),
                event["event_type"],
                payload.get("room_id"),
                payload.get("alert_id"),
                sms_id,
                payload.get("scan_id"),
                _json_text(payload) if payload else "",
                event["payload_error"] or "OK",
            ]
        )
    return [headers, *rows]


def _build_analytics_rows(raw: dict[str, Any]) -> list[list[Any]]:
    headers = [
        "Analytics ID",
        "Alert ID",
        "Scan (UTC)",
        "Scan (Asia/Manila)",
        "Confirm (UTC)",
        "Confirm (Asia/Manila)",
        "Queue (UTC)",
        "Queue (Asia/Manila)",
        "Sent / modem ack (UTC)",
        "Sent / modem ack (Asia/Manila)",
        "Response time (ms; scan-to-confirm)",
        "Delivery time (ms; queue-to-modem-ack)",
    ]
    rows = []
    for item in raw["analytics"]:
        rows.append(
            [
                item["id"],
                item["alert_id"],
                *_timestamp_pair(item["scan_ts"]),
                *_timestamp_pair(item["confirm_ts"]),
                *_timestamp_pair(item["queue_ts"]),
                *_timestamp_pair(item["sent_ts"]),
                item["response_time_ms"],
                item["delivery_time_ms"],
            ]
        )
    return [headers, *rows]


def _build_latency_rows(raw: dict[str, Any]) -> list[list[Any]]:
    milestones = (
        ("detected_at", "Detected"),
        ("identified_at", "Identified"),
        ("confirmation_shown_at", "Confirmation shown"),
        ("confirmed_at", "Confirmed"),
        ("cancelled_at", "Cancelled"),
        ("timed_out_at", "Timed out"),
        ("queued_at", "SMS queued"),
        ("dispatch_started_at", "SMS dispatch started"),
    )
    headers = [
        "Scan ID",
        "Alert ID",
        "Card type",
        "Card UID reference (pseudonymized)",
        "Confirmation result",
    ]
    headers.extend(f"{label} (Asia/Manila)" for _, label in milestones)
    headers.extend(
        [
            "Scan to identification (ms)",
            "Confirmation to queue (ms)",
            "Confirmation to dispatch (ms)",
        ]
    )
    rows = []
    for item in raw["latency"]:
        rows.append(
            [
                item["scan_id"],
                item["alert_id"],
                item["card_type"],
                _uid_reference(item["card_uid"]),
                item["confirmation_result"],
                *[
                    _local_datetime(item[key])
                    for key, _ in milestones
                ],
                item["scan_to_identification_ms"],
                item["confirmation_to_queue_ms"],
                item["confirmation_to_dispatch_ms"],
            ]
        )
    return [headers, *rows]


def _write_data_sheet(
    workbook: Workbook,
    title: str,
    subtitle: str,
    report: dict[str, Any],
    rows: list[list[Any]],
    tab_color: str,
) -> Worksheet:
    sheet = workbook.create_sheet(title)
    sheet.sheet_view.showGridLines = False
    sheet.sheet_view.zoomScale = 85
    sheet.sheet_properties.tabColor = tab_color
    headers = rows[0]
    last_column = max(1, len(headers))
    sheet.column_dimensions["A"].width = 13
    sheet["A1"] = "T"
    sheet["A1"].fill = PatternFill("solid", fgColor=BRAND)
    sheet["A1"].font = Font(name="Calibri", size=16, bold=True, color=WHITE)
    sheet["A1"].alignment = Alignment(horizontal="center", vertical="center")
    if last_column > 1:
        sheet.merge_cells(
            start_row=1,
            start_column=2,
            end_row=1,
            end_column=last_column,
        )
    title_cell = sheet.cell(1, 2 if last_column > 1 else 1)
    title_cell.value = f"T.A.G.A.P. | RESEARCH INSTRUMENT 1 | {title.upper()}"
    title_cell.fill = PatternFill("solid", fgColor=INK)
    title_cell.font = Font(name="Calibri", size=13, bold=True, color=WHITE)
    title_cell.alignment = Alignment(vertical="center")
    if last_column > 1:
        sheet.merge_cells(start_row=2, start_column=1, end_row=2, end_column=last_column)
    sheet.cell(2, 1).value = subtitle
    sheet.cell(2, 1).font = Font(name="Calibri", size=10, color=INK)
    sheet.cell(2, 1).alignment = Alignment(wrap_text=True, vertical="center")
    if last_column > 1:
        sheet.merge_cells(start_row=3, start_column=1, end_row=3, end_column=last_column)
    period = report["period"]
    room = report["room"]
    generated_at = report.get("generated_at")
    if not isinstance(generated_at, datetime):
        generated_at = datetime.now(REPORT_TIMEZONE)
    sheet.cell(3, 1).value = (
        f"Room {room['room_number']} | {room['school']} | "
        f"{period['start']} to {period['end']} (Asia/Manila) | "
        f"Generated {generated_at:%Y-%m-%d %H:%M:%S} PHT | "
        "Phone numbers and RFID UIDs are masked/pseudonymized."
    )
    sheet.cell(3, 1).font = Font(name="Calibri", size=9, italic=True, color=MUTED)
    sheet.cell(3, 1).alignment = Alignment(wrap_text=True, vertical="center")
    sheet.row_dimensions[1].height = 25
    sheet.row_dimensions[2].height = 22
    sheet.row_dimensions[3].height = 25

    header_row = 4
    for column, header in enumerate(headers, 1):
        cell = sheet.cell(header_row, column, _excel_safe(str(header)))
        cell.fill = PatternFill("solid", fgColor=BLUE)
        cell.font = Font(name="Calibri", size=9, bold=True, color=WHITE)
        cell.alignment = Alignment(
            horizontal="left",
            vertical="center",
            wrap_text=True,
        )
        cell.border = Border(bottom=Side(style="thin", color=GRID))
    sheet.row_dimensions[header_row].height = 32

    for row_index, values in enumerate(rows[1:], header_row + 1):
        for column, value in enumerate(values, 1):
            cell = sheet.cell(row_index, column, _excel_safe(value))
            cell.font = Font(name="Calibri", size=9, color=INK)
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            if row_index % 2:
                cell.fill = PatternFill("solid", fgColor=PALE)
            if isinstance(value, datetime):
                cell.number_format = "yyyy-mm-dd hh:mm:ss.000"
            if isinstance(value, str):
                cell.number_format = "@"
        sheet.row_dimensions[row_index].height = 30 if any(
            isinstance(value, str) and len(value) > 80 for value in values
        ) else 20

    last_row = max(header_row, header_row + len(rows) - 1)
    if last_row > header_row:
        sheet.auto_filter.ref = f"A{header_row}:{get_column_letter(last_column)}{last_row}"
    sheet.freeze_panes = "A5"
    sheet.print_title_rows = "1:4"
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    for column, header in enumerate(headers, 1):
        values = [str(header)]
        values.extend(
            str(row[column - 1])
            for row in rows[1:min(len(rows), 20)]
            if row[column - 1] is not None
        )
        width = min(max(max(map(len, values), default=12) + 2, 12), 48)
        sheet.column_dimensions[get_column_letter(column)].width = width
    for index, header in enumerate(headers, 1):
        if "message" in str(header).lower() or "payload" in str(header).lower():
            sheet.column_dimensions[get_column_letter(index)].width = 54
    return sheet


def _summary_metrics(report: dict[str, Any]) -> list[tuple[str, Any, str]]:
    rfid = report["rfid"]
    sms = report["sms"]
    latency = report["latency"]
    response = latency["dispatch_to_modem_result"]
    return [
        ("RFID scans detected", rfid["scans_detected"], "Raw RFID_SCAN_DETECTED events"),
        (
            "Cards identified",
            rfid["cards_identified"],
            f"Identification rate: {_percent(rfid['identification_rate'])}",
        ),
        ("Confirmation interfaces shown", rfid["confirmation_interfaces"], "Audit events"),
        ("Confirmed / cancelled / timed out", f"{rfid['confirmed']} / {rfid['cancelled']} / {rfid['timed_out']}", "Audit events"),
        (
            "Cancelled scans with queued SMS",
            rfid["cancelled_with_sms_queued"],
            "Expected value: 0",
        ),
        ("SMS queued to recipients", sms["recipient_count"], "Raw SMS queue rows"),
        ("SMS modem acknowledgements", sms["sent"], "Not proof of recipient delivery"),
        ("SMS failed / pending", f"{sms['failed']} / {sms['pending']}", "Current queue state"),
        (
            "SMS transmission success rate",
            _percent(sms["success_rate"]),
            "Acknowledged / completed (sent + failed)",
        ),
        (
            "Scan to identification latency",
            _latency_text(latency["scan_to_authentication"]),
            "Observed event timestamp difference",
        ),
        (
            "Confirmation to queue latency",
            _latency_text(latency["confirmation_to_queue"]),
            "Observed event timestamp difference",
        ),
        (
            "Confirmation to dispatch latency",
            _latency_text(latency["confirmation_to_dispatch"]),
            "Observed event timestamp difference",
        ),
        (
            "Dispatch to modem result response time",
            _latency_text(response),
            "Worker-measured duration; not parent receipt time",
        ),
    ]


def _percent(value: Any) -> str:
    return "N/A" if value is None else f"{value:.1f}%"


def _latency_text(value: dict[str, Any]) -> str:
    if not value["samples"]:
        return "Not captured"
    return (
        f"Mean {value['mean_ms']:.1f} ms; median {value['median_ms']:.1f} ms; "
        f"n={value['samples']}"
    )


def _build_summary_sheet(
    workbook: Workbook,
    report: dict[str, Any],
    row_counts: list[tuple[str, int]],
) -> Worksheet:
    sheet = workbook.create_sheet("Summary")
    sheet.sheet_view.showGridLines = False
    sheet.sheet_view.zoomScale = 90
    sheet.sheet_properties.tabColor = BRAND
    sheet.column_dimensions["A"].width = 38
    sheet.column_dimensions["B"].width = 24
    sheet.column_dimensions["C"].width = 57
    sheet.column_dimensions["E"].width = 25
    sheet.column_dimensions["F"].width = 15
    sheet["A1"] = "T"
    sheet["A1"].fill = PatternFill("solid", fgColor=BRAND)
    sheet["A1"].font = Font(name="Calibri", size=18, bold=True, color=WHITE)
    sheet["A1"].alignment = Alignment(horizontal="center", vertical="center")
    sheet.merge_cells("B1:F1")
    sheet["B1"] = "T.A.G.A.P. | RAW DATA & OPERATIONAL SUMMARY"
    sheet["B1"].fill = PatternFill("solid", fgColor=INK)
    sheet["B1"].font = Font(name="Calibri", size=15, bold=True, color=WHITE)
    sheet["B1"].alignment = Alignment(vertical="center")
    sheet.merge_cells("A2:F2")
    room = report["room"]
    period = report["period"]
    generated_at = report.get("generated_at")
    if not isinstance(generated_at, datetime):
        generated_at = datetime.now(REPORT_TIMEZONE)
    sheet["A2"] = (
        f"Research Instrument 1 | {room['school']} | Room {room['room_number']} | "
        f"{period['start']} to {period['end']} (Asia/Manila) | "
        f"Generated {generated_at:%Y-%m-%d %H:%M:%S} PHT"
    )
    sheet["A2"].font = Font(name="Calibri", size=10, color=MUTED)
    sheet["A2"].alignment = Alignment(wrap_text=True)
    sheet.row_dimensions[1].height = 29
    sheet.row_dimensions[2].height = 23

    _write_section_heading(sheet, 4, "Operational metrics")
    for column, value in enumerate(("Measure", "Value", "Source / interpretation"), 1):
        _style_header(sheet.cell(5, column, value))
    for row_index, (label, value, note) in enumerate(_summary_metrics(report), 6):
        sheet.cell(row_index, 1, _excel_safe(label))
        sheet.cell(row_index, 2, _excel_safe(value))
        sheet.cell(row_index, 3, _excel_safe(note))
        _style_body_row(sheet, row_index, 3)

    source_start = 6 + len(_summary_metrics(report)) + 2
    _write_section_heading(sheet, source_start, "Raw data included in this workbook")
    for column, value in enumerate(("Worksheet", "Rows exported", "Reconciliation"), 1):
        _style_header(sheet.cell(source_start + 1, column, value))
    raw = report["raw_data"]
    counts_by_sheet = {
        "RFID Events": len(raw["rfid_events"]),
        "RFID Cards": len(raw["rfid_cards"]),
        "Alerts": len(raw["alerts"]),
        "SMS Queue": len(raw["sms_queue"]),
        "SMS Attempts": len(raw["sms_attempts"]),
        "Audit Trail": len(raw["audit_events"]),
        "Analytics": len(raw["analytics"]),
        "Latency": len(raw["latency"]),
    }
    for row_index, (sheet_name, count) in enumerate(row_counts, source_start + 2):
        sheet.cell(row_index, 1, sheet_name)
        sheet.cell(row_index, 2, count)
        sheet.cell(
            row_index,
            3,
            (
                "Unparseable audit payloads included as flagged rows"
                if sheet_name == "Audit Trail" and raw["malformed_audit_events"]
                else "Source snapshot for selected room and inclusive date range"
            ),
        )
        if sheet_name in counts_by_sheet and count != counts_by_sheet[sheet_name]:
            sheet.cell(row_index, 3, "Row-count mismatch; inspect source export")
            sheet.cell(row_index, 3).font = Font(color=RED, bold=True)
        _style_body_row(sheet, row_index, 3)

    check_row = source_start + len(row_counts) + 3
    _write_section_heading(sheet, check_row, "Reconciliation checks")
    sent_count = sum(row["status"] == "SENT" for row in raw["sms_queue"])
    failed_count = sum(row["status"] == "FAILED" for row in raw["sms_queue"])
    pending_count = sum(
        row["status"] in ("PENDING", "SENDING") for row in raw["sms_queue"]
    )
    detected_count = sum(
        event["event_type"] == "RFID_SCAN_DETECTED"
        for event in raw["rfid_events"]
    )
    checks = [
        (
            "RFID detected count",
            "PASS" if detected_count == report["rfid"]["scans_detected"] else "CHECK",
            f"Raw events: {detected_count}; PDF metric: {report['rfid']['scans_detected']}",
        ),
        (
            "SMS queue statuses",
            "PASS"
            if (
                sent_count == report["sms"]["sent"]
                and failed_count == report["sms"]["failed"]
                and pending_count == report["sms"]["pending"]
            )
            else "CHECK",
            f"Raw queue: sent {sent_count}, failed {failed_count}, pending {pending_count}",
        ),
        (
            "Cancelled scans queued",
            "PASS"
            if report["rfid"]["cancelled_with_sms_queued"] == 0
            else "CHECK",
            f"Observed: {report['rfid']['cancelled_with_sms_queued']}",
        ),
    ]
    for row_index, values in enumerate(checks, check_row + 1):
        for column, value in enumerate(values, 1):
            sheet.cell(row_index, column, _excel_safe(value))
        _style_body_row(sheet, row_index, 3)
        status_cell = sheet.cell(row_index, 2)
        status_cell.font = Font(
            color=GREEN if values[1] == "PASS" else RED,
            bold=True,
        )

    privacy_row = check_row + len(checks) + 2
    _write_section_heading(sheet, privacy_row, "Measurement and privacy notes")
    notes = [
        "SMS response time measures the worker's send operation through the modem result; it is not the time a parent receives the message.",
        "Historical dispatch response time is estimated from audit timestamps when the worker did not record an explicit response_time_ms.",
        "Parent recipient numbers are masked to the last four digits. RFID UIDs are replaced with consistent SHA-256 references.",
        "SMS message text is preserved for local content review. Do not distribute this workbook outside authorized research/system staff.",
        "SMS queue status is the current state at report generation. Complete queue, dispatch, and result events for selected alerts may fall outside the selected alert-trigger date range.",
        "Instrument 2 questionnaire data is not included. RSSI/signal strength and raw serial byte streams are not captured by the system.",
    ]
    for row_index, note in enumerate(notes, privacy_row + 1):
        sheet.merge_cells(start_row=row_index, start_column=1, end_row=row_index, end_column=6)
        cell = sheet.cell(row_index, 1, _excel_safe(note))
        cell.font = Font(name="Calibri", size=9, color=INK)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        sheet.row_dimensions[row_index].height = 30

    alert_counts = report["alerts_by_type"]
    if alert_counts:
        chart_start = 5
        sheet.cell(chart_start, 5, "Alert type")
        sheet.cell(chart_start, 6, "Count")
        for row_index, (card_type, count) in enumerate(
            sorted(alert_counts.items()),
            chart_start + 1,
        ):
            sheet.cell(row_index, 5, str(card_type))
            sheet.cell(row_index, 6, int(count))
        chart = BarChart()
        chart.type = "bar"
        chart.style = 10
        chart.title = "Confirmed alert trials by type"
        chart.y_axis.title = "Card type"
        chart.x_axis.title = "Alerts"
        chart.height = 7
        chart.width = 12
        data = Reference(
            sheet,
            min_col=6,
            min_row=chart_start,
            max_row=chart_start + len(alert_counts),
        )
        categories = Reference(
            sheet,
            min_col=5,
            min_row=chart_start + 1,
            max_row=chart_start + len(alert_counts),
        )
        chart.add_data(data, titles_from_data=True)
        chart.set_categories(categories)
        sheet.add_chart(chart, "E12")

    sms_chart_row = chart_start + len(alert_counts) + 4 if alert_counts else 5
    for column, value in enumerate(("SMS outcome", "Count"), 5):
        sheet.cell(sms_chart_row, column, value)
    sms_values = (
        ("Sent", sent_count),
        ("Failed", failed_count),
        ("Pending", pending_count),
    )
    for row_index, values in enumerate(sms_values, sms_chart_row + 1):
        sheet.cell(row_index, 5, values[0])
        sheet.cell(row_index, 6, values[1])
    sms_chart = BarChart()
    sms_chart.type = "bar"
    sms_chart.style = 11
    sms_chart.title = "SMS modem outcomes"
    sms_chart.y_axis.title = "Outcome"
    sms_chart.x_axis.title = "Messages"
    sms_chart.height = 7
    sms_chart.width = 12
    sms_chart.add_data(
        Reference(sheet, min_col=6, min_row=sms_chart_row, max_row=sms_chart_row + 3),
        titles_from_data=True,
    )
    sms_chart.set_categories(
        Reference(sheet, min_col=5, min_row=sms_chart_row + 1, max_row=sms_chart_row + 3)
    )
    sheet.add_chart(sms_chart, "E28")
    sheet.freeze_panes = "A6"
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 1
    return sheet


def _write_section_heading(sheet: Worksheet, row: int, title: str) -> None:
    sheet.merge_cells(start_row=row, start_column=1, end_row=row, end_column=3)
    cell = sheet.cell(row, 1, title)
    cell.fill = PatternFill("solid", fgColor=INK)
    cell.font = Font(name="Calibri", size=10, bold=True, color=WHITE)
    cell.alignment = Alignment(vertical="center")
    sheet.row_dimensions[row].height = 21


def _style_header(cell) -> None:
    cell.fill = PatternFill("solid", fgColor=BLUE)
    cell.font = Font(name="Calibri", size=9, bold=True, color=WHITE)
    cell.alignment = Alignment(wrap_text=True, vertical="center")
    cell.border = Border(bottom=Side(style="thin", color=GRID))


def _style_body_row(sheet: Worksheet, row: int, columns: int) -> None:
    for column in range(1, columns + 1):
        cell = sheet.cell(row, column)
        cell.font = Font(name="Calibri", size=9, color=INK)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        if row % 2 == 0:
            cell.fill = PatternFill("solid", fgColor=PALE)
    sheet.row_dimensions[row].height = 22


def generate_operational_workbook(
    report: dict[str, Any],
    output_directory: Path,
) -> Path:
    output_directory.mkdir(parents=True, exist_ok=True)
    room = report["room"]
    period = report["period"]
    room_slug = re.sub(
        r"[^A-Za-z0-9_-]+",
        "-",
        str(room["room_number"]),
    ).strip("-")
    generated_at = report.get("generated_at")
    if not isinstance(generated_at, datetime):
        generated_at = datetime.now(REPORT_TIMEZONE)
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=timezone.utc)
    timestamp = generated_at.astimezone(REPORT_TIMEZONE).strftime(
        "%Y%m%d-%H%M%S-%f"
    )
    output_path = output_directory / (
        f"TAGAP-Raw-Data-Room-{room_slug or room['id']}-"
        f"{period['start']}-to-{period['end']}-{timestamp}.xlsx"
    )
    workbook = Workbook()
    workbook.remove(workbook.active)
    workbook.properties.creator = "T.A.G.A.P."
    workbook.properties.title = "Instrument 1 Raw Data and Operational Summary"
    workbook.properties.subject = "Auditable local RFID, alert, SMS, and latency records"
    raw = report["raw_data"]
    sheet_specs = [
        (
            "RFID Events",
            "RFID reads and operator confirmation decisions, as recorded in the audit log.",
            _build_rfid_rows(raw),
            BRAND,
        ),
        (
            "RFID Cards",
            "Registered card types and active state. UIDs are pseudonymized for privacy.",
            _build_card_rows(raw),
            BRAND,
        ),
        (
            "Alerts",
            "Alert records generated from confirmed RFID scans. Card IDs are pseudonymized.",
            _build_alert_rows(raw),
            BLUE,
        ),
        (
            "SMS Queue",
            "Recipient queue records and complete message text. Phone numbers are masked.",
            _build_sms_rows(raw),
            AMBER,
        ),
        (
            "SMS Attempts",
            "Individual dispatch attempts paired with modem success/failure audit events.",
            _build_attempt_rows(raw),
            GREEN,
        ),
        (
            "Audit Trail",
            "Room events in period plus full SMS lifecycle events for selected alerts; identifiers are protected.",
            _build_audit_rows(raw),
            MUTED,
        ),
        (
            "Analytics",
            "Stored per-alert response and delivery timings from the analytics table.",
            _build_analytics_rows(raw),
            BLUE,
        ),
        (
            "Latency",
            "Per-scan milestone timestamps and durations used for response-time checks.",
            _build_latency_rows(raw),
            AMBER,
        ),
    ]
    row_counts = []
    for title, subtitle, rows, color in sheet_specs:
        sheet = _write_data_sheet(
            workbook,
            title,
            subtitle,
            report,
            rows,
            color,
        )
        row_counts.append((title, len(rows) - 1))
    _build_summary_sheet(workbook, report, row_counts)
    workbook.active = len(workbook.worksheets) - 1
    workbook.calculation.fullCalcOnLoad = True
    workbook.calculation.forceFullCalc = True
    workbook.save(output_path)
    return output_path


def generate_operational_workbook_for_room(
    room_id: int,
    start_date: date,
    end_date: date,
) -> Path:
    from data.research_reports import get_operational_report_data

    report = get_operational_report_data(room_id, start_date, end_date)
    return generate_operational_workbook(
        report,
        PROJECT_ROOT / "data" / "generated_reports",
    )
