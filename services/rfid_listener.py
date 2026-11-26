"""
T.A.G.A.P. - RFID Watchdog Listener

Continuously polls the hardware in the background.
Retries initial discovery and reports runtime disconnects for operator recovery.
"""
import asyncio
import logging
import time
import flet as ft
from typing import Callable, Optional

from core.exceptions import RfidConnectionError
from services import get_rfid_service

logger = logging.getLogger(__name__)


class RfidListener:
    DEVICE_DETECTION_INTERVAL_SECONDS = 3

    def __init__(
        self,
        page: ft.Page,
        on_card_scanned: Callable[[str], None],
        on_connection_changed: Optional[Callable[[bool], None]] = None,
    ):
        self.page = page
        self.on_card_scanned = on_card_scanned
        self.on_connection_changed = on_connection_changed
        self.rfid = get_rfid_service()
        self.is_running = True

    def start(self):
        self.is_running = True
        self.page.run_task(self._listen_loop)

    def stop(self):
        self.is_running = False

    async def _listen_loop(self):
        logger.info("RFID Watchdog started.")
        rfid_connected = self.rfid.is_connected()
        has_connected = rfid_connected
        next_device_check_at = 0.0

        while self.is_running:
            try:
                now = time.monotonic()
                if rfid_connected and now >= next_device_check_at:
                    next_device_check_at = (
                        now + self.DEVICE_DETECTION_INTERVAL_SECONDS
                    )
                    device_present = await asyncio.to_thread(
                        self.rfid.is_device_present
                    )
                    if not self.is_running:
                        break
                    if not device_present:
                        logger.warning("RFID device was removed during operation")
                        self.rfid.close()
                        rfid_connected = False
                        if self.on_connection_changed:
                            self.on_connection_changed(False)
                        self.stop()
                        break

                # Retry initial discovery, but require an operator action after
                # a reader that was in service disconnects.
                if not self.rfid.is_connected():
                    if rfid_connected:
                        logger.warning("RFID disconnected during operation")
                        rfid_connected = False
                        if self.on_connection_changed:
                            self.on_connection_changed(False)
                        self.stop()
                        break

                    if has_connected:
                        await asyncio.sleep(0.2)
                        continue

                    self.rfid.open()
                    rfid_connected = True
                    has_connected = True
                    if self.on_connection_changed:
                        self.on_connection_changed(True)
                    logger.info("RFID Watchdog connected.")

                # 2. Read card (Runs in a thread so it doesn't block the UI)
                # Note: Mock reader returns instantly; real reader waits for timeout
                card_uid = await asyncio.to_thread(self.rfid.read_card, 0.5)

                # 3. Trigger if card found
                if card_uid:
                    logger.info("Watchdog detected card: %s", card_uid)
                    self.on_card_scanned(card_uid)

                    # Debounce: prevent double-reads from the same physical tap
                    await asyncio.sleep(1.5)

            except Exception as e:
                if not self.is_running:
                    break
                if isinstance(e, RfidConnectionError):
                    logger.warning("RFID reader disconnected during read: %s", e)
                else:
                    logger.error("RFID Watchdog error: %s", e)
                if has_connected:
                    try:
                        self.rfid.close()
                    except Exception:
                        logger.exception("Could not close disconnected RFID reader")
                    if rfid_connected and self.on_connection_changed:
                        self.on_connection_changed(False)
                rfid_connected = False
                if has_connected:
                    self.stop()
                    break
                await asyncio.sleep(2.0) # Wait before retrying

            # Small sleep to prevent CPU spinning
            await asyncio.sleep(0.1)