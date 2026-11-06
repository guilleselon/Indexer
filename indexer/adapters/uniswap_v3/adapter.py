"""Adapter de Uniswap V3: cumple BaseAdapter para 3 pools de mainnet."""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete
from sqlalchemy.orm import Session

from indexer.adapters.base import BaseAdapter
from indexer.adapters.uniswap_v3.abi import SWAP_ABI
from indexer.adapters.uniswap_v3.handlers import POOLS, _validate_pools, handle_swap
from indexer.adapters.uniswap_v3.models import UniswapV3Swap
from indexer.core.types import EventHandler


class UniswapV3Adapter(BaseAdapter):
    name = "uniswap_v3"
    chain_id = 1
    default_start_block = None

    def __init__(self) -> None:
        _validate_pools()

    def contract_addresses(self) -> list[str]:
        return [meta["address"] for meta in POOLS.values()]

    def event_abi(self) -> list[dict[str, Any]]:
        return [SWAP_ABI]

    def event_handlers(self) -> dict[str, EventHandler]:
        return {"Swap": handle_swap}

    def rollback(self, from_block: int, to_block: int, session: Session) -> None:
        session.execute(
            delete(UniswapV3Swap).where(
                UniswapV3Swap.chain_id == self.chain_id,
                UniswapV3Swap.block_number >= from_block,
                UniswapV3Swap.block_number <= to_block,
            )
        )
        session.flush()

    def register_routes(self, router: Any) -> None:
        from indexer.adapters.uniswap_v3.routes import router as uniswap_router
        router.include_router(uniswap_router)
