# T.A.G.A.P. — Feature Specification v1.0

> **Tag-based Authentication Gateway Alert Platform**
> Offline-first school lockdown-drill status kiosk.

**Version:** 1.0
**Status:** Approved — MVP Scope
**Last Updated:** 2026-10-29
**Owner:** T.A.G.A.P. Research Team

---

## 1. Purpose

T.A.G.A.P. is a **local-first, offline-capable lockdown-drill status kiosk** deployed in classrooms. Using RFID cards, teachers can report when a school lockdown drill is ongoing or has ended. Parents are notified via SMS — **without requiring internet access**.

The system is designed to be **fast, fail-safe, auditable**, and suitable for research evaluation.

---

## 2. Design Principles

1. **Offline-first** — Full operation without internet. GSM only.
2. **Fail-safe** — Every alert persists to disk before any SMS is attempted.
3. **Non-blocking UI** — Hardware I/O never freezes the kiosk.
4. **Auditable** — Every event is timestamped for research and compliance.
5. **Production-grade UX** — Modern, polished, instant feedback.
6. **Privacy-conscious** — No cloud, no third-party, no tracking.

---

## 3. RFID Card System

The system uses **4 RFID cards** per kiosk.

| Card | Color | Trigger | Recipients | UI Flow |
|------|-------|---------|-----------|---------|
| **ONGOING** | Green | Lockdown drill commencing | Parents | Standby → Confirm (3s) → Queue → Standby |
| **END** | Red | Lockdown drill ended | Parents | Standby → Confirm (3s) → Queue → Standby |
| N/A | N/A | Unused slot | — | — |
| **ADMIN** | Blue | Open Settings | — | Standby → Smooth transition → Settings |

> **Note:** Alert cards notify parents only. The category and template system remains extensible for future workflows.

---

## 4. Alert Workflow

1. **RFID reader detects card** (background thread — never blocks UI).
2. **Card UID looked up in DB** → returns `CardType` and associated `Room`.
3. **Deduplication check:** same card within 60s → silently rejected, logged.
4. **UI transitions to Confirmation screen** (color-coded by status).
5. **3-second confirmation window**: confirm with **CONFIRM ALERT** or by scanning the same RFID card again; **CANCEL** remains available.
6. **Only on explicit confirm:**
   - Fetch all students in the room + their parent names + parent phone numbers.
   - Build the configured parent message from the alert category's database template.
   - Insert one SMS per parent into `sms_queue` (durable, survives reboot).
   - Log analytics event.
7. **On cancel or countdown expiry:** return to Standby without creating an alert or queuing SMS.
8. **Background SMS worker polls queue every 2s:**
   - Send via GSM using concatenated UCS-2 PDU parts when the message exceeds one SMS.
   - Retry 3× with exponential backoff (2s / 4s / 8s) on failure.
   - Treat `+CMGS:` as the modem's submission acknowledgement; it does not confirm parent receipt.
   - Update queue status: `SENT` / `FAILED`.
   - Log modem acknowledgement + failure reason to `audit_logs`.
9. **UI returns to Standby.**

---

## 5. SMS Templates (Swappable — Stored in DB)

Templates are stored in the database, **not hardcoded**. Admins can edit them via Settings (PIN-protected).

### 5.1 Parent Templates

**ONGOING:**
ST. MARY'S ACADEMY OF PALO

This is to inform you that the SCHOOL LOCKDOWN DRILL for {grade_section} is currently ongoing as of {time} on {date}.

Students and school personnel are following the established safety protocols. Please remain calm and wait for further official announcements from the school.

This is a scheduled drill. Thank you.

Sent via T.A.G.A.P. Communication System

**END:**
ST. MARY'S ACADEMY OF PALO

This is to inform you that the SCHOOL LOCKDOWN DRILL for {grade_section} has officially concluded as of {time} on {date}.

