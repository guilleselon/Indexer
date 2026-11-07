"""Base contract for niche adapters.

The core depends ONLY on this file and on `indexer.core.types`/`errors`.
Adapters (seaport, uniswap_v3, ...) implement `BaseAdapter`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from sqlalchemy.orm import Session

from indexer.core.types import DecodedEvent, EventHandler


class BaseAdapter(ABC):
    """Contract every niche (Seaport, Uniswap V3, ...) must fulfill."""

    #: Unique adapter identifier. Must match `--adapter` on the CLI.
    name: str

    #: chain_id this adapter operates on.
    chain_id: int

    #: Default starting block. None = uses Settings.start_block.
    default_start_block: int | None = None

    # ------------------------------------------------------------------
    # 1. What to listen for
    # ------------------------------------------------------------------

    @abstractmethod
    def contract_addresses(self) -> list[str]:
        """Addresses (checksummed) whose logs this adapter cares about."""
        ...

    @abstractmethod
    def event_abi(self) -> list[dict[str, Any]]:
        """ABI fragments for the events the decoder must know about."""
        ...

    # ------------------------------------------------------------------
    # 2. What to do with each event
    # ------------------------------------------------------------------

    @abstractmethod
    def event_handlers(self) -> dict[str, EventHandler]:
        """Maps `event_name` -> handler."""
        ...

    # ------------------------------------------------------------------
    # 3. How to undo (reorgs)
    # ------------------------------------------------------------------

    @abstractmethod
    def rollback(self, from_block: int, to_block: int, session: Session) -> None:
        """Undo the adapter's effects over [from_block, to_block]."""
        ...

    # ------------------------------------------------------------------
    # 4. Optional API
    # ------------------------------------------------------------------

    def register_routes(self, router: Any) -> None:
        """Register adapter-specific HTTP endpoints. Does nothing by default."""
        return None
