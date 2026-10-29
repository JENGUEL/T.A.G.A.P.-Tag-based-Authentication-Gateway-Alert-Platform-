"""
T.A.G.A.P. - Services Package & Dependency Injection Factory
"""

from __future__ import annotations

import logging

from config import settings
from services.interfaces import IRfidService, ISmsService

logger = logging.getLogger(__name__)

_rfid_singleton: IRfidService | None = None
_sms_singleton: ISmsService | None = None


def get_rfid_service() -> IRfidService:
    global _rfid_singleton
    if _rfid_singleton is not None:
        return _rfid_singleton
    if settings.USE_MOCK_RFID:
        from services.adapters.rfid_mock import MockRfidService
        _rfid_singleton = MockRfidService()
        logger.info("DI: Using MockRfidService")
    else:
        from services.adapters.rfid_real import SerialRfidService
        _rfid_singleton = SerialRfidService(
            port=settings.RFID_PORT, baudrate=settings.RFID_BAUDRATE,
        )
        logger.info("DI: Using SerialRfidService on %s", settings.RFID_PORT)
    return _rfid_singleton


def get_sms_service() -> ISmsService:
    global _sms_singleton
    if _sms_singleton is not None:
        return _sms_singleton
    if settings.USE_MOCK_SMS:
        from services.adapters.sms_mock import MockSmsService
        _sms_singleton = MockSmsService()
        logger.info("DI: Using MockSmsService")
    else:
        from services.adapters.sms_real import Sim800SmsService
        _sms_singleton = Sim800SmsService(
            port=settings.GSM_PORT,
            baudrate=settings.GSM_BAUDRATE,
            timeout_seconds=settings.GSM_TIMEOUT_SECONDS,
        )
        logger.info("DI: Using Sim800SmsService on %s", settings.GSM_PORT)
    return _sms_singleton


def reset_services() -> None:
    global _rfid_singleton, _sms_singleton
    if _rfid_singleton:
        try:
            _rfid_singleton.close()
        except Exception:
            pass
    if _sms_singleton:
        try:
            _sms_singleton.close()
        except Exception:
            pass
    _rfid_singleton = None
    _sms_singleton = None
    logger.debug("DI: services reset")