"""Demo seeding, scenario control, state, and subprocess progress SSE."""

from __future__ import annotations

import asyncio
import json
import sys
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Request, status
from fastapi.responses import StreamingResponse

from oncall_agent.api.errors import ApiError
from oncall_agent.api.models import (
    DemoBreakRequest,
    DemoJobAccepted,
    DemoJobEvent,
    DemoResetRequest,
    DemoSeedRequest,
    DemoState,
    ErrorResponse,
)

router = APIRouter(tags=["demo"])

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}
_ERROR_RESPONSES = {
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}
_CENSUS_QUERY = """
query demoState($input: SearchAcrossEntitiesInput!) {
  searchAcrossEntities(input: $input) { total }
}
"""


def _job_frame(event: DemoJobEvent) -> str:
    return f"event: {event.kind}\ndata: {event.model_dump_json()}\nid: {event.seq}\n\n"


def _clear_api_caches(request: Request) -> None:
    request.app.state.health_cache.clear()
    request.app.state.signals_cache.clear()
    request.app.state.lineage_cache.clear()


def _receipt(repository_root: Path) -> tuple[str | None, str | None]:
    directory = repository_root / "data" / "scenarios"
    if not directory.exists():
        return None, None
    receipts = sorted(directory.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not receipts:
        return None, None
    try:
        body = json.loads(receipts[0].read_text(encoding="utf-8"))
        scenario = str(body.get("scenario")) if body.get("scenario") else None
        armed_ms = body.get("armed_at_ms")
        armed_at = (
            datetime.fromtimestamp(float(armed_ms) / 1000, tz=UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
            if armed_ms is not None
            else None
        )
        return scenario, armed_at
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None, None


async def _entity_count(gms_url: str) -> int:
    search_input: dict[str, Any] = {
        "types": ["DATASET", "CHART", "DASHBOARD", "MLMODEL"],
        "query": "oncall_demo",
        "start": 0,
        "count": 0,
    }
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.post(
                f"{gms_url.rstrip('/')}/api/graphql",
                json={"query": _CENSUS_QUERY, "variables": {"input": search_input}},
            )
        response.raise_for_status()
        body = response.json()
        return int((((body.get("data") or {}).get("searchAcrossEntities") or {}).get("total")) or 0)
    except Exception:
        return 0


@router.post(
    "/demo/seed",
    response_model=DemoJobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def seed_demo(body: DemoSeedRequest, request: Request) -> DemoJobAccepted:
    """Start the idempotent seeder and its full verification pass."""

    command = [sys.executable, "-m", "demo.seed", "--verify"]
    if body.wipe:
        command.append("--wipe")
    _clear_api_caches(request)
    return DemoJobAccepted(job_id=request.app.state.demo_jobs.start(command))


@router.post(
    "/demo/break",
    response_model=DemoJobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    responses=_ERROR_RESPONSES,
)
async def break_demo(body: DemoBreakRequest, request: Request) -> DemoJobAccepted:
    """Start scenario arming, including its up-to-120-second index convergence poll."""

    if body.scenario == "recall_hit" and await request.app.state.store.count_postmortems() == 0:
        raise ApiError(
            409,
            "recall_requires_memory",
            "The recall_hit scenario requires an existing post-mortem",
            "Arm stale_upstream and complete its triage first so the agent has memory to recall",
        )
    command = [sys.executable, "-m", "demo.break", "--scenario", body.scenario]
    _clear_api_caches(request)
    return DemoJobAccepted(job_id=request.app.state.demo_jobs.start(command))


@router.post(
    "/demo/reset",
    response_model=DemoJobAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    responses=_ERROR_RESPONSES,
)
async def reset_demo(body: DemoResetRequest, request: Request) -> DemoJobAccepted:
    """Heal the demo, optionally preserve memory, or purge only deterministic demo entities."""

    if body.keep_memory and body.purge:
        raise ApiError(
            422,
            "incompatible_reset_options",
            "keep_memory and purge cannot both be true",
            "Choose a healing reset with memory preservation or a complete namespace purge",
        )
    option = "--purge" if body.purge else "--keep-memory" if body.keep_memory else "--all"
    command = [sys.executable, "-m", "demo.reset", option]
    _clear_api_caches(request)
    return DemoJobAccepted(job_id=request.app.state.demo_jobs.start(command))


async def _job_stream(
    request: Request,
    job_id: str,
    queue: asyncio.Queue[DemoJobEvent | None],
) -> AsyncIterator[str]:
    next_ping = time.monotonic() + 15.0
    try:
        while True:
            if await request.is_disconnected():
                return
            timeout = max(0.05, min(1.0, next_ping - time.monotonic()))
            try:
                event = await asyncio.wait_for(queue.get(), timeout=timeout)
            except TimeoutError:
                if time.monotonic() >= next_ping:
                    yield ": ping\n\n"
                    next_ping = time.monotonic() + 15.0
                continue
            if event is None:
                return
            yield _job_frame(event)
    finally:
        request.app.state.demo_jobs.unsubscribe(job_id, queue)


@router.get("/demo/jobs/{job_id}/stream", responses=_ERROR_RESPONSES)
async def stream_demo_job(job_id: str, request: Request) -> StreamingResponse:
    """Replay and tail machine-readable ``STEP n/total`` subprocess progress."""

    queue = request.app.state.demo_jobs.subscribe(job_id)
    if queue is None:
        raise ApiError(404, "demo_job_not_found", f"Demo job {job_id} does not exist")
    return StreamingResponse(
        _job_stream(request, job_id, queue),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.get("/demo/state", response_model=DemoState)
async def get_demo_state(request: Request) -> DemoState:
    """Return current seed count, armed receipt, and observed health state."""

    settings = request.app.state.settings
    entity_count = await _entity_count(settings.datahub_gms_url)
    scenario, armed_at = _receipt(request.app.state.repository_root)
    healthy = False
    if entity_count:
        try:
            signals = await asyncio.to_thread(request.app.state.dh.get_health_signals)
            healthy = not signals
        except Exception:
            healthy = False
    return DemoState(
        seeded=entity_count > 0,
        entity_count=entity_count,
        armed_scenario=scenario,
        armed_at=armed_at,
        healthy=healthy,
    )

