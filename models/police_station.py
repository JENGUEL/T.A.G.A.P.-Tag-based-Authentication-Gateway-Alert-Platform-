"""Police station entity — notified on every alert (per school)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from models.school import School


class PoliceStation(Base, TimestampMixin):
    __tablename__ = "police_stations"

    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False)

    school: Mapped["School"] = relationship(back_populates="police_stations")

    def __repr__(self) -> str:
        return f"<PoliceStation id={self.id} name={self.name!r}>"