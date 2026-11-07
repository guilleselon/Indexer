"""Registry of available adapters. Single discovery point.

Adding a new adapter = one line in _ADAPTERS. Zero changes in the core.
"""

from __future__ import annotations

from indexer.adapters.base import BaseAdapter
from indexer.adapters.echo.adapter import EchoAdapter
from indexer.adapters.uniswap_v3.adapter import UniswapV3Adapter

_ADAPTERS: dict[str, type[BaseAdapter]] = {
    EchoAdapter.name: EchoAdapter,
    UniswapV3Adapter.name: UniswapV3Adapter,
}


def get_adapter(name: str) -> BaseAdapter:
    """Return the adapter registered under `name`."""
    cls = _ADAPTERS.get(name)
    if cls is None:
        raise KeyError(
            f"Unknown adapter: {name}. Available: {sorted(_ADAPTERS)}"
        )
    return cls()


def list_adapters() -> list[str]:
    """Return the sorted list of registered adapter names."""
    return sorted(_ADAPTERS)
