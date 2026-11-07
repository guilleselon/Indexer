"""Uniswap V3 adapter handlers: transform Swap events into rows."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from indexer.adapters.uniswap_v3.models import UniswapV3Swap
from indexer.core.types import DecodedEvent
from indexer.utils.addresses import checksum, is_valid

logger = logging.getLogger(__name__)


POOLS: dict[str, dict[str, Any]] = {
    "0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640": {
        "address": "0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640",
        "token0": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        "token1": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        "dec0": 6,
        "dec1": 18,
    },
    "0xcbcdf9626bc03e24f779434178a73a0b4bad62ed": {
        "address": "0xCBCdF9626bC03E24f779434178A73a0B4bad62eD",
        "token0": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",
        "token1": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        "dec0": 8,
        "dec1": 18,
    },
    "0x3416cf6c708da44db2624d63ea0aaef7113527c6": {
        "address": "0x3416cF6C708Da44DB2624D63ea0AAef7113527C6",
        "token0": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        "token1": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
        "dec0": 6,
        "dec1": 6,
    },
}


def _validate_pools() -> None:
    """Validate that every address in POOLS is checksummed and valid.

    Fails fast if someone typos POOLS. Called from
    UniswapV3Adapter.__init__, not at module level.
    """
    for key, meta in POOLS.items():
        for field in ("address", "token0", "token1"):
            value = meta[field]
            if not is_valid(value):
                raise ValueError(
                    f"POOLS[{key}].{field} is not a valid address: {value!r}"
                )
            if checksum(value) != value:
                raise ValueError(
                    f"POOLS[{key}].{field} is not in checksum form: {value!r}. "
                    f"Should be {checksum(value)!r}"
                )


def compute_prices(
    sqrt_price_x96: int, dec0: int, dec1: int
) -> tuple[float, float]:
    """Convert sqrtPriceX96 to human-readable prices (token0 in token1, token1 in token0)."""
    if sqrt_price_x96 <= 0:
        return (0.0, 0.0)
    price_raw = (sqrt_price_x96 / (2**96)) ** 2
    price_0_in_1 = price_raw * (10 ** (dec0 - dec1))
    if price_0_in_1 <= 0:
        return (0.0, 0.0)
    return (price_0_in_1, 1.0 / price_0_in_1)


def handle_swap(event: DecodedEvent, session: Session) -> None:
    """Persist a Uniswap V3 swap. Idempotent."""
    pool_key = event.contract_address.lower()
    pool_meta = POOLS.get(pool_key)
    if pool_meta is None:
        logger.warning(
            "swap on unconfigured pool: %s (block=%s log=%s)",
            event.contract_address, event.block_number, event.log_index,
        )
        return

    exists = session.execute(
        select(UniswapV3Swap.id).where(
            UniswapV3Swap.chain_id == event.chain_id,
            UniswapV3Swap.block_number == event.block_number,
            UniswapV3Swap.log_index == event.log_index,
        )
    ).scalar_one_or_none()
    if exists is not None:
        return

    args = event.args
    try:
        amount0 = int(args["amount0"])
        amount1 = int(args["amount1"])
        sqrt_price = int(args["sqrtPriceX96"])
        liquidity = int(args["liquidity"])
        tick = int(args["tick"])
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning(
            "malformed swap at %s:%s - %s",
            event.block_number, event.log_index, exc,
        )
        return

    price_0_in_1, price_1_in_0 = compute_prices(
        sqrt_price, pool_meta["dec0"], pool_meta["dec1"]
    )

    swap = UniswapV3Swap(
        chain_id=event.chain_id,
        block_number=event.block_number,
        log_index=event.log_index,
        tx_hash=event.tx_hash,
        block_timestamp=event.block_timestamp,
        pool_address=pool_meta["address"],
        token0=pool_meta["token0"],
        token1=pool_meta["token1"],
        token0_decimals=pool_meta["dec0"],
        token1_decimals=pool_meta["dec1"],
        amount0=str(amount0),
        amount1=str(amount1),
        sqrt_price_x96=str(sqrt_price),
        liquidity=str(liquidity),
        tick=tick,
        price_token0_in_token1=price_0_in_1,
        price_token1_in_token0=price_1_in_0,
        sender=str(args.get("sender", "")),
        recipient=str(args.get("recipient", "")),
    )
    session.add(swap)
    session.flush()
