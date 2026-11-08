"""Smoke test of imports. Usage: python check.py"""

from indexer.adapters.base import BaseAdapter  # noqa: F401
from indexer.adapters.echo.adapter import EchoAdapter  # noqa: F401
from indexer.adapters.registry import list_adapters
from indexer.api.app import create_app
from indexer.core.decoder import Decoder
from indexer.core.ingester import IngestStats  # noqa: F401
from indexer.core.reprocess import ReprocessStats  # noqa: F401
from indexer.core.types import DecodedEvent  # noqa: F401
from indexer.persistence.models import (  # noqa: F401
    Base, Block, Checkpoint, RawLog, ReorgEvent,
)

print("OK imports")

d = Decoder(event_abis=[], chain_id=1)
print(f"OK decoder: {d.chain_id} {len(d._topic_to_abi)} events registered")

tables = sorted(Base.metadata.tables.keys())
print(f"OK models: {len(tables)} tables -> {tables}")

print(f"OK adapters: {list_adapters()}")

app = create_app()
routes = sorted({r.path for r in app.routes if hasattr(r, "path")})
print(f"OK API: {len(routes)} routes -> {routes}")
