"""
T.A.G.A.P. - RFID Watchdog Listener

Continuously polls the hardware in the background.
Handles disconnects gracefully and auto-reconnects.
"""
import asyncio
import logging
import flet as ft
from typing import Callable, Optional

from services import get_rfid_service

logger = logging.getLogger(__name__)

class RfidListener:
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

        while self.is_running:
            try:
                # 1. Ensure connection (Auto-reconnect)
                if not self.rfid.is_connected():
                    if rfid_connected:
                        logger.warning("RFID disconnected. Attempting reconnect...")
                        rfid_connected = False

                    self.rfid.open()
                    rfid_connected = True
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
                logger.error("RFID Watchdog error: %s", e)
                if rfid_connected and self.on_connection_changed:
                    self.on_connection_changed(False)
                rfid_connected = False
                await asyncio.sleep(2.0) # Wait before retrying

            # Small sleep to prevent CPU spinning
            await asyncio.sleep(0.1)