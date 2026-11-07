"""EchoAdapter: a permanent fixture that demonstrates the BaseAdapter contract.

Indexes USDC Transfer events on mainnet and logs them. It does not write
to the domain, so its rollback is a no-op. Used to verify the pipeline
end-to-end without Seaport's complexity, and it stays in the repo as the
reference adapter for isolating core bugs.

If the pipeline fails with Seaport but works with Echo, the bug is in the
Seaport adapter. If it fails with both, the bug is in the core.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from indexer.adapters.base import BaseAdapter
from indexer.core.types import DecodedEvent, EventHandler

logger = logging.getLogger(__name__)


USDC_ADDRESS = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"

TRANSFER_ABI: dict[str, Any] = {
    "anonymous": False,
    "inputs": [
        {"indexed": True, "name": "from", "type": "address"},
        {"indexed": True, "name": "to", "type": "address"},
        {"indexed": False, "name": "value", "type": "uint256"},
    ],
    "name": "Transfer",
    "type": "event",
}


def _handle_transfer(event: DecodedEvent, session: Session) -> None:
    args = event.args
    logger.info(
        "Transfer block=%s log=%s from=%s to=%s value=%s",
        event.block_number,
        event.log_index,
        args.get("from"),
        args.get("to"),
        args.get("value"),
    )


class EchoAdapter(BaseAdapter):
    name = "echo"
    chain_id = 1

    def contract_addresses(self) -> list[str]:
        return [USDC_ADDRESS]

    def event_abi(self) -> list[dict[str, Any]]:
        return [TRANSFER_ABI]

    def event_handlers(self) -> dict[str, EventHandler]:
        return {"Transfer": _handle_transfer}

    def rollback(self, from_block: int, to_block: int, session: Session) -> None:
        return None  # no domain writes, nothing to undo
