"""Parent / guardian entity — receives SMS."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampMixin
from models.student_parent import student_parents

if TYPE_CHECKING:
    from models.student import Student


class Parent(Base, TimestampMixin):
    __tablename__ = "parents"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    students: Mapped[list["Student"]] = relationship(
        secondary=student_parents,
        back_populates="parents",
    )

    def __repr__(self) -> str:
        return f"<Parent id={self.id} name={self.name!r} phone={self.phone_number!r}>"