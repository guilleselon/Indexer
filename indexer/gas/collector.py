"""Collector de gas: background thread que sondea eth_feeHistory.

No escribe en la DB. No usa checkpoints. No toca el core.

- Al arrancar (populate_initial): 1 llamada a eth_feeHistory(1024) → 3.4h de historial
- En cada tick: 1 llamada a eth_feeHistory(delta) → típicamente 1-2 bloques

Si falla, loguea y sigue. Nunca tumba la API.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

from indexer.core.rpc import RPCClient
from indexer.gas.store import GasSnapshot, GasStore

logger = logging.getLogger(__name__)


class GasCollector:
    """Sondea eth_feeHistory cada N segundos y mantiene el store en memoria."""

    def __init__(
        self,
        rpc: RPCClient,
        store: GasStore,
        poll_interval: int = 12,
        confirmations: int = 2,
    ) -> None:
        self._rpc = rpc
        self._store = store
        self._poll_interval = poll_interval
        self._confirmations = confirmations
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._started = False

    def _parse_fee_history(self, history: dict, newest_block: int) -> list[GasSnapshot]:
        """Convierte la respuesta de eth_feeHistory a snapshots."""
        base_fees = history.get("baseFeePerGas", [])
        ratios = history.get("gasUsedRatio", [])
        rewards = history.get("reward", [])
        oldest_block = history.get("oldestBlock", 0)

        if not base_fees or not ratios:
            return []

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        snapshots: list[GasSnapshot] = []

        for i, ratio in enumerate(ratios):
            block_num = int(oldest_block) + i
            if block_num > newest_block:
                break

            reward = rewards[i] if i < len(rewards) else [0, 0, 0]
            p10 = int(reward[0]) if len(reward) > 0 else 0
            p50 = int(reward[1]) if len(reward) > 1 else 0
            p90 = int(reward[2]) if len(reward) > 2 else 0

            snapshots.append(GasSnapshot(
                block_number=block_num,
                timestamp=now,
                base_fee_wei=int(base_fees[i]),
                gas_used_ratio=float(ratio),
                priority_fee_p10_wei=p10,
                priority_fee_p50_wei=p50,
                priority_fee_p90_wei=p90,
            ))

        return snapshots

    def populate_initial(self) -> int:
        """Rellena el store con los últimos 1024 bloques en 1 llamada."""
        try:
            head = self._rpc.block_number() - self._confirmations
            history = self._rpc.fee_history(
                block_count=1024,
                newest_block=head,
                reward_percentiles=[10, 50, 90],
            )
            snapshots = self._parse_fee_history(history, head)
            added = self._store.append_many(snapshots)
            logger.info(
                "gas: populate_initial ok, %s bloques añadidos (head=%s)",
                added, head,
            )
            return added
        except Exception as exc:
            logger.warning("gas: populate_initial falló: %s", exc)
            return 0

    def _tick(self) -> None:
        """Una iteración: pide solo los bloques nuevos desde el último."""
        head = self._rpc.block_number() - self._confirmations
        last = self._store.last_block()

        if head <= last:
            return

        count = min(head - last, 1024)
        history = self._rpc.fee_history(
            block_count=count,
            newest_block=head,
            reward_percentiles=[10, 50, 90],
        )
        snapshots = self._parse_fee_history(history, head)
        added = self._store.append_many(snapshots)
        if added > 0:
            logger.debug("gas: tick ok, +%s bloques (head=%s)", added, head)

    def _loop(self) -> None:
        logger.info("gas: collector thread iniciado (poll=%ss)", self._poll_interval)
        while not self._stop_event.is_set():
            try:
                self._tick()
            except Exception as exc:
                logger.warning("gas: tick falló: %s", exc)
            self._stop_event.wait(self._poll_interval)
        logger.info("gas: collector thread detenido")

    def start(self) -> None:
        """Arranca: populate inicial (síncrono) + thread en background."""
        if self._started:
            return
        self._started = True
        self.populate_initial()
        self._thread = threading.Thread(
            target=self._loop, name="gas-collector", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """Señal de parada. El thread termina en <= poll_interval segundos."""
        self._stop_event.set()