Students and school personnel have completed the drill in accordance with the school's established safety protocols. Please wait for further official announcements regarding the resumption of regular school activities.

Thank you for your cooperation.

Sent via T.A.G.A.P. Communication System

---

## 6. Database Schema (Sprint 2 Scope)
schools (id, name, hotline, created_at)
police_stations (id, school_id, name, phone_number)
rooms (id, school_id, name, wing [legacy/unused], floor)
cards (id, uid, type, room_id, active, created_at)
students (id, name, room_id)
parents (id, name, phone_number)
student_parents (student_id, parent_id)
sms_templates (id, key, template_text, updated_at)
alerts (id, card_uid, card_type, room_id, triggered_at, confirmed_at)
sms_queue (id, alert_id, recipient_type, phone_number, message, status, attempts, created_at, sent_at, failure_reason)
audit_logs (id, event_type, payload_json, created_at)
analytics (id, alert_id, response_time_ms, scan_ts, confirm_ts, queue_ts, sent_ts)


**Key relations:**
- One school → many rooms, many police stations, many cards.
- One room → many students.
- One student → many parents (via `student_parents`).
- One alert → one SMS per parent. Police-station records remain in the database but are not alert recipients in this workflow.

---

## 7. Admin / Settings Screen

### 7.1 Access

- **Scan Admin card** → smooth transition to Settings view. No PIN required to *view*.
- **4-digit PIN** required for all destructive actions.

### 7.2 View (no PIN)

- Room info (name, floor)
- School info (name, hotline)
- Police station (name, phone)
- GSM status (signal strength, SIM balance, connectivity)
- Queue status (pending / sent / failed counts)
- Recent alerts (last 20)
- Analytics summary (response times, success rates)
- Manage alert card categories (except the protected ADMIN type) and register matching RFID cards.
- Configure and persist deduplication (1–3600 seconds), confirmation timeout (1–300 seconds), and SMS retry attempts (1–10).

Legacy Wing values may remain in existing databases, but are omitted from the kiosk, admin UI, reports, and outgoing SMS.

### 7.3 Destructive Actions (PIN required)

- Edit SMS templates
- Edit police station number
- Edit school info
- Retry failed SMS (per row / retry-all)
- Clear queue
- Register / delete cards
- Factory reset

---

## 8. Analytics & Research Metrics

Auto-collected on every alert:

| Metric | Purpose |
|--------|---------|
| `scan_timestamp` | RFID read time |
| `confirm_timestamp` | User confirmation time |
| `queue_timestamp` | When SMS entered queue |
| `sent_timestamp` | GSM delivery confirmation |
| `response_time_ms` | scan → queued (system latency) |
| `delivery_time_ms` | queued → sent (GSM latency) |
| `sms_success` | Boolean |
| `sms_failure_reason` | Text reason if failed |
| `deduplication_rejections` | Count per hour |
| `card_type_distribution` | Usage patterns |
| `hourly_alert_volume` | Peak analysis |

**Export:** CSV download from Settings (for research paper).

---

## 9. UI/UX Standards

- **Kiosk full-screen** — no taskbar, no close button, no window frame.
- **Standby screen** — logo, drill mode indicator, "Ready to scan", GSM status, listening indicator.
- **Confirmation screen** — color-coded (green/yellow/red), large countdown ring, explicit CONFIRM ALERT and CANCEL buttons; expiry performs no operation.
- **Settings screen** — inspired by Linear/Stripe: sidebar nav, clean typography, card-based layout, subtle animations.
- **Feedback latency:** every action < 100ms visual response.
- **Accessibility:** high contrast, tap targets ≥ 44px, readable fonts.

---

## 10. Failure Handling

