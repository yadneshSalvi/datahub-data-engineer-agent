"""Health and non-secret environment endpoints.

Run this application with one uvicorn worker. The process owns a single WAL-mode SQLite connection
and in-memory live-run registry, so ``--workers 1`` is part of the runtime contract.
"""

from __future__ import annotations

import asyncio
from importlib.metadata import PackageNotFoundError, version
from typing import Any

import httpx
from fastapi import APIRouter, Request

from oncall_agent.agent.tools_mcp import MCP_TOOL_NAMES
from oncall_agent.api.models import (
    ConfigResponse,
    DatabaseHealth,
    DataHubHealth,
    HealthResponse,
    MCPHealth,
    OpenAIHealth,
)

router = APIRouter(tags=["health"])

_CENSUS_QUERY = """
query census($input: SearchAcrossEntitiesInput!) {
  searchAcrossEntities(input: $input) { total }
}
"""


def _version() -> str:
    try:
        return version("oncall-agent")
    except PackageNotFoundError:
        return "0.1.0"


async def _probe_datahub(gms_url: str, name_prefix: str) -> DataHubHealth:
    """Probe config and namespace census within a strict sub-two-second budget."""

    base = gms_url.rstrip("/")
    timeout = httpx.Timeout(1.8)
    census_input: dict[str, Any] = {
        "types": ["DATASET", "CHART", "DASHBOARD", "MLMODEL"],
        "query": name_prefix.rstrip("."),
        "start": 0,
        "count": 0,
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            config_call = client.get(f"{base}/config")
            census_call = client.post(
                f"{base}/api/graphql",
                json={"query": _CENSUS_QUERY, "variables": {"input": census_input}},
            )
            async with asyncio.timeout(1.9):
                config_result, census_result = await asyncio.gather(
                    config_call,
                    census_call,
                    return_exceptions=True,
                )
        if isinstance(config_result, BaseException):
            raise config_result
        config_result.raise_for_status()
        config = config_result.json()
        server_version = (
            ((config.get("versions") or {}).get("acryldata/datahub") or {}).get("version")
        )
        seeded_entities = 0
        if not isinstance(census_result, BaseException):
            census_result.raise_for_status()
            census_body = census_result.json()
            seeded_entities = int(
                (((census_body.get("data") or {}).get("searchAcrossEntities") or {}).get("total"))
                or 0
            )
        return DataHubHealth(
            status="up",
            gms_url=gms_url,
            server_version=server_version,
            seeded_entities=seeded_entities,
        )
    except Exception:
        return DataHubHealth(status="down", gms_url=gms_url)


@router.get("/health", response_model=HealthResponse)
async def get_health(request: Request) -> HealthResponse:
    """Return cached backend dependency status without blocking on a failed GMS."""

    settings = request.app.state.settings

    async def load_datahub() -> DataHubHealth:
        return await _probe_datahub(settings.datahub_gms_url, settings.name_prefix)

    datahub = await request.app.state.health_cache.get("datahub", load_datahub)
    run_count = await request.app.state.store.count_runs()
    manager = request.app.state.mcp
    connected = bool(manager is not None and manager.active_servers)
    return HealthResponse(
        ok=datahub.status == "up",
        version=_version(),
        datahub=datahub,
        mcp=MCPHealth(
            status="connected" if connected else "unavailable",
            tools=list(MCP_TOOL_NAMES) if connected else [],
        ),
        openai=OpenAIHealth(configured=bool(settings.openai_api_key)),
        db=DatabaseHealth(path=str(request.app.state.store.path), runs=run_count),
    )


@router.get("/config", response_model=ConfigResponse)
async def get_config(request: Request) -> ConfigResponse:
    """Return the non-secret configuration required by the web UI."""

    settings = request.app.state.settings
    return ConfigResponse(
        datahub_ui_url=settings.datahub_ui_url,
        platform=settings.platform,
        scenarios=["stale_upstream", "recall_hit", "schema_drift"],
        agent_model=settings.agent_model,
    )
