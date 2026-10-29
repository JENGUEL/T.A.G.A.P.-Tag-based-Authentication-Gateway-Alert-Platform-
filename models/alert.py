"""Alert — a single incident recorded when a card is confirmed."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from models.room import Room
    from models.sms_queue import SmsQueue


class Alert(Base, TimestampMixin):
    __tablename__ = "alerts"

    card_uid: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    card_type: Mapped[str] = mapped_column(String(16), nullable=False)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), nullable=False, index=True)

    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    room: Mapped["Room"] = relationship()
    sms_messages: Mapped[list["SmsQueue"]] = relationship(
        back_populates="alert", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Alert id={self.id} card={self.card_type!r} room_id={self.room_id}>"