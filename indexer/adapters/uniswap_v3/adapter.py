"""Uniswap V3 adapter: BaseAdapter implementation for 3 mainnet pools."""

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
        """Addresses of the pools in POOLS."""
        return [meta["address"] for meta in POOLS.values()]

    def event_abi(self) -> list[dict[str, Any]]:
        """Swap event ABI."""
        return [SWAP_ABI]

    def event_handlers(self) -> dict[str, EventHandler]:
        """Swap event handler."""
        return {"Swap": handle_swap}

    def rollback(self, from_block: int, to_block: int, session: Session) -> None:
        """Delete UniswapV3Swap rows in [from_block, to_block].

        session.flush() forces the pending DELETE to be issued.
        """
        session.execute(
            delete(UniswapV3Swap).where(
                UniswapV3Swap.chain_id == self.chain_id,
                UniswapV3Swap.block_number >= from_block,
                UniswapV3Swap.block_number <= to_block,
            )
        )
        session.flush()

    def register_routes(self, router: Any) -> None:
        """Register the Uniswap V3 routes on the given router."""
        from indexer.adapters.uniswap_v3.routes import router as uniswap_router
        router.include_router(uniswap_router)
