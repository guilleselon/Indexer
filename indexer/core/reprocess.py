"""Reprocessing from raw_logs: re-runs handlers without calling the RPC.

This module is the whole reason the `raw_logs` table exists: the source of
truth of what we already saw on-chain. It lets you change handlers, fix
decoding bugs, or rebuild an adapter's domain without paying for RPC again.

Does not modify checkpoints: reprocessing is not indexing. The checkpoint
reflects how far we've read from the chain, not how many times we've
processed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from indexer.adapters.base import BaseAdapter
from indexer.core.decoder import Decoder
from indexer.core.errors import DecodingError
from indexer.persistence.repositories import blocks as blocks_repo
from indexer.persistence.repositories import raw_logs as raw_logs_repo

logger = logging.getLogger(__name__)


@dataclass
class ReprocessStats:
    logs_read: int = 0
    events_decoded: int = 0
    events_dispatched: int = 0
    decode_errors: int = 0


def _raw_log_to_dict(raw: Any) -> dict[str, Any]:
    """Rebuild a web3-style dict from a RawLog row."""
    return {
        "blockNumber": raw.block_number,
        "blockHash": raw.block_hash,
        "transactionHash": raw.tx_hash,
        "transactionIndex": raw.tx_index,
        "logIndex": raw.log_index,
        "address": raw.address,
        "topics": list(raw.topics),
        "data": raw.data,
    }


def _timestamps_by_block(
    session: Session, chain_id: int, from_block: int, to_block: int
) -> dict[int, datetime]:
    """Timestamps of the stored blocks in the range."""
    blocks = blocks_repo.get_blocks_range(session, chain_id, from_block, to_block)
    return {b.number: b.timestamp for b in blocks}


def reprocess(
    session: Session,
    adapter: BaseAdapter,
    from_block: int,
    to_block: int,
    *,
    clean: bool = False,
) -> ReprocessStats:
    """Re-run the adapter's handlers over the range's raw_logs.

    clean=True: call adapter.rollback(from, to) first to wipe the current
    domain for the range. Useful when you changed a handler's logic and want
    to rebuild from scratch. raw_logs are NOT deleted.

    Idempotent: if clean=False and the handlers already inserted their rows,
    each domain table's unique constraint prevents duplicates and the
    handlers do a prior SELECT (or fail silently on flush).
    """
    if from_block > to_block:
        return ReprocessStats()

    if clean:
        adapter.rollback(from_block, to_block, session)
        logger.info("reprocess clean: rollback %s..%s", from_block, to_block)

    raw_logs = raw_logs_repo.get_logs_range(
        session, adapter.chain_id, from_block, to_block
    )
    if not raw_logs:
        logger.info("reprocess: no raw_logs in %s..%s", from_block, to_block)
        return ReprocessStats()

    decoder = Decoder(adapter.event_abi(), adapter.chain_id)
    handlers = adapter.event_handlers()
    timestamps = _timestamps_by_block(session, adapter.chain_id, from_block, to_block)

    stats = ReprocessStats(logs_read=len(raw_logs))

    for raw in raw_logs:
        log_dict = _raw_log_to_dict(raw)
        try:
            event = decoder.decode(
                log_dict,
                block_timestamp=timestamps.get(
                    raw.block_number,
                    datetime.now(timezone.utc).replace(tzinfo=None),
                ),
            )
        except DecodingError as exc:
            stats.decode_errors += 1
            logger.debug(
                "reprocess skip %s:%s - %s",
                raw.block_number, raw.log_index, exc,
            )
            continue

        stats.events_decoded += 1
        handler = handlers.get(event.event_name)
        if handler is None:
            continue
        handler(event, session)
        stats.events_dispatched += 1

    session.flush()
    logger.info(
        "reprocess %s..%s: %s logs, %s decoded, %s dispatched, %s errors",
        from_block, to_block,
        stats.logs_read, stats.events_decoded,
        stats.events_dispatched, stats.decode_errors,
    )
    return stats
