"""
T.A.G.A.P. - Database Engine & Session Management

Centralizes SQLAlchemy engine creation and session lifecycle.
All repository code must use `get_db()` context manager.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from config import settings
from models.base import Base

logger = logging.getLogger(__name__)


# ============================================================
# Engine
# ============================================================

def _build_engine() -> Engine:
    """Build SQLAlchemy engine. SQLite needs special handling."""
    url = settings.DATABASE_URL

    # Ensure the DB directory exists
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(
        url,
        echo=False,                      # Don't print every SQL (noisy)
        future=True,                     # Use SQLAlchemy 2.0 style
        connect_args={
            # SQLite-specific: allow threads to share the connection
            # (required for background SMS worker + UI thread)
            "check_same_thread": False,
            "timeout": 15,               # Wait 15s on lock (avoid crashes)
        },
    )

    # Enable SQLite foreign key enforcement (OFF by default!)
    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")   # Better concurrency
        cursor.close()

    return engine


engine: Engine = _build_engine()


# ============================================================
# Session factory
# ============================================================

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,   # Avoids lazy-load errors after commit
)


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """
    Provide a transactional database session.

    Usage:
        with get_db() as db:
            card = db.query(Card).first()

    On success -> auto-commit.
    On exception -> auto-rollback and re-raise.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Database transaction failed")
        raise
    finally:
        db.close()


# ============================================================
# Schema initialization
# ============================================================

def init_db() -> None:
    """
    Create all tables if they don't exist.

    Safe to call on every boot. For MVP we use create_all.
    If schema evolves, we'll add Alembic in a later sprint.
    """
    # Import models here so they register with Base.metadata
    # (circular import avoidance).
    import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    logger.info("Database schema initialized at %s", settings.db_path)


def drop_db() -> None:
    """DANGER: Drop all tables. Used only in tests / factory reset."""
    Base.metadata.drop_all(bind=engine)
    logger.warning("Database schema dropped at %s", settings.db_path)