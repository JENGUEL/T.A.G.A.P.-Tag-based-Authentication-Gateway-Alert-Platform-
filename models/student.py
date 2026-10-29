"""Student entity — belongs to a room, linked to parents."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampMixin
from models.student_parent import student_parents

if TYPE_CHECKING:
    from models.parent import Parent
    from models.room import Room


class Student(Base, TimestampMixin):
    __tablename__ = "students"

    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    room: Mapped["Room"] = relationship(back_populates="students")
    parents: Mapped[list["Parent"]] = relationship(
        secondary=student_parents,
        back_populates="students",
    )

    def __repr__(self) -> str:
        return f"<Student id={self.id} name={self.name!r}>"