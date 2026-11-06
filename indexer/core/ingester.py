"""Ingester: bucle principal que une RPC, decoder, adapter y persistencia."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from indexer.adapters.base import BaseAdapter
from indexer.config import Settings
from indexer.core.decoder import Decoder
from indexer.core.errors import DecodingError, ReorgDetected
from indexer.core.reorg import detect
from indexer.core.rpc import RPCClient
from indexer.persistence.db import session_scope
from indexer.persistence.repositories import blocks as blocks_repo
from indexer.persistence.repositories import checkpoints as cp_repo
from indexer.persistence.repositories import raw_logs as raw_logs_repo
from indexer.persistence.repositories import reorg_events as reorg_repo

logger = logging.getLogger(__name__)


@dataclass
class IngestStats:
    iterations: int = 0
    events_processed: int = 0
    blocks_processed: int = 0
    reorgs_handled: int = 0


def run(
    adapter: BaseAdapter,
    rpc: RPCClient,
    settings: Settings,
    *,
    from_block: int | None = None,
    to_block: int | None = None,
    tail: bool = False,
    skip_backlog: bool = False,
    max_iterations: int | None = None,
    poll_interval: int = 12,
    checkpoint_key: str | None = None,
    max_block_range: int | None = None,
) -> IngestStats:
    """Ejecuta el ingester para un adapter."""
    if adapter.chain_id != settings.chain_id:
        raise ValueError(
            f"adapter.chain_id={adapter.chain_id} != settings.chain_id={settings.chain_id}"
        )

    cp_key = checkpoint_key or adapter.name
    block_range = max_block_range or settings.max_block_range

    if from_block is not None:
        with session_scope() as session:
            cp_repo.set_checkpoint(
                session, adapter.chain_id, cp_key, from_block - 1, None
            )
                
    elif skip_backlog:  # <-- Corregido: funciona sin --tail
        head = rpc.block_number() - settings.confirmations
        with session_scope() as session:
            current_cp = cp_repo.get_last_block(session, adapter.chain_id, cp_key)
            if head > current_cp:
                logger.info("skip-backlog activado: saltando de %s a %s", current_cp, head)
                block = rpc.block(head)
                cp_repo.set_checkpoint(
                    session, adapter.chain_id, cp_key, head, str(block["hash"])
                )

    stats = IngestStats()
    while True:
        with session_scope() as session:
            result = _run_once(
                session, adapter, rpc, settings, to_block, cp_key, block_range
            )

        if result is None:
            if tail:
                with session_scope() as session:
                    cp = cp_repo.get_last_block(session, adapter.chain_id, cp_key)
                logger.info(
                    "tail: sin bloques nuevos (checkpoint=%s), durmiendo %ss",
                    cp, poll_interval,
                )
                time.sleep(poll_interval)
                continue
            break

        events, range_size, was_reorg = result
        stats.events_processed += events
        stats.blocks_processed += range_size
        stats.iterations += 1
        if was_reorg:
            stats.reorgs_handled += 1

        if max_iterations is not None and stats.iterations >= max_iterations:
            break

    return stats


def _run_once(
    session: Session,
    adapter: BaseAdapter,
    rpc: RPCClient,
    settings: Settings,
    to_block: int | None,
    checkpoint_key: str,
    max_block_range: int,
) -> tuple[int, int, bool] | None:
    """Una iteración."""
    chain_id = adapter.chain_id

    reorg = detect(session, rpc, chain_id, adapter.name, checkpoint_key=checkpoint_key)
    if reorg is not None:
        _handle_reorg(session, adapter, reorg, checkpoint_key)
        logger.warning("reorg handled: blocks %s..%s", reorg.from_block, reorg.to_block)
        return (0, 0, True)

    checkpoint = cp_repo.get_last_block(session, chain_id, checkpoint_key)
    head = rpc.block_number() - settings.confirmations
    start = checkpoint + 1
    end = min(start + max_block_range - 1, head)  # <-- Usa el block_range inyectado
    if to_block is not None:
        end = min(end, to_block)

    if start > end:
        return None

    logs = rpc.logs(start, end, adapter.contract_addresses())

    block_numbers_to_fetch: set[int] = {int(l["blockNumber"]) for l in logs}
    block_numbers_to_fetch.add(end)
    blocks = [rpc.block(n) for n in sorted(block_numbers_to_fetch)]

    for block in blocks:
        blocks_repo.insert_block(session, chain_id, block)
    raw_logs_repo.insert_logs(session, chain_id, logs)

    decoder = Decoder(adapter.event_abi(), chain_id)
    handlers = adapter.event_handlers()
    ts_by_block = {
        int(b["number"]): datetime.fromtimestamp(
            int(b["timestamp"]), tz=timezone.utc
        ).replace(tzinfo=None)
        for b in blocks
    }

    events_processed = 0
    for log in logs:
        try:
            event = decoder.decode(log, block_timestamp=ts_by_block.get(int(log["blockNumber"])))
        except DecodingError as exc:
            logger.debug("skip undecodable log %s:%s - %s", log["blockNumber"], log["logIndex"], exc)
            continue
        handler = handlers.get(event.event_name)
        if handler is None:
            continue
        handler(event, session)
        events_processed += 1

    checkpoint_block = blocks[-1]
    assert int(checkpoint_block["number"]) == end, (
        f"checkpoint_block.number={checkpoint_block['number']} != end={end}"
    )
    cp_repo.set_checkpoint(session, chain_id, checkpoint_key, end, str(checkpoint_block["hash"]))

    range_size = end - start + 1
    logger.info(
        "ingested %s..%s: fetched=%s/%s blocks (%.0f%%), logs=%s, events=%s",
        start, end, len(blocks), range_size, 100.0 * len(blocks) / range_size, len(logs), events_processed,
    )
    return (events_processed, range_size, False)


def _handle_reorg(session: Session, adapter: BaseAdapter, reorg: ReorgDetected, checkpoint_key: str) -> None:
    chain_id = adapter.chain_id
    adapter.rollback(reorg.from_block, reorg.to_block, session)
    raw_logs_repo.delete_logs_from(session, chain_id, reorg.from_block, reorg.to_block)
    blocks_repo.delete_blocks_from(session, chain_id, reorg.from_block, reorg.to_block)
    cp_repo.set_checkpoint(session, chain_id, checkpoint_key, reorg.from_block - 1, None)
    reorg_repo.record_reorg(
        session, chain_id=chain_id, adapter=adapter.name,
        from_block=reorg.from_block, to_block=reorg.to_block,
        old_hash=None, new_hash=None, depth=reorg.to_block - reorg.from_block + 1,
    )
