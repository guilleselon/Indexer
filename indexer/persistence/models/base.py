"""Base declarativa y utilidades compartidas de modelos."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base declarativa de todos los modelos."""


def utcnow() -> datetime:
    """UTC naive (SQLite no maneja tz-aware, y Postgres lo acepta como UTC)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
