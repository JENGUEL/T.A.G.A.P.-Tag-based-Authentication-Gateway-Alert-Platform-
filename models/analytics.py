"""Analytics — research metrics for each alert."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, TimestampMixin


class Analytics(Base, TimestampMixin):
    __tablename__ = "analytics"

    alert_id: Mapped[int] = mapped_column(ForeignKey("alerts.id"), nullable=False, index=True)

    scan_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confirm_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    queue_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delivery_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:
        return f"<Analytics alert_id={self.alert_id}>"