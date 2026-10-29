"""SMS queue — durable outbox for parent + police notifications."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.constants import SmsStatus
from models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from models.alert import Alert


class SmsQueue(Base, TimestampMixin):
    __tablename__ = "sms_queue"

    alert_id: Mapped[int] = mapped_column(ForeignKey("alerts.id"), nullable=False, index=True)

    # "PARENT" or "POLICE"
    recipient_type: Mapped[str] = mapped_column(String(16), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=SmsStatus.PENDING.value, index=True
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    alert: Mapped["Alert"] = relationship(back_populates="sms_messages")

    @property
    def status_enum(self) -> SmsStatus:
        return SmsStatus(self.status)

    def __repr__(self) -> str:
        return f"<SmsQueue id={self.id} to={self.phone_number!r} status={self.status!r}>"