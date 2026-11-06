"""Decoder: convierte logs crudos en DecodedEvent usando una lista de ABIs.

No toca red ni DB: recibe ABIs + logs y devuelve DTOs. Testeable en aislamiento.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from eth_utils import event_abi_to_log_topic, to_hex
from web3 import Web3
from web3._utils.events import get_event_data

from indexer.core.errors import DecodingError
from indexer.core.types import DecodedEvent


def _hex(value: Any) -> str:
    """Normaliza HexBytes / bytes / str a '0x...' en minúsculas."""
    if isinstance(value, (bytes, bytearray)):
        return "0x" + bytes(value).hex()
    if isinstance(value, str):
        return value.lower() if value.startswith("0x") else "0x" + value
    return to_hex(value)


class Decoder:
    """Decodifica logs on-chain usando una lista de ABIs de eventos.

    No conoce Seaport ni Uniswap: solo recibe ABIs + logs.
    """

    def __init__(self, event_abis: list[dict[str, Any]], chain_id: int) -> None:
        self.chain_id = chain_id
        self._w3 = Web3()  # sin provider: el decoder no hace red
        self._topic_to_abi: dict[str, dict[str, Any]] = {}
        for abi in event_abis:
            topic = _hex(event_abi_to_log_topic(abi))
            if topic in self._topic_to_abi:
                raise DecodingError(f"ABI duplicada para topic {topic}")
            self._topic_to_abi[topic] = abi

    def decode(
        self,
        log: dict[str, Any],
        block_timestamp: datetime | None = None,
    ) -> DecodedEvent:
        """Decodifica un único log. Lanza DecodingError si no se puede."""
        topics = log.get("topics") or []
        if not topics:
            raise DecodingError("Log sin topics")

        topic0 = _hex(topics[0])
        event_abi = self._topic_to_abi.get(topic0)
        if event_abi is None:
            raise DecodingError(f"Topic desconocido: {topic0}")

        try:
            decoded = get_event_data(self._w3.codec, event_abi, log)
        except Exception as exc:
            raise DecodingError(
                f"Fallo decodificando {event_abi.get('name', '?')}: {exc}"
            ) from exc

        ts = block_timestamp or datetime.now(timezone.utc)

        return DecodedEvent(
            chain_id=self.chain_id,
            block_number=int(log["blockNumber"]),
            block_hash=_hex(log["blockHash"]),
            block_timestamp=ts,
            tx_hash=_hex(log["transactionHash"]),
            tx_index=int(log["transactionIndex"]),
            log_index=int(log["logIndex"]),
            contract_address=decoded["address"],
            event_name=decoded["event"],
            event_signature=topic0,
            args=dict(decoded["args"]),
            raw={
                "topics": [_hex(t) for t in topics],
                "data": _hex(log["data"]),
            },
        )
