"""Dependencias compartidas de FastAPI."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Query
from sqlalchemy.orm import Session

from indexer.config import get_settings
from indexer.persistence.db import session_scope


def get_db() -> Iterator[Session]:
    """Sesión por request. Commit al final, rollback si falla."""
    with session_scope() as session:
        yield session


def pagination(
    limit: int = Query(100, ge=1, le=1000, description="Máximo de filas"),
    offset: int = Query(0, ge=0, description="Desplazamiento"),
) -> tuple[int, int]:
    return limit, offset


def default_chain_id() -> int:
    """chain_id configurado en .env. Base para endpoints de una sola cadena."""
    return get_settings().chain_id
