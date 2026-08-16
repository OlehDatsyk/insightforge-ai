"""
database.py
============
SQLAlchemy engine/session setup.

Uses SQLite by default (zero-config local development) but the engine is
constructed generically so pointing ``DATABASE_URL`` at a PostgreSQL
connection string (e.g. the one Render or Railway inject when you attach a
Postgres add-on) works with no code changes.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import get_settings

settings = get_settings()

# SQLite needs a special connect arg to allow use across threads (FastAPI's
# thread pool for sync endpoints). Postgres/other engines don't need it.
_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

# Ensure the directory for a SQLite file DB exists before the engine tries
# to open it.
if settings.database_url.startswith("sqlite:///"):
    db_path = settings.database_url.replace("sqlite:///", "", 1)
    if db_path not in (":memory:", ""):
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

engine = create_engine(settings.database_url, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    """Create all tables if they do not already exist."""
    import models  # noqa: F401  (ensures models are registered on Base.metadata)

    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a request-scoped DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Context manager for use outside of FastAPI request handlers (e.g. the agent)."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
