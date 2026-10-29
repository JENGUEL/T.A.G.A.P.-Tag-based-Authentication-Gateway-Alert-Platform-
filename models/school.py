"""School entity — top of the hierarchy."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from models.police_station import PoliceStation
    from models.room import Room


class School(Base, TimestampMixin):
    __tablename__ = "schools"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    hotline: Mapped[str] = mapped_column(String(20), nullable=False)

    # Relations
    rooms: Mapped[list["Room"]] = relationship(back_populates="school", cascade="all, delete-orphan")
    police_stations: Mapped[list["PoliceStation"]] = relationship(
        back_populates="school", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<School id={self.id} name={self.name!r}>"