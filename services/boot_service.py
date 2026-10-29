"""
T.A.G.A.P. - Boot Service

Performs critical system checks before the kiosk UI is allowed to load.
Returns a list of errors. If the list is empty, the system is healthy.
"""
import logging
from core.exceptions import RfidConnectionError, GsmConnectionError
from data.database import init_db, get_db
from data.repositories import CardRepository
from services import get_rfid_service, get_sms_service

logger = logging.getLogger(__name__)

def run_preflight_checks() -> list[str]:
    """
    Runs all system diagnostics.
    Returns a list of error messages. Empty list = all good.
    """
    errors = []

    # 1. Database Check
    try:
        init_db()
        with get_db() as db:
            CardRepository.get_all_active(db) # Simple test query
        logger.info("Boot Check: Database OK")
    except Exception as e:
        logger.exception("Boot Check: DB Failed")
        errors.append(f"Database failure: {str(e)}")

    # 2. RFID Hardware Check
    try:
        rfid = get_rfid_service()
        if not rfid.is_connected():
            rfid.open() # Attempt to connect
        logger.info("Boot Check: RFID OK")
    except (RfidConnectionError, Exception) as e:
        logger.exception("Boot Check: RFID Failed")
        errors.append(f"RFID Reader: {str(e)}")

    # 3. GSM Hardware Check
    try:
        sms = get_sms_service()
        if not sms.is_connected():
            sms.open()
        logger.info("Boot Check: GSM OK")
    except (GsmConnectionError, Exception) as e:
        logger.exception("Boot Check: GSM Failed")
        errors.append(f"GSM Module: {str(e)}")

    return errors