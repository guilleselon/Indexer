"""Checkpoints repository (per-adapter progress)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from indexer.persistence.models.checkpoints import Checkpoint


def get_checkpoint(session: Session, chain_id: int, adapter: str) -> Checkpoint | None:
    return session.execute(
        select(Checkpoint).where(
            Checkpoint.chain_id == chain_id,
            Checkpoint.adapter == adapter,
        )
    ).scalar_one_or_none()


def get_last_block(session: Session, chain_id: int, adapter: str) -> int:
    """Last processed block. 0 if nothing has ever been processed."""
    cp = get_checkpoint(session, chain_id, adapter)
    return cp.last_block if cp else 0


def set_checkpoint(
    session: Session,
    chain_id: int,
    adapter: str,
    last_block: int,
    last_block_hash: str | None = None,
) -> Checkpoint:
    """Create or update the checkpoint. Idempotent."""
    cp = get_checkpoint(session, chain_id, adapter)
    if cp is None:
        cp = Checkpoint(
            chain_id=chain_id,
            adapter=adapter,
            last_block=last_block,
            last_block_hash=last_block_hash.lower() if last_block_hash else None,
        )
        session.add(cp)
    else:
        cp.last_block = last_block
        cp.last_block_hash = last_block_hash.lower() if last_block_hash else None
    session.flush()
    return cp
