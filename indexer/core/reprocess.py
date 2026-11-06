"""Reprocesamiento desde raw_logs: re-ejecuta handlers sin llamar al RPC.

Este módulo es la razón de ser de la tabla `raw_logs`: la fuente de verdad
de lo que ya vimos on-chain. Permite cambiar handlers, corregir bugs de
decodificación o reconstruir el dominio de un adapter sin volver a pagar RPC.

No modifica checkpoints: reprocesar no es indexar. El checkpoint refleja
hasta dónde se ha leído de la cadena, no cuántas veces se ha procesado.
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
    """Reconstruye un dict estilo web3 a partir de una fila RawLog."""
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
    """Timestamps de los bloques almacenados en el rango."""
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
    """Re-ejecuta los handlers del adapter sobre los raw_logs del rango.

    clean=True: llama primero a adapter.rollback(from, to) para borrar el
    dominio actual del rango. Útil cuando cambiaste la lógica de un handler
    y quieres reconstruir desde cero. Los raw_logs NO se borran.

    Idempotente: si clean=False y los handlers ya insertaron sus filas,
    la unique constraint de cada tabla de dominio evita duplicados y los
    handlers hacen un SELECT previo (o fallan silenciosamente en flush).
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
        logger.info("reprocess: sin raw_logs en %s..%s", from_block, to_block)
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
