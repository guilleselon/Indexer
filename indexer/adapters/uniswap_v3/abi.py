"""ABI del evento Swap de Uniswap V3.

Firma:
    event Swap(
        address indexed sender,
        address indexed recipient,
        int256 amount0,
        int256 amount1,
        uint160 sqrtPriceX96,
        uint128 liquidity,
        int24 tick
    )

Idéntica en todos los pools de Uniswap V3 (las fees son un parámetro del
constructor del pool, no del evento), así que un solo ABI sirve para los
2-3 pools del adapter.
"""

from __future__ import annotations

from typing import Any


SWAP_ABI: dict[str, Any] = {
    "anonymous": False,
    "inputs": [
        {"indexed": True, "name": "sender", "type": "address"},
        {"indexed": True, "name": "recipient", "type": "address"},
        {"indexed": False, "name": "amount0", "type": "int256"},
        {"indexed": False, "name": "amount1", "type": "int256"},
        {"indexed": False, "name": "sqrtPriceX96", "type": "uint160"},
        {"indexed": False, "name": "liquidity", "type": "uint128"},
        {"indexed": False, "name": "tick", "type": "int24"},
    ],
    "name": "Swap",
    "type": "event",
}
