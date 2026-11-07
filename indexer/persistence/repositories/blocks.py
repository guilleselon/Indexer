"""Blocks repository."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from indexer.persistence.models.blocks import Block


def insert_block(session: Session, chain_id: int, block: dict[str, Any]) -> Block | None:
    """Insert a block if it doesn't exist. Returns None if it already did."""
    number = int(block["number"])

    exists = session.execute(
        select(Block.id).where(Block.chain_id == chain_id, Block.number == number)
    ).scalar_one_or_none()
    if exists is not None:
        return None

    ts = datetime.fromtimestamp(int(block["timestamp"]), tz=timezone.utc).replace(tzinfo=None)
    row = Block(
        chain_id=chain_id,
        number=number,
        hash=str(block["hash"]).lower(),
        parent_hash=str(block["parentHash"]).lower(),
        timestamp=ts,
    )
    session.add(row)
    session.flush()
    return row


def get_block(session: Session, chain_id: int, number: int) -> Block | None:
    return session.execute(
        select(Block).where(Block.chain_id == chain_id, Block.number == number)
    ).scalar_one_or_none()


def get_blocks_range(
    session: Session, chain_id: int, from_block: int, to_block: int
) -> list[Block]:
    """Stored blocks in [from_block, to_block], sorted ascending."""
    return list(
        session.execute(
            select(Block)
            .where(
                Block.chain_id == chain_id,
                Block.number >= from_block,
                Block.number <= to_block,
            )
            .order_by(Block.number)
        ).scalars()
    )


def delete_blocks_from(
    session: Session, chain_id: int, from_block: int, to_block: int
) -> int:
    """Delete blocks in the range. Used by the reorg flow."""
    result = session.execute(
        delete(Block).where(
            Block.chain_id == chain_id,
            Block.number >= from_block,
            Block.number <= to_block,
        )
    )
    return result.rowcount or 0
