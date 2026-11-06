"""Modelos Pydantic de respuesta de la API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class BlockOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chain_id: int
    number: int
    hash: str
    parent_hash: str
    timestamp: datetime
    processed_at: datetime


class BlocksPage(BaseModel):
    items: list[BlockOut]
    limit: int
    offset: int
    total: int


class RawLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chain_id: int
    block_number: int
    block_hash: str
    log_index: int
    tx_hash: str
    tx_index: int
    address: str
    topic0: str | None
    topics: list[Any]
    data: str
    created_at: datetime


class RawLogsPage(BaseModel):
    items: list[RawLogOut]
    limit: int
    offset: int
    total: int


class CheckpointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chain_id: int
    adapter: str
    last_block: int
    last_block_hash: str | None
    updated_at: datetime


class ReorgOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chain_id: int
    adapter: str
    from_block: int
    to_block: int
    depth: int
    detected_at: datetime


class StatusResponse(BaseModel):
    chain_id: int
    rpc_ok: bool
    head: int | None
    checkpoints: list[CheckpointOut]
    lag: dict[str, int | None]
    recent_reorgs: list[ReorgOut]
