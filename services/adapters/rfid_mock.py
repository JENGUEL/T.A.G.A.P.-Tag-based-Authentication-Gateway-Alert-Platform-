"""
T.A.G.A.P. - Mock RFID Adapter

Simulates card reads for development and automated tests.
Behavior:
- If a "tap file" exists (data/mock_rfid_taps.txt), reads and clears it.
- Otherwise blocks for the timeout window and returns None.
- Also supports a "scripted" queue for automated tests.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Optional

from services.interfaces import IRfidService

logger = logging.getLogger(__name__)

# File that the developer (or a script) drops a UID into to simulate a tap
DEFAULT_TAP_FILE = Path("data/mock_rfid_taps.txt")


class MockRfidService(IRfidService):
    def __init__(self, tap_file: Path = DEFAULT_TAP_FILE) -> None:
        self._tap_file = tap_file
        self._open = False
        self._scripted: list[str] = []
        self._lock = threading.Lock()

    # --- Lifecycle ---

    def open(self) -> None:
        self._tap_file.parent.mkdir(parents=True, exist_ok=True)
        # Clear any stale tap from a previous run
        if self._tap_file.exists():
            self._tap_file.unlink()
        self._open = True
        logger.info("MockRfidService opened (tap_file=%s)", self._tap_file)

    def close(self) -> None:
        self._open = False
        logger.info("MockRfidService closed")

    def is_connected(self) -> bool:
        return self._open

    # --- Test helper ---

    def queue_tap(self, uid: str) -> None:
        """Programmatically enqueue a card tap (used in tests)."""
        with self._lock:
            self._scripted.append(uid)
        logger.debug("MockRfidService queued tap: %s", uid)

    # --- Core contract ---

    def read_card(self, timeout_seconds: float = 1.0) -> Optional[str]:
        if not self._open:
            raise RuntimeError("MockRfidService is not open")

        # 1. Check scripted queue first
        with self._lock:
            if self._scripted:
                return self._scripted.pop(0)

        # 2. Check tap file
        if self._tap_file.exists():
            try:
                content = self._tap_file.read_text(encoding="utf-8").strip()
                self._tap_file.unlink(missing_ok=True)
                if content:
                    logger.info("MockRfidService read from tap file: %s", content)
                    return content
            except OSError as exc:
                logger.warning("MockRfidService failed to read tap file: %s", exc)

        # 3. Block for timeout
        time.sleep(timeout_seconds)
        return None