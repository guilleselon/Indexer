"""Utilidades de direcciones Ethereum."""

from __future__ import annotations

from web3 import Web3


def checksum(addr: str) -> str:
    """Devuelve la dirección en checksum form. Lanza ValueError si es inválida."""
    return Web3.to_checksum_address(addr)


def is_valid(addr: str) -> bool:
    """True si la dirección es válida (hex 20 bytes). No exige checksum."""
    return Web3.is_address(addr)
