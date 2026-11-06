"""Healthchecks para orquestadores (Render, Railway, VPS, Docker)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from indexer.api.deps import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness: el proceso está vivo. No toca dependencias."""
    return {"status": "ok"}


@router.get("/ready")
def ready(db: Session = Depends(get_db)) -> dict[str, str]:
    """Readiness: la DB responde. Para orquestadores que esperan a que arranque."""
    db.execute(text("SELECT 1"))
    return {"status": "ready"}
