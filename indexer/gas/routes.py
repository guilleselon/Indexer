"""Endpoints de gas. Leen del store en memoria y (opcionalmente) del precio de Uniswap.

Cero APIs externas. El precio de ETH se obtiene del propio indexador:
- Si hay swaps de USDC/WETH en `uniswap_v3_swaps`, se usa el último precio.
- Si no, el campo `cost_usd` es None.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from indexer.gas.store import GasStore
from indexer.persistence.db import session_scope

# ⚠️ CORRECCIÓN: el modelo vive en el adapter, no en persistence
from indexer.adapters.uniswap_v3.models import UniswapV3Swap

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/gas", tags=["gas"])

_store: GasStore | None = None

GAS_ESTIMATES = {
    "transfer_erc20": 51_000,
    "approve": 46_000,
    "swap_v3": 180_000,
    "add_liquidity_v3": 250_000,
}


def set_store(store: GasStore) -> None:
    global _store
    _store = store


def _get_store() -> GasStore:
    if _store is None:
        raise HTTPException(status_code=503, detail="gas collector no inicializado")
    return _store


def _get_eth_price_from_uniswap() -> float | None:
    """Precio de 1 WETH en USDC desde el último swap de Uniswap V3. None si no hay."""
    try:
        with session_scope() as session:
            row = session.execute(
                select(UniswapV3Swap.price_token1_in_token0)
                .where(
                    UniswapV3Swap.token1 == "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
                    UniswapV3Swap.token0 == "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                )
                .order_by(UniswapV3Swap.block_number.desc())
                .limit(1)
            ).first()
            if row is None:
                return None
            return float(row[0])
    except Exception as exc:
        logger.debug("gas: no se pudo leer precio de Uniswap: %s", exc)
        return None


@router.get("/current")
def gas_current() -> dict:
    """Snapshot enriquecido: gas actual + costo estimado por operación."""
    store = _get_store()
    snap = store.current()
    if snap is None:
        return {"status": "warming_up", "message": "collector aún no tiene datos"}

    eth_price_usd = _get_eth_price_from_uniswap()

    ratio = snap.gas_used_ratio
    next_base_wei = int(snap.base_fee_wei * (1 + (ratio - 0.5) / 8))
    next_base_gwei = next_base_wei / 1e9
    trend = "up" if next_base_wei > snap.base_fee_wei else "down"

    if ratio >= 0.9:
        congestion = "high"
    elif ratio >= 0.7:
        congestion = "medium"
    else:
        congestion = "low"

    total_fee_wei_per_gas = snap.base_fee_wei + snap.priority_fee_p50_wei
    costs = {}
    for op, gas_units in GAS_ESTIMATES.items():
        cost_wei = total_fee_wei_per_gas * gas_units
        cost_eth = cost_wei / 1e18
        cost_usd = cost_eth * eth_price_usd if eth_price_usd else None
        costs[op] = {
            "gas_units": gas_units,
            "cost_eth": round(cost_eth, 8),
            "cost_usd": round(cost_usd, 4) if cost_usd is not None else None,
        }

    return {
        "block_number": snap.block_number,
        "timestamp": snap.timestamp.isoformat(),
        "eth_price_usd": round(eth_price_usd, 2) if eth_price_usd else None,
        "gas_prices": {
            "slow": {
                "base_gwei": round(snap.base_fee_gwei, 3),
                "tip_gwei": round(snap.priority_fee_p10_wei / 1e9, 3),
                "total_gwei": round((snap.base_fee_wei + snap.priority_fee_p10_wei) / 1e9, 3),
                "estimated_confirmation": "~2 min",
            },
            "standard": {
                "base_gwei": round(snap.base_fee_gwei, 3),
                "tip_gwei": round(snap.priority_fee_p50_wei / 1e9, 3),
                "total_gwei": round(snap.total_fee_p50_gwei, 3),
                "estimated_confirmation": "~30s",
            },
            "fast": {
                "base_gwei": round(snap.base_fee_gwei, 3),
                "tip_gwei": round(snap.priority_fee_p90_wei / 1e9, 3),
                "total_gwei": round((snap.base_fee_wei + snap.priority_fee_p90_wei) / 1e9, 3),
                "estimated_confirmation": "~12s",
            },
        },
        "network": {
            "gas_used_ratio": round(ratio, 4),
            "congestion": congestion,
            "next_block_base_gwei": round(next_base_gwei, 3),
            "trend": trend,
        },
        "costs": costs,
    }


@router.get("/history")
def gas_history(
    blocks: Annotated[int, Query(ge=1, le=2048)] = 1800,
) -> dict:
    store = _get_store()
    items = store.history(blocks)
    if not items:
        return {"status": "warming_up", "items": [], "count": 0}
    return {
        "count": len(items),
        "from_block": items[0].block_number,
        "to_block": items[-1].block_number,
        "items": [
            {
                "block_number": s.block_number,
                "base_fee_gwei": round(s.base_fee_gwei, 3),
                "gas_used_ratio": round(s.gas_used_ratio, 4),
                "priority_fee_p50_gwei": round(s.priority_fee_p50_wei / 1e9, 3),
            }
            for s in items
        ],
    }


@router.get("/status")
def gas_status() -> dict:
    store = _get_store()
    return {
        "size": store.size(),
        "last_block": store.last_block(),
        "has_data": store.current() is not None,
    }
