"""Endpoints genéricos del core. Ninguno menciona un adapter concreto."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from web3 import Web3

from indexer.api.deps import default_chain_id, get_db, pagination
from indexer.api.schemas import (
    BlockOut,
    BlocksPage,
    CheckpointOut,
    RawLogOut,
    RawLogsPage,
    ReorgOut,
    StatusResponse,
)
from indexer.config import get_settings
from indexer.persistence.models.blocks import Block
from indexer.persistence.models.checkpoints import Checkpoint
from indexer.persistence.models.raw_logs import RawLog
from indexer.persistence.models.reorg_events import ReorgEvent

router = APIRouter(tags=["core"])


def _try_head(rpc_url: str, timeout: int = 5) -> int | None:
    """Block number actual o None si el RPC no responde. Nunca lanza."""
    try:
        w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": timeout}))
        return int(w3.eth.block_number)
    except Exception:
        return None


@router.get("/status", response_model=StatusResponse)
def status(
    db: Annotated[Session, Depends(get_db)],
    chain_id: Annotated[int, Depends(default_chain_id)],
    include_rpc: bool = Query(True, description="Consultar el head al RPC"),
    reorg_limit: int = Query(10, ge=0, le=100),
) -> StatusResponse:
    """Estado del indexador: checkpoints, head, lag y reorgs recientes."""
    settings = get_settings()

    cps = list(
        db.execute(
            select(Checkpoint).where(Checkpoint.chain_id == chain_id)
        ).scalars()
    )

    head = _try_head(settings.rpc_url) if include_rpc else None
    lag: dict[str, int | None] = {}
    for cp in cps:
        lag[cp.adapter] = (head - cp.last_block) if head is not None else None

    reorgs = list(
        db.execute(
            select(ReorgEvent)
            .where(ReorgEvent.chain_id == chain_id)
            .order_by(ReorgEvent.detected_at.desc())
            .limit(reorg_limit)
        ).scalars()
    )

    return StatusResponse(
        chain_id=chain_id,
        rpc_ok=head is not None,
        head=head,
        checkpoints=[CheckpointOut.model_validate(c) for c in cps],
        lag=lag,
        recent_reorgs=[ReorgOut.model_validate(r) for r in reorgs],
    )


@router.get("/blocks", response_model=BlocksPage)
def list_blocks(
    db: Annotated[Session, Depends(get_db)],
    chain_id: Annotated[int, Depends(default_chain_id)],
    from_block: int | None = Query(None, ge=0),
    to_block: int | None = Query(None, ge=0),
    page: Annotated[tuple[int, int], Depends(pagination)] = (100, 0),
) -> BlocksPage:
    """Bloques procesados en un rango, con paginación."""
    limit, offset = page

    filters = [Block.chain_id == chain_id]
    if from_block is not None:
        filters.append(Block.number >= from_block)
    if to_block is not None:
        filters.append(Block.number <= to_block)

    total = db.execute(
        select(func.count()).select_from(Block).where(*filters)
    ).scalar_one()

    items = list(
        db.execute(
            select(Block)
            .where(*filters)
            .order_by(Block.number.desc())
            .limit(limit)
            .offset(offset)
        ).scalars()
    )

    return BlocksPage(
        items=[BlockOut.model_validate(b) for b in items],
        limit=limit,
        offset=offset,
        total=int(total),
    )


@router.get("/raw-logs", response_model=RawLogsPage)
def list_raw_logs(
    db: Annotated[Session, Depends(get_db)],
    chain_id: Annotated[int, Depends(default_chain_id)],
    address: str | None = Query(None, description="Contrato (0x...)"),
    topic0: str | None = Query(None, description="topic0 del evento (0x...)"),
    from_block: int | None = Query(None, ge=0),
    to_block: int | None = Query(None, ge=0),
    page: Annotated[tuple[int, int], Depends(pagination)] = (100, 0),
) -> RawLogsPage:
    """Logs crudos en un rango, opcionalmente filtrados por address y topic0."""
    limit, offset = page

    filters = [RawLog.chain_id == chain_id]
    if address is not None:
        filters.append(func.lower(RawLog.address) == address.lower())
    if topic0 is not None:
        filters.append(func.lower(RawLog.topic0) == topic0.lower())
    if from_block is not None:
        filters.append(RawLog.block_number >= from_block)
    if to_block is not None:
        filters.append(RawLog.block_number <= to_block)

    total = db.execute(
        select(func.count()).select_from(RawLog).where(*filters)
    ).scalar_one()

    items = list(
        db.execute(
            select(RawLog)
            .where(*filters)
            .order_by(RawLog.block_number.desc(), RawLog.log_index.desc())
            .limit(limit)
            .offset(offset)
        ).scalars()
    )

    return RawLogsPage(
        items=[RawLogOut.model_validate(r) for r in items],
        limit=limit,
        offset=offset,
        total=int(total),
    )
