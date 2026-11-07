"""Ethereum address utilities."""

from __future__ import annotations

from web3 import Web3


def checksum(addr: str) -> str:
    """Return the address in checksum form. Raises ValueError if invalid."""
    return Web3.to_checksum_address(addr)


def is_valid(addr: str) -> bool:
    """True if the address is valid (20-byte hex). Does not require checksum."""
    return Web3.is_address(addr)
