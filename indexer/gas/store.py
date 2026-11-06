"""Store en memoria para snapshots de gas.

Thread-safe: el collector escribe desde un thread en background,
los endpoints de FastAPI leen desde los hilos del event loop.

Cero DB. Cero disco. Solo RAM (~160KB para 2048 snapshots).
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class GasSnapshot:
    """Un bloque con sus métricas de gas."""

    block_number: int
    timestamp: datetime
    base_fee_wei: int
    gas_used_ratio: float
    priority_fee_p10_wei: int
    priority_fee_p50_wei: int
    priority_fee_p90_wei: int

    @property
    def base_fee_gwei(self) -> float:
        return self.base_fee_wei / 1e9

    @property
    def priority_fee_p50_gwei(self) -> float:
        return self.priority_fee_p50_wei / 1e9

    @property
    def total_fee_p50_gwei(self) -> float:
        """Gas total que pagaría una tx con prioridad media."""
        return (self.base_fee_wei + self.priority_fee_p50_wei) / 1e9


class GasStore:
    """Cache circular de los últimos N snapshots. Sin persistencia, sin locks de DB."""

    def __init__(self, maxlen: int = 2048) -> None:
        # 2048 bloques ≈ 6.8h a 12s/bloque. Suficiente para gráficos de 6h.
        self._deque: deque[GasSnapshot] = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._last_block: int = 0

    def append_many(self, snapshots: list[GasSnapshot]) -> int:
        """Añade snapshots (ignora duplicados y desordenados). Devuelve cuántos nuevos."""
        if not snapshots:
            return 0
        with self._lock:
            added = 0
            for snap in sorted(snapshots, key=lambda s: s.block_number):
                if snap.block_number > self._last_block:
                    self._deque.append(snap)
                    self._last_block = snap.block_number
                    added += 1
            return added

    def last_block(self) -> int:
        with self._lock:
            return self._last_block

    def current(self) -> GasSnapshot | None:
        with self._lock:
            return self._deque[-1] if self._deque else None

    def history(self, blocks: int = 1800) -> list[GasSnapshot]:
        """Últimos N snapshots en orden ascendente."""
        with self._lock:
            items = list(self._deque)
        return items[-blocks:] if blocks > 0 else items

    def size(self) -> int:
        with self._lock:
            return len(self._deque)
