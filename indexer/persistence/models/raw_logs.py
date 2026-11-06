"""Logs crudos tal como los devolvió el RPC. Fuente de verdad para re-decodificar."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column

from indexer.persistence.models.base import Base, utcnow

# JSONB en Postgres (indexable, eficiente); JSON genérico en SQLite.
JSONType = JSON().with_variant(JSONB, "postgresql")


class RawLog(Base):
    """Un log on-chain en su forma original.

    Clave de idempotencia: (chain_id, block_number, log_index).
    Reprocesar un bloque no duplica filas.
    """

    __tablename__ = "raw_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chain_id: Mapped[int] = mapped_column(Integer, nullable=False)
    block_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    block_hash: Mapped[str] = mapped_column(String(66), nullable=False)
    log_index: Mapped[int] = mapped_column(Integer, nullable=False)
    tx_hash: Mapped[str] = mapped_column(String(66), nullable=False)
    tx_index: Mapped[int] = mapped_column(Integer, nullable=False)
    address: Mapped[str] = mapped_column(String(42), nullable=False)
    topic0: Mapped[str | None] = mapped_column(String(66), nullable=True)
    topics: Mapped[list[Any]] = mapped_column(JSONType, nullable=False)
    data: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "chain_id", "block_number", "log_index", name="uq_raw_logs_position"
        ),
        Index("ix_raw_logs_address_block", "address", "block_number"),
        Index("ix_raw_logs_chain_block", "chain_id", "block_number"),
        Index("ix_raw_logs_topic0", "topic0"),
    )
