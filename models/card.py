"""RFID card entity — 4 cards per room (Safe/Assist/Danger/Admin)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.constants import CardType
from models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from models.room import Room


class Card(Base, TimestampMixin):
    __tablename__ = "cards"

    uid: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    type: Mapped[str] = mapped_column(
        String(16), nullable=False
    )  # One of CardType values
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), nullable=False, index=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    room: Mapped["Room"] = relationship(back_populates="cards")

    @property
    def card_type(self) -> CardType:
        """Typed access to card type."""
        return CardType(self.type)

    def __repr__(self) -> str:
        return f"<Card uid={self.uid!r} type={self.type!r}>"