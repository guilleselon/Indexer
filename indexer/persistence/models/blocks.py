"""Bloques procesados: base para reorgs y contexto temporal."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from indexer.persistence.models.base import Base, utcnow


class Block(Base):
    """Un bloque canónico procesado por el indexador."""

    __tablename__ = "blocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chain_id: Mapped[int] = mapped_column(Integer, nullable=False)
    number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    hash: Mapped[str] = mapped_column(String(66), nullable=False)
    parent_hash: Mapped[str] = mapped_column(String(66), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("chain_id", "number", name="uq_blocks_chain_number"),
        Index("ix_blocks_chain_number", "chain_id", "number"),
    )
