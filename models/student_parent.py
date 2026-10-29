"""Association table: student <-> parent (many-to-many)."""

from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Integer, Table

from models.base import Base


student_parents = Table(
    "student_parents",
    Base.metadata,
    Column("student_id", Integer, ForeignKey("students.id", ondelete="CASCADE"), primary_key=True),
    Column("parent_id", Integer, ForeignKey("parents.id", ondelete="CASCADE"), primary_key=True),
)