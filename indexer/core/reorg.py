"""Detección de reorganizaciones de cadena.

Módulo puro: NO ejecuta rollback, solo detecta y devuelve el rango afectado.
El ingester decide qué hacer con esa información (rollback + reindex).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from indexer.core.errors import ReorgDetected
from indexer.core.rpc import RPCClient
from indexer.persistence.repositories import blocks as blocks_repo
from indexer.persistence.repositories import checkpoints as cp_repo


def detect(
    session: Session,
    rpc: RPCClient,
    chain_id: int,
    adapter: str,
    max_depth: int = 64,
    checkpoint_key: str | None = None,
) -> ReorgDetected | None:
    """Compara los bloques almacenados contra el RPC para detectar un reorg.

    checkpoint_key permite usar un checkpoint distinto al del adapter (p.ej.
    'uniswap_v3:backfill'). Por defecto usa `adapter`.
    """
    if max_depth <= 0:
        return None

    cp_key = checkpoint_key or adapter
    last_block = cp_repo.get_last_block(session, chain_id, cp_key)
    if last_block == 0:
        return None

    oldest_to_check = max(last_block - max_depth + 1, 1)
    stored_blocks = blocks_repo.get_blocks_range(
        session, chain_id, oldest_to_check, last_block
    )
    if not stored_blocks:
        return None

    latest = stored_blocks[-1]
    latest_current = rpc.block(latest.number)
    if str(latest_current["hash"]).lower() == latest.hash.lower():
        return None

    found_divergence = latest.number
    for stored in reversed(stored_blocks[:-1]):
        current = rpc.block(stored.number)
        if str(current["hash"]).lower() != stored.hash.lower():
            found_divergence = stored.number
        else:
            break

    return ReorgDetected(
        from_block=found_divergence,
        to_block=last_block,
        reason=f"reorg desde bloque {found_divergence} hasta {last_block}",
    )
