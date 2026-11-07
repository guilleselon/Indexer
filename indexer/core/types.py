"""Shared core types: DTOs that don't depend on anything internal."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from sqlalchemy.orm import Session


@dataclass(frozen=True)
class DecodedEvent:
    """An on-chain event, already decoded, ready for an adapter.

    Pure DTO: contains no business logic, knows no tables, depends on
    neither SQLAlchemy nor web3. Just data.
    """

    # On-chain identity
    chain_id: int
    block_number: int
    block_hash: str
    block_timestamp: datetime  # UTC
    tx_hash: str
    tx_index: int
    log_index: int
    contract_address: str  # checksummed

    # Event content
    event_name: str  # e.g. "OrderFulfilled"
    event_signature: str  # topic0, e.g. "0x9d9af8e3..."
    args: dict[str, Any]  # decoded args by name
    raw: dict[str, Any] = field(default_factory=dict)  # original log (audit)

    @property
    def dedup_key(self) -> tuple[int, int]:
        """Idempotency key: (block_number, log_index)."""
        return (self.block_number, self.log_index)


EventHandler = Callable[[DecodedEvent, Session], None]
