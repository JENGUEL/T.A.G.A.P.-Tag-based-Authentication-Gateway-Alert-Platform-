"""
Sprint 2 verification — proves DB, models, repositories, and seed all work.
Run: python -m scripts.verify_sprint2
"""

from data.database import get_db, init_db, drop_db
from data.repositories import (
    AlertRepository,
    CardRepository,
    DeduplicationChecker,
    ParentRepository,
    SmsQueueRepository,
)
from data.seed import seed
from datetime import datetime, timezone


def main() -> None:
    print("=" * 60)
    print("Sprint 2 Verification")
    print("=" * 60)

    # Fresh DB
    drop_db()
    init_db()
    seed()

    # --- 1. Verify cards ---
    safe_card = CardRepository.get_by_uid("CARD-SAFE-0001")
    assert safe_card is not None, "Safe card not found"
    assert safe_card.room.name == "Room 201"
    assert safe_card.room.school.name.startswith("San Jose")
    print(f"✅ Card lookup: {safe_card.uid} → {safe_card.room.name}")

    # --- 2. Verify parents per room ---
    with get_db() as db:
        parents = ParentRepository.get_for_room(db, safe_card.room_id)
        assert len(parents) == 3, f"Expected 3 parents, got {len(parents)}"
        print(f"✅ Parents for room: {len(parents)} found")
        for p in parents:
            print(f"     - {p.name}: {p.phone_number}")

    # --- 3. Simulate alert + queue ---
    with get_db() as db:
        alert = AlertRepository.create(
            db,
            card_uid=safe_card.uid,
            card_type=safe_card.card_type,
            room_id=safe_card.room_id,
            triggered_at=datetime.now(timezone.utc),
        )
        alert.confirmed_at = datetime.now(timezone.utc)
        for p in parents:
            SmsQueueRepository.enqueue(
                db,
                alert_id=alert.id,
                recipient_type="PARENT",
                phone_number=p.phone_number,
                message=f"Test message for {p.name}",
            )
        print(f"✅ Alert created with {len(parents)} SMS queued")

    # --- 4. Verify queue is durable ---
    with get_db() as db:
        pending = SmsQueueRepository.fetch_pending(db)
        assert len(pending) == 3, f"Expected 3 pending, got {len(pending)}"
        print(f"✅ Queue persistence: {len(pending)} pending messages")

    # --- 5. Deduplication check ---
    with get_db() as db:
        is_dup = DeduplicationChecker.is_duplicate(db, safe_card.uid, window_seconds=60)
        assert is_dup is True, "Deduplication should detect duplicate"
        print(f"✅ Deduplication: same card detected within window")

    print("=" * 60)
    print("✅ ALL SPRINT 2 CHECKS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()