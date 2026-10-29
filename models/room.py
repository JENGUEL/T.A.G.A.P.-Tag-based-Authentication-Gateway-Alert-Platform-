"""Room entity — one kiosk = one room."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from models.card import Card
    from models.school import School
    from models.student import Student


class Room(Base, TimestampMixin):
    __tablename__ = "rooms"

    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    wing: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    floor: Mapped[str] = mapped_column(String(20), nullable=False, default="")

    school: Mapped["School"] = relationship(back_populates="rooms")
    students: Mapped[list["Student"]] = relationship(back_populates="room", cascade="all, delete-orphan")
    cards: Mapped[list["Card"]] = relationship(back_populates="room", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Room id={self.id} name={self.name!r} wing={self.wing!r}>"