| Failure | Behavior |
|---------|----------|
| RFID or GSM unavailable at startup | Explain which hardware is unavailable and ask whether to cancel or continue in degraded mode; do not silently enable mock hardware |
| GSM offline | Keep SMS queued locally and wait for the configured serial device to be reconnected; attempt one modem handshake, then show a connection confirmation and resume delivery on success |
| RFID or GSM disconnects during operation | Open a terminal-style recovery dialog showing both device states and disconnect events; let the operator reconnect or continue in degraded mode |
| GSM send fail | Retry 3× with backoff, then mark FAILED |
| RFID offline or disconnected | Show "Reader disconnected" indicator; UI stays responsive, but card scans remain unavailable until reconnected |
| Power loss | Queue persists in SQLite; resumes on boot |
| DB corruption | Auto-backup on boot, show admin warning |
| Duplicate scan | Silent rejection within 60s; log for analytics |

---

## 11. Security

- Admin card-only for settings view.
- 4-digit PIN for destructive actions.
- All actions logged to `audit_logs` (append-only).
- No internet exposure; serial-only hardware.
- No PII in SMS beyond child's room — no student names in parent messages.

---

## 12. Deployment Targets

| Env | Platform | Hardware |
|-----|----------|----------|
| Dev | Windows laptop | Mock RFID + Mock SMS |
| Prod | Raspberry Pi 4/5 (Linux) | RC522/PN532 + SIM800 |

---

## 13. Explicitly Out of Scope (v1.0)

- Cloud sync / internet dependency
- Mobile companion app
- Two-way SMS (parent replies)
- Video / audio recording
- Facial recognition
- GPS tracking
- Live parent tracking of student location
- School LMS integration
- "All Clear" follow-up SMS

---

## 14. Build Plan (Sprints)

| Sprint | Focus |
|--------|-------|
| **S1** ✅ | Foundation: config, logging, constants, exceptions |
| **S2** | Database models + repositories + seed data |
| **S3** | HAL: RFID + SMS interfaces (mock + real adapters) |
| **S4** | Alert workflow: dedup, queue, retry, analytics |
| **S5** | UI: state machine, standby, confirmation screens |
| **S6** | Settings screen + admin card flow + PIN |
| **S7** | Analytics export + reporting |
| **S8** | Polish, testing, kiosk packaging |

### Research Instrument 1 report outputs

- The Emergency Report screen generates a formal PDF and a matching Excel workbook from one database snapshot.
- The workbook separates registered RFID cards, RFID scan/confirmation events, alerts, SMS queue records, per-attempt modem results, audit events, analytics, and per-scan latency; its final worksheet is a metric and raw-row reconciliation summary.
- SMS response time measures the worker's send operation until a modem result. Parent receipt time, modem RSSI, and raw serial byte streams are not captured.
- Parent phone numbers are masked and card UIDs are replaced with consistent pseudonymous references in the workbook. SMS message text remains available for authorized local review.
- SMS status counts reflect the queue state at report generation. Lifecycle audit entries for selected alerts may be included even when their timestamps fall outside the selected alert-trigger date range.

### Room roster, cards, and reader access

- The Room Device quick action and Settings expose the same editable student/contact roster. Each saved row updates room students and linked parent contacts, which are used by alert recipient selection.
- Settings can enroll ONGOING, END, and ADMIN cards. Enrollment requires an initial scan, operator confirmation, a second matching scan, and an explicit save. Cards can be disabled or removed.
- SMS templates are initialized once, stored in the database, and edited only after the admin PIN is verified. Subsequent seeding preserves edits.
- SMS templates are editable in Settings and saved to the database; alert dispatch uses the saved template for the selected card and recipient type.
- The kiosk Reader Monitor button routes to Settings for initial ADMIN-card enrollment when none is active. Once an ADMIN card is active, Reader Monitor requires that card to be scanned before access.
- The built-in `CARD-ADMIN-0001` sample is deactivated during seed repair so it cannot satisfy the real ADMIN-card enrollment gate.

---

## 15. Approval

- [x] Research Lead — Scope aligned with study objectives
- [x] Tech Lead — Architecture supports MVP requirements
- [ ] Panel Review — Pending