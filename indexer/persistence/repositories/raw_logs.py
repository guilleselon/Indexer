"""Raw logs repository. Idempotent by (chain_id, block_number, log_index)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from indexer.persistence.models.raw_logs import RawLog


def _hex(value: Any) -> str:
    if isinstance(value, (bytes, bytearray)):
        return "0x" + bytes(value).hex()
    s = str(value)
    if s.startswith(("0x", "0X")):
        return s.lower()
    return "0x" + s.lower()


def _to_raw_log(chain_id: int, log: dict[str, Any]) -> RawLog:
    topics = [_hex(t) for t in (log.get("topics") or [])]
    return RawLog(
        chain_id=chain_id,
        block_number=int(log["blockNumber"]),
        block_hash=_hex(log["blockHash"]),
        log_index=int(log["logIndex"]),
        tx_hash=_hex(log["transactionHash"]),
        tx_index=int(log.get("transactionIndex") or 0),
        address=str(log["address"]),
        topic0=topics[0] if topics else None,
        topics=topics,
        data=_hex(log.get("data") or b""),
    )


def insert_logs(session: Session, chain_id: int, logs: list[dict[str, Any]]) -> int:
    """Insert logs avoiding duplicates. Returns how many were inserted."""
    if not logs:
        return 0

    blocks = [int(l["blockNumber"]) for l in logs]
    from_block, to_block = min(blocks), max(blocks)

    existing = session.execute(
        select(RawLog.block_number, RawLog.log_index).where(
            RawLog.chain_id == chain_id,
            RawLog.block_number >= from_block,
            RawLog.block_number <= to_block,
        )
    ).all()
    existing_set = {(b, i) for b, i in existing}

    new_rows = [
        _to_raw_log(chain_id, log)
        for log in logs
        if (int(log["blockNumber"]), int(log["logIndex"])) not in existing_set
    ]
    if not new_rows:
        return 0

    session.add_all(new_rows)
    session.flush()
    return len(new_rows)


def get_logs_range(
    session: Session,
    chain_id: int,
    from_block: int,
    to_block: int,
    addresses: list[str] | None = None,
) -> list[RawLog]:
    """Raw logs in [from_block, to_block], optionally filtered by address.

    Useful for reprocessing a range without calling the RPC again.
    """
    stmt = select(RawLog).where(
        RawLog.chain_id == chain_id,
        RawLog.block_number >= from_block,
        RawLog.block_number <= to_block,
    )
    if addresses:
        normalized = {a.lower() for a in addresses}
        stmt = stmt.where(RawLog.address.in_(normalized))
    stmt = stmt.order_by(RawLog.block_number, RawLog.log_index)
    return list(session.execute(stmt).scalars())


def delete_logs_from(
    session: Session, chain_id: int, from_block: int, to_block: int
) -> int:
    """Delete logs in the range. Used by the reorg flow."""
    result = session.execute(
        delete(RawLog).where(
            RawLog.chain_id == chain_id,
            RawLog.block_number >= from_block,
            RawLog.block_number <= to_block,
        )
    )
    return result.rowcount or 0
