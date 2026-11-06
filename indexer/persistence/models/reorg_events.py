"""Auditoría de reorgs detectados."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from indexer.persistence.models.base import Base, utcnow


class ReorgEvent(Base):
    """Registro de una reorganización de cadena detectada.

    No se usa para lógica: es auditoría. Permite demostrar que manejaste
    reorgs y con qué profundidad.
    """

    __tablename__ = "reorg_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chain_id: Mapped[int] = mapped_column(Integer, nullable=False)
    adapter: Mapped[str] = mapped_column(String(64), nullable=False)
    from_block: Mapped[int] = mapped_column(BigInteger, nullable=False)
    to_block: Mapped[int] = mapped_column(BigInteger, nullable=False)
    old_hash: Mapped[str | None] = mapped_column(String(66), nullable=True)
    new_hash: Mapped[str | None] = mapped_column(String(66), nullable=True)
    depth: Mapped[int] = mapped_column(Integer, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
