"""Contrato base de los adapters de nicho.

El core depende SOLO de este archivo y de `indexer.core.types`/`errors`.
Los adapters (seaport, uniswap_v3, ...) implementan `BaseAdapter`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from sqlalchemy.orm import Session

from indexer.core.types import DecodedEvent, EventHandler


class BaseAdapter(ABC):
    """Contrato que todo nicho (Seaport, Uniswap V3, ...) debe cumplir."""

    #: Identificador único del adapter. Debe coincidir con `--adapter` en CLI.
    name: str

    #: chain_id en el que opera este adapter.
    chain_id: int

    #: Bloque de arranque por defecto. None = usa START_BLOCK del .env.
    default_start_block: int | None = None

    # ------------------------------------------------------------------
    # 1. Qué escuchar
    # ------------------------------------------------------------------

    @abstractmethod
    def contract_addresses(self) -> list[str]:
        """Direcciones (checksummed) cuyos logs le interesan a este adapter."""
        ...

    @abstractmethod
    def event_abi(self) -> list[dict[str, Any]]:
        """Fragmentos de ABI de los eventos que el decoder debe conocer."""
        ...

    # ------------------------------------------------------------------
    # 2. Qué hacer con cada evento
    # ------------------------------------------------------------------

    @abstractmethod
    def event_handlers(self) -> dict[str, EventHandler]:
        """Mapea `event_name` -> handler."""
        ...

    # ------------------------------------------------------------------
    # 3. Cómo deshacer (reorgs)
    # ------------------------------------------------------------------

    @abstractmethod
    def rollback(self, from_block: int, to_block: int, session: Session) -> None:
        """Deshacer los efectos del adapter en [from_block, to_block]."""
        ...

    # ------------------------------------------------------------------
    # 4. API opcional
    # ------------------------------------------------------------------

    def register_routes(self, router: Any) -> None:
        """Registra endpoints HTTP propios del adapter. Por defecto, nada."""
        return None
