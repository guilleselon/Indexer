"""Domain model for the Uniswap V3 adapter.

Each row is an individual swap. The unique constraint (chain_id,
block_number, log_index) guarantees schema-level idempotency and turns
the reorg rollback into a bounded DELETE.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from indexer.persistence.models.base import Base, utcnow


class UniswapV3Swap(Base):
    """A swap settled in a Uniswap V3 pool."""

    __tablename__ = "uniswap_v3_swaps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # On-chain identity (idempotency + rollback)
    chain_id: Mapped[int] = mapped_column(Integer, nullable=False)
    block_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    log_index: Mapped[int] = mapped_column(Integer, nullable=False)
    tx_hash: Mapped[str] = mapped_column(String(66), nullable=False)
    block_timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Pool and tokens
    pool_address: Mapped[str] = mapped_column(String(42), nullable=False)
    token0: Mapped[str] = mapped_column(String(42), nullable=False)
    token1: Mapped[str] = mapped_column(String(42), nullable=False)
    token0_decimals: Mapped[int] = mapped_column(Integer, nullable=False)
    token1_decimals: Mapped[int] = mapped_column(Integer, nullable=False)

    # From swap state (int256/uint256 as string for portability)
    amount0: Mapped[str] = mapped_column(String(78), nullable=False)
    amount1: Mapped[str] = mapped_column(String(78), nullable=False)
    sqrt_price_x96: Mapped[str] = mapped_column(String(78), nullable=False)
    liquidity: Mapped[str] = mapped_column(String(78), nullable=False)
    tick: Mapped[int] = mapped_column(Integer, nullable=False)

    # Derived (computed by the handler)
    price_token0_in_token1: Mapped[float] = mapped_column(Float, nullable=False)
    price_token1_in_token0: Mapped[float] = mapped_column(Float, nullable=False)

    # Participants
    sender: Mapped[str] = mapped_column(String(42), nullable=False)
    recipient: Mapped[str] = mapped_column(String(42), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "chain_id", "block_number", "log_index",
            name="uq_uniswap_v3_swaps_pos",
        ),
        Index("ix_uniswap_v3_swaps_pool_block", "pool_address", "block_number"),
        Index("ix_uniswap_v3_swaps_tokens", "token0", "token1"),
    )
