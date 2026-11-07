"""HTTP endpoints for the Uniswap V3 adapter.

Registered via UniswapV3Adapter.register_routes(). The core does not know
about them.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Integer, cast, func, select
from sqlalchemy.orm import Session

from indexer.adapters.uniswap_v3.handlers import POOLS
from indexer.adapters.uniswap_v3.models import UniswapV3Swap
from indexer.api.deps import get_db, pagination

router = APIRouter(prefix="/uniswap", tags=["uniswap"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_pool(pool_address: str) -> dict:
    for meta in POOLS.values():
        if meta["address"].lower() == pool_address.lower():
            return meta
    raise HTTPException(status_code=404, detail=f"pool not configured: {pool_address}")


def _window_to_cutoff(window: str) -> datetime:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    mapping = {
        "1h": timedelta(hours=1),
        "24h": timedelta(hours=24),
        "7d": timedelta(days=7),
        "30d": timedelta(days=30),
    }
    delta = mapping.get(window)
    if delta is None:
        raise HTTPException(
            status_code=400,
            detail=f"invalid window: {window!r}. Use 1h, 24h, 7d, 30d.",
        )
    return now - delta


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class SwapOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    block_number: int
    log_index: int
    tx_hash: str
    block_timestamp: datetime
    pool_address: str
    token0: str
    token1: str
    amount0: str
    amount1: str
    sqrt_price_x96: str
    liquidity: str
    tick: int
    price_token0_in_token1: float
    price_token1_in_token0: float
    sender: str
    recipient: str


class SwapsPage(BaseModel):
    items: list[SwapOut]
    limit: int
    offset: int
    total: int


class PoolInfo(BaseModel):
    address: str
    token0: str
    token1: str
    token0_decimals: int
    token1_decimals: int


class PoolStats(BaseModel):
    pool_address: str
    swaps: int
    first_block: int | None
    last_block: int | None
    avg_price_token0_in_token1: float | None
    avg_price_token1_in_token0: float | None


class VolumeResponse(BaseModel):
    pool_address: str
    window: str | None
    from_block: int | None
    to_block: int | None
    cutoff_timestamp: datetime | None
    swap_count: int
    volume_token0_raw: str
    volume_token1_raw: str
    volume_token0: float
    volume_token1: float


class PricePoint(BaseModel):
    period: str
    first_block: int
    last_block: int
    price_token0_in_token1: float
    price_token1_in_token0: float
    swap_count: int


class PriceHistoryPage(BaseModel):
    pool_address: str
    interval: str
    items: list[PricePoint]
    limit: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/pools", response_model=list[PoolInfo])
def list_pools() -> list[PoolInfo]:
    return [
        PoolInfo(
            address=meta["address"],
            token0=meta["token0"],
            token1=meta["token1"],
            token0_decimals=meta["dec0"],
            token1_decimals=meta["dec1"],
        )
        for meta in POOLS.values()
    ]


@router.get("/swaps", response_model=SwapsPage)
def list_swaps(
    db: Annotated[Session, Depends(get_db)],
    pool: str | None = Query(None, description="Pool address"),
    from_block: int | None = Query(None, ge=0),
    to_block: int | None = Query(None, ge=0),
    token0: str | None = Query(None),
    token1: str | None = Query(None),
    page: Annotated[tuple[int, int], Depends(pagination)] = (100, 0),
) -> SwapsPage:
    limit, offset = page

    filters = []
    if pool is not None:
        filters.append(func.lower(UniswapV3Swap.pool_address) == pool.lower())
    if from_block is not None:
        filters.append(UniswapV3Swap.block_number >= from_block)
    if to_block is not None:
        filters.append(UniswapV3Swap.block_number <= to_block)
    if token0 is not None:
        filters.append(func.lower(UniswapV3Swap.token0) == token0.lower())
    if token1 is not None:
        filters.append(func.lower(UniswapV3Swap.token1) == token1.lower())

    total = db.execute(
        select(func.count()).select_from(UniswapV3Swap).where(*filters)
    ).scalar_one()

    items = list(
        db.execute(
            select(UniswapV3Swap)
            .where(*filters)
            .order_by(
                UniswapV3Swap.block_number.desc(),
                UniswapV3Swap.log_index.desc(),
            )
            .limit(limit)
            .offset(offset)
        ).scalars()
    )

    return SwapsPage(
        items=[SwapOut.model_validate(s) for s in items],
        limit=limit,
        offset=offset,
        total=int(total),
    )


@router.get("/pools/{pool_address}/stats", response_model=PoolStats)
def pool_stats(
    pool_address: str,
    db: Annotated[Session, Depends(get_db)],
) -> PoolStats:
    _find_pool(pool_address)

    row = db.execute(
        select(
            func.count(UniswapV3Swap.id),
            func.min(UniswapV3Swap.block_number),
            func.max(UniswapV3Swap.block_number),
            func.avg(UniswapV3Swap.price_token0_in_token1),
            func.avg(UniswapV3Swap.price_token1_in_token0),
        ).where(func.lower(UniswapV3Swap.pool_address) == pool_address.lower())
    ).one()

    return PoolStats(
        pool_address=pool_address,
        swaps=int(row[0] or 0),
        first_block=int(row[1]) if row[1] is not None else None,
        last_block=int(row[2]) if row[2] is not None else None,
        avg_price_token0_in_token1=float(row[3]) if row[3] is not None else None,
        avg_price_token1_in_token0=float(row[4]) if row[4] is not None else None,
    )


@router.get("/pools/{pool_address}/volume", response_model=VolumeResponse)
def pool_volume(
    pool_address: str,
    db: Annotated[Session, Depends(get_db)],
    window: str | None = Query(
        None,
        description="Time window: 1h, 24h, 7d, 30d. Ignored if from_block/to_block are passed.",
    ),
    from_block: int | None = Query(None, ge=0),
    to_block: int | None = Query(None, ge=0),
) -> VolumeResponse:
    """Per-pool volume: sum of |amount0| and |amount1| over the range's swaps.

    amount0/amount1 are int256 stored as string (up to 78 chars).
    SQLite cannot sum them with CAST (overflows at 64 bits), so they are
    summed in Python. A 24h window is hundreds/thousands of rows:
    instantaneous.
    """
    pool_meta = _find_pool(pool_address)

    filters = [func.lower(UniswapV3Swap.pool_address) == pool_address.lower()]
    cutoff_ts: datetime | None = None

    if from_block is None and to_block is None and window is not None:
        cutoff_ts = _window_to_cutoff(window)
        filters.append(UniswapV3Swap.block_timestamp >= cutoff_ts)
    else:
        if from_block is not None:
            filters.append(UniswapV3Swap.block_number >= from_block)
        if to_block is not None:
            filters.append(UniswapV3Swap.block_number <= to_block)

    rows = db.execute(
        select(UniswapV3Swap.amount0, UniswapV3Swap.amount1).where(*filters)
    ).all()

    swap_count = len(rows)
    vol0_raw = sum(abs(int(r.amount0)) for r in rows)
    vol1_raw = sum(abs(int(r.amount1)) for r in rows)

    vol0_human = vol0_raw / (10 ** pool_meta["dec0"])
    vol1_human = vol1_raw / (10 ** pool_meta["dec1"])

    return VolumeResponse(
        pool_address=pool_meta["address"],
        window=window if (from_block is None and to_block is None) else None,
        from_block=from_block,
        to_block=to_block,
        cutoff_timestamp=cutoff_ts,
        swap_count=swap_count,
        volume_token0_raw=str(vol0_raw),
        volume_token1_raw=str(vol1_raw),
        volume_token0=vol0_human,
        volume_token1=vol1_human,
    )


@router.get("/pools/{pool_address}/price-history", response_model=PriceHistoryPage)
def pool_price_history(
    pool_address: str,
    db: Annotated[Session, Depends(get_db)],
    interval: Literal["block", "hour", "day"] = Query(
        "hour", description="Time grouping: block, hour, day"
    ),
    from_block: int | None = Query(None, ge=0),
    to_block: int | None = Query(None, ge=0),
    limit: int = Query(100, ge=1, le=1000),
) -> PriceHistoryPage:
    _find_pool(pool_address)

    filters = [func.lower(UniswapV3Swap.pool_address) == pool_address.lower()]
    if from_block is not None:
        filters.append(UniswapV3Swap.block_number >= from_block)
    if to_block is not None:
        filters.append(UniswapV3Swap.block_number <= to_block)

    if interval == "block":
        period_expr = cast(UniswapV3Swap.block_number, Integer)
    elif interval == "hour":
        period_expr = func.strftime("%Y-%m-%d %H:00:00", UniswapV3Swap.block_timestamp)
    else:
        period_expr = func.strftime("%Y-%m-%d", UniswapV3Swap.block_timestamp)

    stmt = (
        select(
            period_expr.label("period"),
            func.min(UniswapV3Swap.block_number).label("first_block"),
            func.max(UniswapV3Swap.block_number).label("last_block"),
            func.avg(UniswapV3Swap.price_token0_in_token1).label("avg_price_0_in_1"),
            func.avg(UniswapV3Swap.price_token1_in_token0).label("avg_price_1_in_0"),
            func.count(UniswapV3Swap.id).label("swap_count"),
        )
        .where(*filters)
        .group_by(period_expr)
        .order_by(period_expr.desc())
        .limit(limit)
    )

    rows = db.execute(stmt).all()

    items = [
        PricePoint(
            period=str(r.period),
            first_block=int(r.first_block),
            last_block=int(r.last_block),
            price_token0_in_token1=(
                float(r.avg_price_0_in_1) if r.avg_price_0_in_1 is not None else 0.0
            ),
            price_token1_in_token0=(
                float(r.avg_price_1_in_0) if r.avg_price_1_in_0 is not None else 0.0
            ),
            swap_count=int(r.swap_count),
        )
        for r in rows
    ]

    return PriceHistoryPage(
        pool_address=pool_address,
        interval=interval,
        items=items,
        limit=limit,
    )
