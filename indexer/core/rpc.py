"""JSON-RPC client with retries, pagination and batching."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, TypeVar

from eth_utils import to_hex
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from web3 import Web3

from indexer.config import Settings
from indexer.core.errors import RPCError, RPCFatalError

logger = logging.getLogger(__name__)
T = TypeVar("T")

# Small batch to avoid saturating Infura free-tier rate limit.
DEFAULT_BATCH_SIZE = 10

_TRANSIENT_MARKERS = (
    "timeout", "timed out", "too many requests", "429",
    "502", "503", "504", "connection", "reset", "broken pipe",
    "temporarily", "try again", "unavailable",
    "limit exceeded", "rate limit", "exceeded", "quota",
)

def _is_transient(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(marker in msg for marker in _TRANSIENT_MARKERS)

def _post_json(url: str, payload: Any, timeout: float = 60.0) -> Any:
    """POST JSON to the RPC. Uses httpx if available, falls back to requests."""
    try:
        import httpx
        resp = httpx.post(url, json=payload, timeout=timeout)
    except ImportError:
        import requests
        resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json()

class RPCClient:
    """Minimalist JSON-RPC client with retries and batching."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._w3 = Web3(
            Web3.HTTPProvider(settings.rpc_url, request_kwargs={"timeout": 30})
        )
        self._verify_connection()

    def _verify_connection(self) -> None:
        try:
            connected = self._w3.is_connected()
        except Exception as exc:
            raise RPCFatalError(f"Error verifying RPC connection: {exc}") from exc

        if not connected:
            raise RPCFatalError(
                f"Cannot connect to RPC (chain_id={self._settings.chain_id})"
            )

        actual = self._w3.eth.chain_id
        if actual != self._settings.chain_id:
            raise RPCFatalError(
                f"chain_id mismatch: expected {self._settings.chain_id}, got {actual}"
            )

    @retry(
        retry=retry_if_exception_type(RPCError),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    def _call(self, operation: str, fn: Callable[[], T]) -> T:
        try:
            return fn()
        except Exception as exc:
            if _is_transient(exc):
                raise RPCError(f"{operation}: {exc}") from exc
            raise RPCFatalError(f"{operation}: {exc}") from exc

    @property
    def chain_id(self) -> int:
        return self._settings.chain_id

    def block_number(self) -> int:
        return self._call("block_number", lambda: self._w3.eth.block_number)

    def block(self, number: int) -> dict[str, Any]:
        """Block by number (single call)."""
        raw = self._call(
            f"get_block({number})",
            lambda: dict(self._w3.eth.get_block(number)),
        )
        if raw.get("hash") is not None:
            raw["hash"] = to_hex(raw["hash"])
        if raw.get("parentHash") is not None:
            raw["parentHash"] = to_hex(raw["parentHash"])
        return raw

    def block_timestamp(self, number: int) -> datetime:
        raw = self.block(number)["timestamp"]
        return datetime.fromtimestamp(int(raw), tz=timezone.utc)

    def has_code(self, address: str, block: int) -> bool:
        """Return True if the address has code at the given block (contract exists)."""
        try:
            code = self._call(
                f"get_code({address}, {block})",
                lambda: self._w3.eth.get_code(address, block_identifier=block)
            )
            return len(code) > 0
        except Exception:
            return False

    def fee_history(
        self,
        block_count: int,
        newest_block: int | str = "latest",
        reward_percentiles: list[float] | None = None,
    ) -> dict[str, Any]:
        """eth_feeHistory: returns base fees, gas ratios and rewards for N blocks in 1 call.

        block_count: max 1024 on most nodes.
        reward_percentiles: e.g. [10, 50, 90] for p10/p50/p90 priority fees.
        """
        if block_count <= 0:
            raise RPCFatalError(f"invalid block_count: {block_count}")
        if block_count > 1024:
            block_count = 1024

        percentiles = reward_percentiles or [10, 50, 90]

        def _fetch() -> dict[str, Any]:
            result = self._w3.eth.fee_history(
                block_count=block_count,
                newest_block=newest_block,
                reward_percentiles=percentiles,
            )
            return dict(result)

        return self._call(f"fee_history({block_count})", _fetch)

    def blocks_batch(
        self,
        numbers: list[int],
        chunk_size: int | None = None,
        inter_batch_sleep: float = 1.0,
    ) -> list[dict[str, Any]]:
        """Fetch multiple blocks via JSON-RPC batch. Sorted by number."""
        if not numbers:
            return []
        size = chunk_size or DEFAULT_BATCH_SIZE
        results: list[dict[str, Any]] = []
        for i in range(0, len(numbers), size):
            chunk = numbers[i:i + size]
            results.extend(self._blocks_batch_one(chunk))
            if i + size < len(numbers):
                time.sleep(inter_batch_sleep)
        results.sort(key=lambda b: b["number"])
        return results

    def _blocks_batch_one(
        self, numbers: list[int], max_attempts: int = 5
    ) -> list[dict[str, Any]]:
        """Fetch a batch with per-item retry on rate-limit (-32005)."""
        if not numbers:
            return []

        pending: set[int] = set(numbers)
        results: dict[int, dict[str, Any]] = {}

        for attempt in range(max_attempts):
            if not pending:
                break

            current = sorted(pending)
            payload = [
                {
                    "jsonrpc": "2.0",
                    "id": idx,
                    "method": "eth_getBlockByNumber",
                    "params": [hex(n), False],
                }
                for idx, n in enumerate(current)
            ]

            try:
                data = _post_json(self._settings.rpc_url, payload, timeout=60.0)
            except Exception as exc:
                if attempt < max_attempts - 1:
                    wait = min(2 ** attempt, 30)
                    logger.warning(
                        "batch HTTP error (%s), retry %s/%s in %ss",
                        exc, attempt + 1, max_attempts, wait,
                    )
                    time.sleep(wait)
                    continue
                raise

            if not isinstance(data, list):
                raise RuntimeError(f"Batch response is not a list: {type(data).__name__}")

            failed: list[int] = []

            for position, item in enumerate(data):
                if not isinstance(item, dict):
                    raise RuntimeError(f"Non-dict item at pos {position}: {item!r}")

                raw_id = item.get("id")
                if isinstance(raw_id, int):
                    idx = raw_id
                elif isinstance(raw_id, str) and raw_id.isdigit():
                    idx = int(raw_id)
                elif raw_id is None:
                    idx = position
                else:
                    raise RuntimeError(f"Invalid id at pos {position}: {raw_id!r}")

                if not (0 <= idx < len(current)):
                    raise RuntimeError(f"id out of range at pos {position}: {idx} (len={len(current)})")

                n = current[idx]

                if item.get("error") is not None:
                    code = item["error"].get("code")
                    if code == -32005:
                        failed.append(n)
                        continue
                    raise RuntimeError(f"RPC error block {n} (pos {position}): {item['error']}")

                raw = item.get("result")
                if raw is None:
                    failed.append(n)
                    continue

                results[n] = {
                    "number": int(raw["number"], 16),
                    "hash": raw["hash"],
                    "parentHash": raw["parentHash"],
                    "timestamp": int(raw["timestamp"], 16),
                }
                pending.discard(n)

            if not failed:
                continue

            if attempt == max_attempts - 1:
                raise RuntimeError(
                    f"persistent rate-limit after {max_attempts} attempts: "
                    f"{len(failed)} pending blocks (sample: {failed[:5]})"
                )

            wait = min(2 ** (attempt + 1), 30)
            logger.warning(
                "Infura rate-limit: %s/%s items failed, retry %s/%s in %ss",
                len(failed), len(current), attempt + 1, max_attempts, wait,
            )
            pending = set(failed)
            time.sleep(wait)

        if pending:
            raise RuntimeError(f"incomplete batch: {len(pending)} pending blocks")

        return [results[n] for n in numbers]

    def logs(
        self,
        from_block: int,
        to_block: int,
        addresses: list[str],
        topics: list[Any] | None = None,
    ) -> list[dict[str, Any]]:
        if not addresses:
            raise RPCFatalError("addresses cannot be empty in logs()")
        if from_block > to_block:
            return []

        filter_params: dict[str, Any] = {
            "fromBlock": from_block,
            "toBlock": to_block,
            "address": addresses,
        }
        if topics:
            filter_params["topics"] = topics

        def _fetch() -> list[dict[str, Any]]:
            return [dict(log) for log in self._w3.eth.get_logs(filter_params)]

        return self._call(f"get_logs({from_block}-{to_block})", _fetch)

    def logs_paginated(
        self,
        from_block: int,
        to_block: int,
        addresses: list[str],
        topics: list[Any] | None = None,
        chunk_size: int | None = None,
    ) -> Iterable[dict[str, Any]]:
        if from_block > to_block:
            return
        size = chunk_size or self._settings.max_block_range
        if size <= 0:
            raise RPCFatalError(f"invalid chunk_size: {size}")
        current = from_block
        while current <= to_block:
            end = min(current + size - 1, to_block)
            for log in self.logs(current, end, addresses, topics):
                yield log
            current = end + 1
