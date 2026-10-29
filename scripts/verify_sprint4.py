"""
Sprint 4 verification — proves the AlertService and SmsWorker work end-to-end.
Run: python -m scripts.verify_sprint4
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from core.constants import CardType, SmsStatus
from data.database import drop_db, get_db, init_db
from data.repositories import SmsQueueRepository
from data.seed import seed
from models import Alert, Analytics, AuditLog, SmsQueue
from services import get_sms_service, reset_services
from services.adapters.sms_mock import MockSmsService
from services.alert_service import AlertService
from services.sms_worker import SmsWorker


def main() -> None:
    print("=" * 60)
    print("Sprint 4 Verification — Alert Workflow")
    print("=" * 60)

    # --- Fresh DB + seed ---
    drop_db()
    init_db()
    seed()
    print("✅ DB seeded")

    # --- 1. Scan known card → NEEDS_CONFIRMATION ---
    scan_ts = datetime.now(timezone.utc)
    result = AlertService.scan_card("CARD-DANGER-0001")
    assert result.outcome.value == "NEEDS_CONFIRMATION", result.outcome
    assert result.card_type == CardType.DANGER
    assert result.room_name == "Room 201"
    print(f"✅ Scan danger card → NEEDS_CONFIRMATION (room={result.room_name})")

    # --- 2. Execute alert → creates 3 parent + 1 police = 4 SMS ---
    exec_result = AlertService.execute_alert("CARD-DANGER-0001", scan_ts)
    assert exec_result.outcome.value == "NEEDS_CONFIRMATION"
    assert exec_result.alert_id is not None
    assert exec_result.sms_queued == 4, f"Expected 4 SMS, got {exec_result.sms_queued}"
    print(f"✅ Alert executed: id={exec_result.alert_id} sms_queued={exec_result.sms_queued}")

    # --- 3. Verify rows in DB ---
    with get_db() as db:
        alert = db.get(Alert, exec_result.alert_id)
        assert alert is not None
        assert alert.card_type == "DANGER"
        assert alert.confirmed_at is not None

        sms_rows = db.query(SmsQueue).filter_by(alert_id=alert.id).all()
        assert len(sms_rows) == 4
        parents = [r for r in sms_rows if r.recipient_type == "PARENT"]
        police = [r for r in sms_rows if r.recipient_type == "POLICE"]
        assert len(parents) == 3
        assert len(police) == 1
        print(f"✅ DB rows: 3 parent SMS + 1 police SMS queued")

        # Check templates were rendered
        assert "DANGER" in parents[0].message
        assert "Room 201" in parents[0].message
        assert "ACTIVE THREAT" in police[0].message
        print(f"✅ Templates rendered correctly")

        # Verify analytics
        analytics = db.query(Analytics).filter_by(alert_id=alert.id).first()
        assert analytics is not None
        assert analytics.response_time_ms is not None
        print(f"✅ Analytics: response_time={analytics.response_time_ms}ms")

    # --- 4. Duplicate scan should be rejected ---
    dup_result = AlertService.scan_card("CARD-DANGER-0001")
    assert dup_result.outcome.value == "REJECTED_DUPLICATE"
    print("✅ Duplicate scan rejected")

    # --- 5. Unknown card rejected ---
    unknown = AlertService.scan_card("CARD-NOT-EXIST")
    assert unknown.outcome.value == "REJECTED_UNKNOWN"
    print("✅ Unknown card rejected")

    # --- 6. Admin card → ADMIN_ACCESS ---
    admin = AlertService.scan_card("CARD-ADMIN-0001")
    assert admin.outcome.value == "ADMIN_ACCESS"
    print("✅ Admin card → ADMIN_ACCESS")

    # --- 7. Run SMS worker to process the queue ---
    print("\nStarting SMS worker...")
    sms_svc = get_sms_service()
    assert isinstance(sms_svc, MockSmsService)
    sms_svc.open()

    worker = SmsWorker(sms_service=sms_svc)
    worker.start()

    # Wait up to 10 seconds for queue to drain
    deadline = time.time() + 10
    while time.time() < deadline:
        with get_db() as db:
            pending = db.query(SmsQueue).filter(
                SmsQueue.status.in_([SmsStatus.PENDING.value, SmsStatus.SENDING.value])
            ).count()
        if pending == 0:
            break
        time.sleep(0.5)

    worker.stop()

    # --- 8. Verify all 4 SMS were sent ---
    with get_db() as db:
        sent = db.query(SmsQueue).filter_by(status=SmsStatus.SENT.value).count()
        failed = db.query(SmsQueue).filter_by(status=SmsStatus.FAILED.value).count()
        assert sent == 4, f"Expected 4 sent, got {sent}"
        assert failed == 0
        print(f"✅ SMS worker: {sent} sent, {failed} failed")

        # Analytics sent_ts should now be populated
        analytics = db.query(Analytics).first()
        assert analytics.sent_ts is not None
        assert analytics.delivery_time_ms is not None
        print(f"✅ Analytics: delivery_time={analytics.delivery_time_ms}ms")

    # --- 9. Verify audit logs ---
    with get_db() as db:
        events = db.query(AuditLog).all()
        event_types = {e.event_type for e in events}
        assert "CARD_SCANNED" in event_types
        assert "ALERT_QUEUED" in event_types
        assert "SMS_SENT" in event_types
        assert "SMS_FAILED" not in event_types
        print(f"✅ Audit logs: {len(events)} entries, types={sorted(event_types)}")

        # --- 10. Test retry logic with injected failures ---
    print("\n--- Testing retry with injected failures ---")
    sms_svc.open()

    # Execute a fresh alert (SAFE card → 4 SMS again: 3 parents + 1 police)
    safe_scan = datetime.now(timezone.utc)
    safe_result = AlertService.execute_alert("CARD-SAFE-0001", safe_scan)
    assert safe_result.sms_queued == 4
    print(f"✅ SAFE alert queued: id={safe_result.alert_id}")

    # Inject 2 failures — worker should retry with backoff
    sms_svc.fail_next(2, reason="injected retry test")

    worker2 = SmsWorker(sms_service=sms_svc)
    worker2.start()

    # Wait up to 20 seconds (backoff can push retries out)
    deadline = time.time() + 20
    while time.time() < deadline:
        with get_db() as db:
            pending = db.query(SmsQueue).filter(
                SmsQueue.status.in_([SmsStatus.PENDING.value, SmsStatus.SENDING.value])
            ).count()
        if pending == 0:
            break
        time.sleep(0.5)

    worker2.stop()

    # --- 11. Verify retries eventually delivered all 4 ---
    with get_db() as db:
        safe_sent = (
            db.query(SmsQueue)
            .filter_by(alert_id=safe_result.alert_id)
            .filter_by(status=SmsStatus.SENT.value)
            .count()
        )
        assert safe_sent == 4, f"Retry failed: only {safe_sent}/4 delivered"
        print(f"✅ Retry logic: {safe_sent}/4 delivered after injected failures")

        # At least one SMS should have attempts > 1
        retried = (
            db.query(SmsQueue)
            .filter_by(alert_id=safe_result.alert_id)
            .filter(SmsQueue.attempts > 1)
            .count()
        )
        assert retried >= 1, "Expected at least 1 SMS to have retried"
        print(f"✅ Retried SMS count: {retried}")

    # --- 12. Verify outbox files exist ---
    from pathlib import Path
    outbox = Path("data/mock_sms_outbox")
    files = list(outbox.glob("*.txt"))
    assert len(files) >= 8, f"Expected ≥8 outbox files, got {len(files)}"
    print(f"✅ Mock outbox: {len(files)} files written")

    # --- 13. Cleanup ---
    sms_svc.close()
    reset_services()

    print("=" * 60)
    print("✅ ALL SPRINT 4 CHECKS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()