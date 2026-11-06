"""Registro de adapters disponibles. Punto único de descubrimiento.

Añadir un adapter nuevo = una línea en _ADAPTERS. Cero cambios en el core.
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
    cls = _ADAPTERS.get(name)
    if cls is None:
        raise KeyError(
            f"Adapter desconocido: {name}. Disponibles: {sorted(_ADAPTERS)}"
        )
    return cls()


def list_adapters() -> list[str]:
    return sorted(_ADAPTERS)
