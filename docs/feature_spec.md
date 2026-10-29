# T.A.G.A.P. — Feature Specification v1.0

> **Tag-based Authentication Gateway Alert Platform**
> Offline-first emergency alert kiosk for school shooting response.

**Version:** 1.0
**Status:** Approved — MVP Scope
**Last Updated:** 2026-10-29
**Owner:** T.A.G.A.P. Research Team

---

## 1. Purpose

T.A.G.A.P. is a **local-first, offline-capable emergency alert kiosk** deployed in classrooms. Using RFID cards, teachers can instantly report the status of their room during a school shooting or active threat incident. Parents and the nearest police station are notified via SMS — **without requiring internet access**.

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
| **SAFE** | Green | Status = Safe | Parents + Police | Standby → Confirm (3s) → Queue → Standby |
| **ASSIST** | Yellow | Status = Need Assistance | Parents + Police | Standby → Confirm (3s) → Queue → Standby |
| **DANGER** | Red | Status = Active Threat | Parents + Police | Standby → Confirm (3s) → Queue → Standby |
| **ADMIN** | Blue | Open Settings | — | Standby → Smooth transition → Settings |

> **Note:** ALL card types notify **both** parents and the police station. The system's research goal is maximum awareness during any incident. SMS templates differ per card type to convey correct urgency.

---

## 4. Alert Workflow

1. **RFID reader detects card** (background thread — never blocks UI).
2. **Card UID looked up in DB** → returns `CardType` and associated `Room`.
3. **Deduplication check:** same card within 60s → silently rejected, logged.
4. **UI transitions to Confirmation screen** (color-coded by status).
5. **3-second countdown** with a **CANCEL** button.
6. **On confirm (or timeout):**
   - Fetch all students in the room + their parent names + parent phone numbers.
   - Fetch the school's configured police station number.
   - Build SMS messages from templates (parents → one message per parent; police → one message).
   - Insert all into `sms_queue` table (durable, survives reboot).
   - Log analytics event.
7. **Background SMS worker polls queue every 2s:**
   - Send via GSM (AT commands).
   - Retry 3× with exponential backoff (2s / 4s / 8s) on failure.
   - Parse `+CMGS:` response to confirm actual delivery.
   - Update queue status: `SENT` / `FAILED`.
   - Log delivery confirmation + failure reason to `audit_logs`.
8. **UI returns to Standby.**

---

## 5. SMS Templates (Swappable — Stored in DB)

Templates are stored in the database, **not hardcoded**. Admins can edit them via Settings (PIN-protected).

### 5.1 Parent Templates

**SAFE:**
[T.A.G.A.P.] SAFE: Your child in {room_name} is safe. Reported at {timestamp}. No action needed. — {school_name}

**ASSIST:**
[T.A.G.A.P.] ASSIST: Assistance requested in {room_name} at {timestamp}. Please monitor for updates. — {school_name}

**DANGER:**
[T.A.G.A.P.] DANGER: Emergency in {room_name} at {timestamp}. Follow school instructions. Hotline: {school_hotline}.

### 5.2 Police Templates (per card type)

**SAFE:**
[T.A.G.A.P.] SAFE status reported at {school_name}, {room_name} ({wing}) at {timestamp}. No emergency. Situation monitored. — School hotline: {school_hotline}

**ASSIST:**
[T.A.G.A.P.] ASSIST request at {school_name}, {room_name} ({wing}) at {timestamp}. Situation requires attention. — School hotline: {school_hotline}

**DANGER:**
[T.A.G.A.P. EMERGENCY] ACTIVE THREAT reported at {school_name}, {room_name} ({wing}) at {timestamp}. Immediate police response required. Callback: {school_hotline}.

---

## 6. Database Schema (Sprint 2 Scope)
schools (id, name, hotline, created_at)
police_stations (id, school_id, name, phone_number)
rooms (id, school_id, name, wing, floor)
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
- One alert → many SMS messages (one per parent + one for police).

---

## 7. Admin / Settings Screen

### 7.1 Access

- **Scan Admin card** → smooth transition to Settings view. No PIN required to *view*.
- **4-digit PIN** required for all destructive actions.

### 7.2 View (no PIN)

- Room info (name, wing, floor)
- School info (name, hotline)
- Police station (name, phone)
- GSM status (signal strength, SIM balance, connectivity)
- Queue status (pending / sent / failed counts)
- Recent alerts (last 20)
- Analytics summary (response times, success rates)

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
- **Confirmation screen** — color-coded (green/yellow/red), large countdown ring, CANCEL button, distinct visual per card type.
- **Settings screen** — inspired by Linear/Stripe: sidebar nav, clean typography, card-based layout, subtle animations.
- **Feedback latency:** every action < 100ms visual response.
- **Accessibility:** high contrast, tap targets ≥ 44px, readable fonts.

---

## 10. Failure Handling

| Failure | Behavior |
|---------|----------|
| GSM offline | Queue SMS, show "Pending — Retrying", log to audit |
| GSM send fail | Retry 3× with backoff, then mark FAILED |
| RFID disconnect | Show "Reader disconnected" indicator; UI stays responsive |
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

---

## 15. Approval

- [x] Research Lead — Scope aligned with study objectives
- [x] Tech Lead — Architecture supports MVP requirements
- [ ] Panel Review — Pending