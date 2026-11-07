"""Gas collector: background thread that polls eth_feeHistory.

Does not write to the DB. Does not use checkpoints. Does not touch the core.

- On startup (populate_initial): 1 eth_feeHistory(1024) call → 3.4h of history
- On each tick: 1 eth_feeHistory(delta) call → typically 1-2 blocks

On failure, it logs and moves on. Never crashes the API.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

from indexer.core.rpc import RPCClient
from indexer.gas.store import GasSnapshot, GasStore

logger = logging.getLogger(__name__)


class GasCollector:
    """Polls eth_feeHistory every N seconds and keeps the in-memory store fresh."""

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
        """Convert the eth_feeHistory response into snapshots."""
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
        """Fill the store with the last 1024 blocks in 1 call."""
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
                "gas: populate_initial ok, %s blocks added (head=%s)",
                added, head,
            )
            return added
        except Exception as exc:
            logger.warning("gas: populate_initial failed: %s", exc)
            return 0

    def _tick(self) -> None:
        """One iteration: request only the new blocks since the last one."""
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
            logger.debug("gas: tick ok, +%s blocks (head=%s)", added, head)

    def _loop(self) -> None:
        logger.info("gas: collector thread started (poll=%ss)", self._poll_interval)
        while not self._stop_event.is_set():
            try:
                self._tick()
            except Exception as exc:
                logger.warning("gas: tick failed: %s", exc)
            self._stop_event.wait(self._poll_interval)
        logger.info("gas: collector thread stopped")

    def start(self) -> None:
        """Start: initial populate (synchronous) + background thread."""
        if self._started:
            return
        self._started = True
        self.populate_initial()
        self._thread = threading.Thread(
            target=self._loop, name="gas-collector", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop signal. The thread exits in <= poll_interval seconds."""
        self._stop_event.set()
