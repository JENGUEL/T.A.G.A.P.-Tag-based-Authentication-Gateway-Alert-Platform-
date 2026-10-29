"""
T.A.G.A.P. - Mock SMS Adapter

Simulates GSM SMS sending without any hardware.
Every "sent" SMS is:
- Logged to console + logs/sms_mock.log
- Appended to data/mock_sms_outbox/<timestamp>_<phone>.txt

Also supports failure injection for testing retry logic:
    mock_sms.fail_next(n=2)  # next 2 sends fail
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

from services.interfaces import ISmsService, SmsResult

logger = logging.getLogger(__name__)

DEFAULT_OUTBOX = Path("data/mock_sms_outbox")


class MockSmsService(ISmsService):
    def __init__(self, outbox: Path = DEFAULT_OUTBOX) -> None:
        self._outbox = outbox
        self._open = False
        self._lock = threading.Lock()
        self._fail_remaining = 0

    # --- Lifecycle ---

    def open(self) -> None:
        self._outbox.mkdir(parents=True, exist_ok=True)
        self._open = True
        logger.info("MockSmsService opened (outbox=%s)", self._outbox)

    def close(self) -> None:
        self._open = False
        logger.info("MockSmsService closed")

    def is_connected(self) -> bool:
        return self._open

    # --- Test helpers ---

    def fail_next(self, n: int = 1, reason: str = "injected failure") -> None:
        """Force the next `n` send attempts to fail (for retry tests)."""
        with self._lock:
            self._fail_remaining += n

    # --- Core contract ---

    def send_sms(self, phone_number: str, message: str) -> SmsResult:
        if not self._open:
            raise RuntimeError("MockSmsService is not open")

        with self._lock:
            if self._fail_remaining > 0:
                self._fail_remaining -= 1
                logger.warning("MockSmsService INJECTED FAILURE to %s", phone_number)
                return SmsResult(
                    success=False,
                    phone_number=phone_number,
                    message=message,
                    reason="injected failure",
                )

        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        safe_phone = "".join(c for c in phone_number if c.isdigit()) or "unknown"
        out_path = self._outbox / f"{ts}_{safe_phone}.txt"
        try:
            out_path.write_text(
                f"TO: {phone_number}\nAT: {ts}\n\n{message}\n",
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("MockSmsService failed to write outbox: %s", exc)

        logger.info("MockSmsService SENT to %s: %s", phone_number, message[:60])
        return SmsResult(
            success=True,
            phone_number=phone_number,
            message=message,
            raw_response="MOCK+SENT",
        )

    def signal_strength(self) -> int:
        return 24  # Fake "good" signal