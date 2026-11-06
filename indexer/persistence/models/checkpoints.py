"""Progreso por adapter: último bloque procesado."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from indexer.persistence.models.base import Base, utcnow


class Checkpoint(Base):
    """Último bloque procesado por un adapter en una cadena.

    Un checkpoint por (chain_id, adapter): permite varios adapters
    independientes sobre la misma cadena.
    """

    __tablename__ = "checkpoints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chain_id: Mapped[int] = mapped_column(Integer, nullable=False)
    adapter: Mapped[str] = mapped_column(String(64), nullable=False)
    last_block: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    last_block_hash: Mapped[str | None] = mapped_column(String(66), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("chain_id", "adapter", name="uq_checkpoints_chain_adapter"),
    )
