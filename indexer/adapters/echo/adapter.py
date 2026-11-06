"""EchoAdapter: fixture permanente que demuestra el contrato BaseAdapter.

Indexa los eventos Transfer de USDC en mainnet y los loguea. No escribe
dominio, así que su rollback es no-op. Sirve para verificar el pipeline
end-to-end sin la complejidad de Seaport, y se queda en el repo como
adapter de referencia para aislar bugs del core.

Si el pipeline falla con Seaport pero funciona con Echo, el bug está en
el adapter de Seaport. Si falla con ambos, el bug está en el core.
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
        return None  # sin dominio, nada que deshacer
