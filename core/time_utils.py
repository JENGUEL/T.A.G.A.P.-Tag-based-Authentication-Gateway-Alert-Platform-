"""
T.A.G.A.P. - Time Utilities

Centralized handling of timezone-aware vs naive datetimes.

Rule of thumb:
- Store timestamps in DB as UTC **naive** (SQLite limitation).
- Use UTC **aware** inside the application logic.
- Convert with `to_db()` when writing, `from_db()` when reading.
- Use `utc_now()` (aware) in code, never `datetime.utcnow()` (deprecated).
"""

from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Return current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


def to_db(dt: datetime | None) -> datetime | None:
    """
    Convert an aware datetime to a naive UTC datetime for DB storage.
    If already naive, assume it's already UTC and return as-is.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt  # assume caller already gave UTC
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def from_db(dt: datetime | None) -> datetime | None:
    """
    Convert a naive datetime read from the DB to an aware UTC datetime.
    If already aware, leave as-is.
    """
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def safe_diff_ms(later: datetime | None, earlier: datetime | None) -> int | None:
    """
    Compute (later - earlier) in milliseconds, tolerant of
    naive/aware mixes. Returns None if either input is None.
    """
    if later is None or earlier is None:
        return None
    later_a = from_db(later)
    earlier_a = from_db(earlier)
    return int((later_a - earlier_a).total_seconds() * 1000)