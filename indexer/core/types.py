"""Tipos compartidos del core: DTOs que no dependen de nada interno."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from sqlalchemy.orm import Session


@dataclass(frozen=True)
class DecodedEvent:
    """Un evento on-chain ya decodificado, listo para un adapter.

    Es un DTO puro: no contiene lógica de negocio, no conoce tablas,
    no depende de SQLAlchemy ni de web3. Solo datos.
    """

    # Identidad on-chain
    chain_id: int
    block_number: int
    block_hash: str
    block_timestamp: datetime  # UTC
    tx_hash: str
    tx_index: int
    log_index: int
    contract_address: str  # checksummed

    # Contenido del evento
    event_name: str  # p.ej. "OrderFulfilled"
    event_signature: str  # topic0, p.ej. "0x9d9af8e3..."
    args: dict[str, Any]  # argumentos decodificados por nombre
    raw: dict[str, Any] = field(default_factory=dict)  # log original (auditoría)

    @property
    def dedup_key(self) -> tuple[int, int]:
        """Clave de idempotencia: (block_number, log_index)."""
        return (self.block_number, self.log_index)


EventHandler = Callable[[DecodedEvent, Session], None]
