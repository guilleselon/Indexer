"""Repositorio de auditoría de reorgs."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from indexer.persistence.models.reorg_events import ReorgEvent


def record_reorg(
    session: Session,
    *,
    chain_id: int,
    adapter: str,
    from_block: int,
    to_block: int,
    old_hash: str | None,
    new_hash: str | None,
    depth: int,
) -> ReorgEvent:
    """Registra un reorg detectado. Solo auditoría, no afecta a la lógica."""
    row = ReorgEvent(
        chain_id=chain_id,
        adapter=adapter,
        from_block=from_block,
        to_block=to_block,
        old_hash=old_hash.lower() if old_hash else None,
        new_hash=new_hash.lower() if new_hash else None,
        depth=depth,
    )
    session.add(row)
    session.flush()
    return row


def list_reorgs(
    session: Session,
    chain_id: int | None = None,
    adapter: str | None = None,
) -> list[ReorgEvent]:
    stmt = select(ReorgEvent).order_by(ReorgEvent.detected_at.desc())
    if chain_id is not None:
        stmt = stmt.where(ReorgEvent.chain_id == chain_id)
    if adapter is not None:
        stmt = stmt.where(ReorgEvent.adapter == adapter)
    return list(session.execute(stmt).scalars())
