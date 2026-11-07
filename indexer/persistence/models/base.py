"""Declarative base and shared model utilities."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all models."""


def utcnow() -> datetime:
    """Naive UTC (SQLite doesn't handle tz-aware, Postgres accepts it as UTC)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
