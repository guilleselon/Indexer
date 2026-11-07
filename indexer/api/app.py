"""FastAPI app factory. Mounts core, adapter and gas routers."""

from __future__ import annotations

import logging

from fastapi import APIRouter, FastAPI

from indexer.adapters.registry import get_adapter, list_adapters
from indexer.api.routers import core, health

logger = logging.getLogger(__name__)


def _collect_adapter_routes() -> APIRouter | None:
    """Ask every adapter to register its routes. If one fails, it doesn't block the rest."""
    router = APIRouter()
    for name in list_adapters():
        try:
            adapter = get_adapter(name)
        except Exception as exc:
            logger.warning("adapter %s could not be instantiated: %s", name, exc)
            continue
        try:
            adapter.register_routes(router)
        except Exception as exc:
            logger.warning("adapter %s failed registering routes: %s", name, exc)
    return router if router.routes else None


def create_app() -> FastAPI:
    """Factory: the `serve` command invokes it via uvicorn --factory."""
    from indexer.gas.collector import GasCollector
    from indexer.gas.routes import router as gas_router
    from indexer.gas.routes import set_store
    from indexer.gas.store import GasStore
    from indexer.core.rpc import RPCClient
    from indexer.config import get_settings

    app = FastAPI(
        title="Indexer API",
        version="0.1.0",
        description="Read API for the generic Web3 indexer.",
    )

    app.include_router(health.router)
    app.include_router(core.router)

    adapter_router = _collect_adapter_routes()
    if adapter_router is not None:
        app.include_router(adapter_router)

    # --- GAS (isolated) ---
    gas_store = GasStore(maxlen=2048)
    set_store(gas_store)
    app.include_router(gas_router)

    try:
        rpc = RPCClient(get_settings())
        collector = GasCollector(
            rpc, gas_store,
            poll_interval=12,
            confirmations=get_settings().confirmations,
        )
        collector.start()
        app.state.gas_collector = collector
        logger.info("gas: collector started in create_app")
    except Exception as exc:
        logger.warning("gas: collector could not start: %s", exc)
    # --- END GAS ---

    return app
