"""Shared FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Query
from sqlalchemy.orm import Session

from indexer.config import get_settings
from indexer.persistence.db import session_scope


def get_db() -> Iterator[Session]:
    """Per-request session. Commit at the end, rollback on failure."""
    with session_scope() as session:
        yield session


def pagination(
    limit: int = Query(100, ge=1, le=1000, description="Maximum rows"),
    offset: int = Query(0, ge=0, description="Offset"),
) -> tuple[int, int]:
    return limit, offset


def default_chain_id() -> int:
    """chain_id configured in .env. Base for single-chain endpoints."""
    return get_settings().chain_id
