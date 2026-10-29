"""
T.A.G.A.P. - SQLAlchemy Declarative Base

All ORM models inherit from `Base`. Provides common columns:
- id (primary key)
- created_at / updated_at (UTC timestamps)
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    """Timezone-aware UTC now. Used as default for timestamps."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Declarative base for all T.A.G.A.P. models."""


class TimestampMixin:
    """Adds id, created_at, updated_at columns to a model."""

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )