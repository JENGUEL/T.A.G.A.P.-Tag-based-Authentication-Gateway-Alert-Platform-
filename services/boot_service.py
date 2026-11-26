"""
T.A.G.A.P. - Boot Service

Performs critical system checks before the kiosk UI is allowed to load.
Returns a list of non-fixable errors.
"""
import logging
from pathlib import Path
from typing import Callable, Optional

from core.exceptions import RfidConnectionError, GsmConnectionError
from data.database import init_db, get_db
from data.repositories import CardRepository
from services import get_rfid_service, get_sms_service
from config import settings

logger = logging.getLogger(__name__)

def run_preflight_checks(
    progress_callback: Optional[Callable[[str], None]] = None,
    *,
    check_rfid: bool = True,
) -> list[str]:
    """
    Runs all system diagnostics.
    Returns a list of error messages. Empty list = all good.
    """
    errors: list[str] = []

    def report(message: str) -> None:
        logger.info("Preflight: %s", message)
        if progress_callback is not None:
            progress_callback(message)

    # 0. Repair required directories
    report("Preparing required data and log directories")
    try:
        settings.db_path.parent.mkdir(parents=True, exist_ok=True)
        settings.log_path.parent.mkdir(parents=True, exist_ok=True)
        Path("data/mock_sms_outbox").mkdir(parents=True, exist_ok=True)
        Path("data").mkdir(parents=True, exist_ok=True)
        logger.info("Boot Check: Required directories OK")
    except Exception as exc:
        logger.exception("Boot Check: Directory repair failed")
        errors.append(f"File storage: {exc}")

    # 1. Database Check
    report("Checking SQLite integrity and seed data")
    try:
        init_db()
        with get_db() as db:
            CardRepository.get_all_active(db)
            quick_check = db.connection().exec_driver_sql("PRAGMA quick_check").scalar()
            if quick_check != "ok":
                raise RuntimeError(f"SQLite integrity check failed: {quick_check}")

        # Repair missing demo records and update the deployed school identity.
        from data.seed import seed
        seed()
        logger.info("Boot Check: Database and seed data OK")
    except Exception as exc:
        logger.exception("Boot Check: DB Failed")
        errors.append(f"Database failure: {exc}")

    # 1B. Compile-check application Python source. This never changes source.
    report("Checking application source syntax")
    try:
        roots = [Path("main.py"), Path("core"), Path("data"), Path("models"),
                 Path("services"), Path("ui")]
        for root in roots:
            files = [root] if root.is_file() else root.rglob("*.py")
            for source in files:
                compile(source.read_text(encoding="utf-8"), str(source), "exec")
        logger.info("Boot Check: Python source syntax OK")
    except Exception as exc:
        logger.exception("Boot Check: Source syntax failed")
        errors.append(f"Application source: {exc}")

    if check_rfid:
        report("Checking RFID connection")
        try:
            rfid = get_rfid_service()
            if not rfid.is_connected():
                rfid.open()
            logger.info("Boot Check: RFID OK")
        except (RfidConnectionError, Exception) as e:
            logger.exception("Boot Check: RFID Failed")
            errors.append(f"RFID Reader: {str(e)}")

    # 3. GSM Hardware Check
    report("Checking GSM connection")
    try:
        sms = get_sms_service()
        if not sms.is_connected():
            sms.open()
        logger.info("Boot Check: GSM OK")
    except (GsmConnectionError, Exception) as e:
        logger.exception("Boot Check: GSM Failed")
        errors.append(f"GSM Module: {str(e)}")

    report("System preflight complete")
    return errors


