"""
Sprint 3 verification — proves HAL contracts, mocks, and DI all work.
Run: python -m scripts.verify_sprint3
"""

from __future__ import annotations

import time

from config import settings
from services import get_rfid_service, get_sms_service, reset_services
from services.adapters.rfid_mock import MockRfidService
from services.adapters.sms_mock import MockSmsService


def main() -> None:
    print("=" * 60)
    print("Sprint 3 Verification — HAL")
    print("=" * 60)

    # --- 1. DI returns mock (per .env) ---
    rfid = get_rfid_service()
    sms = get_sms_service()
    print(f"✅ DI RFID: {type(rfid).__name__}")
    print(f"✅ DI SMS:  {type(sms).__name__}")
    assert isinstance(rfid, MockRfidService)
    assert isinstance(sms, MockSmsService)

    # --- 2. Lifecycle ---
    rfid.open()
    sms.open()
    assert rfid.is_connected()
    assert sms.is_connected()
    print("✅ Services opened")

    # --- 3. RFID: no card case ---
    card = rfid.read_card(timeout_seconds=0.2)
    assert card is None
    print("✅ RFID returns None on timeout (no card)")

    # --- 4. RFID: scripted tap ---
    rfid.queue_tap("CARD-DANGER-0001")  # type: ignore[attr-defined]
    card = rfid.read_card(timeout_seconds=0.5)
    assert card == "CARD-DANGER-0001"
    print(f"✅ RFID read scripted card: {card}")

    # --- 5. SMS: successful send ---
    result = sms.send_sms("0917-111-0001", "Test alert from T.A.G.A.P.")
    assert result.success is True
    print(f"✅ SMS sent successfully → {result.phone_number}")

    # --- 6. SMS: injected failure ---
    sms.fail_next(2, reason="simulated network down")  # type: ignore[attr-defined]
    r1 = sms.send_sms("0917-111-0002", "Will fail #1")
    r2 = sms.send_sms("0917-111-0003", "Will fail #2")
    r3 = sms.send_sms("0917-111-0004", "Will succeed")
    assert r1.success is False
    assert r2.success is False
    assert r3.success is True
    print("✅ SMS failure injection + recovery works")

    # --- 7. Signal strength ---
    rssi = sms.signal_strength()
    print(f"✅ SMS signal strength: {rssi}/31")

    # --- 8. Verify outbox files were created ---
    from pathlib import Path
    outbox = Path("data/mock_sms_outbox")
    files = list(outbox.glob("*.txt"))
    print(f"✅ Mock outbox: {len(files)} message file(s) in {outbox}")
    assert len(files) >= 2, "Expected at least 2 successful mocks written to outbox"

    # --- 9. Cleanup ---
    rfid.close()
    sms.close()
    reset_services()
    print("✅ Services closed and DI reset")

    print("=" * 60)
    print("✅ ALL SPRINT 3 CHECKS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()