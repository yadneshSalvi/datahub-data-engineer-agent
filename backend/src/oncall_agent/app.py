"""FastAPI application exposing the on-call data engineer agent on port 8001."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from agents import set_tracing_disabled
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from oncall_agent.agent.context import DataHubFacade
from oncall_agent.agent.tools_mcp import build_mcp_manager
from oncall_agent.api.cache import AsyncTTLCache
from oncall_agent.api.compare import router as compare_router
from oncall_agent.api.demo import router as demo_router
from oncall_agent.api.demo_jobs import DemoJobRegistry
from oncall_agent.api.errors import install_error_handlers
from oncall_agent.api.health import router as health_router
from oncall_agent.api.lineage import router as lineage_router
from oncall_agent.api.metrics import router as metrics_router
from oncall_agent.api.postmortems import router as postmortems_router
from oncall_agent.api.registry import RunRegistry
from oncall_agent.api.runs import router as runs_router
from oncall_agent.api.signals import router as signals_router
from oncall_agent.config import Settings, get_settings
from oncall_agent.store import Store

log = logging.getLogger(__name__)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_BACKEND_ROOT = _REPOSITORY_ROOT / "backend"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Own SQLite, MCP, task registries, and cleanup in one Starlette lifespan task."""

    set_tracing_disabled(True)
    settings: Settings = app.state.settings_override or get_settings()
    app.state.settings = settings
    app.state.repository_root = _REPOSITORY_ROOT
    app.state.store = await Store.open(settings.db_path)
    app.state.dh = DataHubFacade()
    app.state.mcp = None
    manager = None
    if settings.mcp_enabled:
        try:
            manager = build_mcp_manager(settings)
            # Entry and exit deliberately stay in this async-generator task. Splitting them across
            # tasks breaks anyio cancel-scope ownership during shutdown.
            await manager.__aenter__()
            app.state.mcp = manager
            if not manager.active_servers:
                log.warning("MCP unavailable; native lineage fallback is active")
        except Exception as exc:
            manager = None
            log.warning("MCP unavailable; native lineage fallback is active error=%s", exc)
    app.state.runs = RunRegistry(app.state.store)
    app.state.demo_jobs = DemoJobRegistry(_BACKEND_ROOT)
    app.state.health_cache = AsyncTTLCache(10.0)
    app.state.signals_cache = AsyncTTLCache(5.0)
    app.state.lineage_cache = AsyncTTLCache(10.0)
    try:
        yield
    finally:
        await app.state.runs.close()
        await app.state.demo_jobs.close()
        if manager is not None:
            try:
                await manager.__aexit__(None, None, None)
            except Exception:
                log.exception("MCP shutdown failed")
        await app.state.store.close()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build an application, optionally with isolated settings for offline tests."""

    application = FastAPI(
        title="On-Call Data Engineer Agent",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.state.settings_override = settings
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3001", "http://127.0.0.1:3001"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_error_handlers(application)
    for router in (
        health_router,
        signals_router,
        runs_router,
        demo_router,
        lineage_router,
        postmortems_router,
        metrics_router,
        compare_router,
    ):
        application.include_router(router, prefix="/api")
    return application


app = create_app()