def get_system_status() -> dict[str, dict[str, object]]:
    """Collect live status used by the kiosk status modal."""
    status: dict[str, dict[str, object]] = {}
    if settings.USE_MOCK_RFID:
        mode_detail = "Simulation mode; real RFID and SMS hardware are not used"
        mode_label = "SIMULATION MODE"
        mode_color = "#D9A05B"
    else:
        mode_detail = f"Real RFID reader selected on {settings.RFID_PORT}"
        mode_label = "REAL HARDWARE"
        mode_color = "#397E68"
    status["mode"] = {
        "label": "Operating mode",
        "connected": True,
        "detail": mode_detail,
        "state": mode_label,
        "color": mode_color,
    }

    try:
        with get_db() as db:
            db.connection().exec_driver_sql("SELECT 1").scalar()
        status["database"] = {
            "label": "Database",
            "connected": True,
            "detail": "SQLite healthy",
        }
    except Exception as exc:
        status["database"] = {
            "label": "Database",
            "connected": False,
            "detail": str(exc),
        }

    try:
        rfid = get_rfid_service()
        connected = rfid.is_connected()
        status["rfid"] = {
            "label": "RFID reader",
            "connected": connected,
            "detail": "Simulated reader" if settings.USE_MOCK_RFID else f"Verified Arduino reader · {settings.RFID_PORT}",
            "state": "SIMULATED" if settings.USE_MOCK_RFID else "Connected" if connected else "Disconnected",
            "color": "#D9A05B" if settings.USE_MOCK_RFID else "#397E68" if connected else "#BA384B",
        }
        if not settings.USE_MOCK_RFID:
            status["mode"] = {
                "label": "Operating mode",
                "connected": connected,
                "detail": (
                    f"Verified Arduino reader on {settings.RFID_PORT}"
                    if connected
                    else "Real reader selected but not connected"
                ),
                "state": "REAL HARDWARE" if connected else "READER OFFLINE",
                "color": "#397E68" if connected else "#BA384B",
            }
    except Exception as exc:
        status["rfid"] = {
            "label": "RFID reader",
            "connected": False,
            "detail": str(exc),
            "state": "Disconnected",
            "color": "#BA384B",
        }

    try:
        sms = get_sms_service()
        connected = sms.is_connected()
        signal = sms.signal_strength()
        status["gsm"] = {
            "label": "GSM module",
            "connected": connected,
            "detail": (
                f"Mock SMS · signal {signal}/31"
                if settings.USE_MOCK_SMS
                else f"Serial modem · signal {signal}/31"
                if signal is not None
                else "Serial modem"
            ),
            "state": "SIMULATED" if settings.USE_MOCK_SMS else "Connected" if connected else "Disconnected",
            "color": "#D9A05B" if settings.USE_MOCK_SMS else "#397E68" if connected else "#BA384B",
        }
    except Exception as exc:
        status["gsm"] = {
            "label": "GSM module",
            "connected": False,
            "detail": str(exc),
            "state": "Disconnected",
            "color": "#BA384B",
        }

    if settings.USE_MOCK_RFID and settings.USE_MOCK_SMS:
        status["mode"] = {
            "label": "Operating mode",
            "connected": True,
            "detail": "RFID and SMS are simulated",
            "state": "SIMULATION MODE",
            "color": "#D9A05B",
        }
    elif settings.USE_MOCK_RFID or settings.USE_MOCK_SMS:
        status["mode"] = {
            "label": "Operating mode",
            "connected": True,
            "detail": (
                f"RFID: {status['rfid']['state']}; GSM: {status['gsm']['state']}"
            ),
            "state": "MIXED MODE",
            "color": "#D9A05B",
        }
    else:
        missing_devices = [
            str(status[name]["label"])
            for name in ("rfid", "gsm")
            if not status[name]["connected"]
        ]
        status["mode"] = {
            "label": "Operating mode",
            "connected": not missing_devices,
            "detail": (
                "RFID and GSM are connected"
                if not missing_devices
                else f"Unavailable: {', '.join(missing_devices)}"
            ),
            "state": "REAL HARDWARE" if not missing_devices else "DEGRADED MODE",
            "color": "#397E68" if not missing_devices else "#D9A05B",
        }

    return status