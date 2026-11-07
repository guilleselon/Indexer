"""Healthchecks for orchestrators (Render, Railway, VPS, Docker)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from indexer.api.deps import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness: the process is alive. Does not touch dependencies."""
    return {"status": "ok"}


@router.get("/ready")
def ready(db: Session = Depends(get_db)) -> dict[str, str]:
    """Readiness: the DB responds. For orchestrators waiting for startup."""
    db.execute(text("SELECT 1"))
    return {"status": "ready"}
