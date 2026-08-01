"""Run lifecycle, permanent replay, and gap-free SSE streaming endpoints."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Header, Query, Request, status
from fastapi.responses import StreamingResponse

from oncall_agent.agent.events import Event
from oncall_agent.agent.models import TriggerSpec
from oncall_agent.agent.runner import Deps
from oncall_agent.api.errors import ApiError
from oncall_agent.api.models import (
    CancelRunResponse,
    ErrorResponse,
    RunAccepted,
    RunCreateRequest,
    RunRecord,
)
from oncall_agent.datahub.urns import is_our_dataset_urn, short_display_name

router = APIRouter(tags=["runs"])

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}
_ERROR_RESPONSES = {
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
}


def _scenario_name(repository_root: Path) -> str | None:
    directory = repository_root / "data" / "scenarios"
    if not directory.exists():
        return None
    receipts = sorted(directory.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not receipts:
        return None
    try:
        return str(json.loads(receipts[0].read_text(encoding="utf-8")).get("scenario"))
    except (OSError, json.JSONDecodeError):
        return None


def _frame(event: Event) -> str:
    return f"event: {event.kind}\ndata: {event.model_dump_json()}\nid: {event.seq}\n\n"


async def _event_stream(
    request: Request,
    run_id: str,
    queue: asyncio.Queue[Event | None] | None,
    stored: list[Event],
    high_water_mark: int,
    last_event_id: int,
) -> AsyncIterator[str]:
    """Replay a storage snapshot, then tail a pre-subscribed queue without gaps or duplicates."""

    emitted = last_event_id
    terminal_seen = False
    try:
        for event in stored:
            if await request.is_disconnected():
                return
            if last_event_id < event.seq <= high_water_mark and event.seq > emitted:
                yield _frame(event)
                emitted = event.seq
                terminal_seen = terminal_seen or event.kind == "run_completed"
        if queue is None:
            return

        next_ping = time.monotonic() + 15.0
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
            if event.seq <= high_water_mark or event.seq <= emitted:
                continue
            if terminal_seen:
                continue
            yield _frame(event)
            emitted = event.seq
            terminal_seen = event.kind == "run_completed"
    finally:
        if queue is not None:
            await request.app.state.runs.unsubscribe(run_id, queue)


@router.post(
    "/runs",
    response_model=RunAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    responses=_ERROR_RESPONSES,
)
async def create_run(body: RunCreateRequest, request: Request) -> RunAccepted:
    """Start triage in an owned background task without waiting for an SSE subscriber."""

    if not is_our_dataset_urn(body.dataset_urn):
        raise ApiError(
            422,
            "dataset_outside_namespace",
            "Runs may only target datasets in the configured oncall namespace",
            "Choose a dataset whose platform is oncall and name starts with oncall_demo.",
        )
    try:
        exists = await asyncio.to_thread(request.app.state.dh.dataset_exists, body.dataset_urn)
    except Exception as exc:
        raise ApiError(
            503,
            "dataset_existence_unverified",
            f"DataHub could not verify the target dataset: {body.dataset_urn}",
            "Retry when the index-independent aspect API is available; no run was started.",
        ) from exc
    if not exists:
        raise ApiError(
            404,
            "dataset_not_found",
            f"The target dataset does not exist: {body.dataset_urn}",
            "Choose an existing oncall dataset; no run was started and no metadata was written.",
        )
    trigger = TriggerSpec(
        dataset_urn=body.dataset_urn,
        name=short_display_name(body.dataset_urn),
        signal_kind=body.signal_kind,
        signal_detail=body.signal_detail or f"Manual {body.signal_kind} triage requested over HTTP",
        assertion_urn=body.assertion_urn,
    )
    deps = Deps(
        store=request.app.state.store,
        dh=request.app.state.dh,
        mcp_manager=request.app.state.mcp,
        settings=request.app.state.settings,
        scenario=_scenario_name(request.app.state.repository_root),
    )
    try:
        run_id = await request.app.state.runs.start(trigger, deps)
    except Exception as exc:
        raise ApiError(
            500,
            "run_start_failed",
            f"The triage task could not start: {exc}",
            "Inspect backend logs; no SSE connection is required to start a run",
        ) from exc
    return RunAccepted(run_id=run_id)


@router.get("/runs", response_model=list[RunRecord])
async def list_runs(
    request: Request,
    limit: int = Query(default=50, ge=1, le=500),
) -> list[RunRecord]:
    """List newest runs first with expanded metrics and JSON accumulators."""

    rows = await request.app.state.store.list_runs(limit=limit)
    return [RunRecord.model_validate(row) for row in rows]


@router.get("/runs/{run_id}", response_model=RunRecord, responses=_ERROR_RESPONSES)
async def get_run(run_id: str, request: Request) -> RunRecord:
    """Return a permanently replayable run's full stored record."""

    row = await request.app.state.store.get_run(run_id)
    if row is None:
        raise ApiError(404, "run_not_found", f"Run {run_id} does not exist")
    return RunRecord.model_validate(row)


@router.get("/runs/{run_id}/events", response_model=list[Event], responses=_ERROR_RESPONSES)
async def get_run_events(run_id: str, request: Request) -> list[Event]:
    """Return the validated event DTO list for non-SSE replay and reconciliation."""

    if await request.app.state.store.get_run(run_id) is None:
        raise ApiError(404, "run_not_found", f"Run {run_id} does not exist")
    return await request.app.state.store.get_events(run_id)


@router.get("/runs/{run_id}/stream", responses=_ERROR_RESPONSES)
async def stream_run(
    run_id: str,
    request: Request,
    last_event_id: Annotated[int | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    """Replay persisted events, tail a live run, and close after its terminal event."""

    if await request.app.state.store.get_run(run_id) is None:
        raise ApiError(404, "run_not_found", f"Run {run_id} does not exist")

    # The subscription MUST precede the event snapshot. An event appended during the read is then
    # either present in the snapshot, present in the live queue, or both (where seq dedupe removes
    # it).
    queue = await request.app.state.runs.subscribe(run_id)
    stored = await request.app.state.store.get_events(run_id)
    high_water_mark = max((event.seq for event in stored), default=0)
    after = max(0, last_event_id or 0)
    return StreamingResponse(
        _event_stream(request, run_id, queue, stored, high_water_mark, after),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.post(
    "/runs/{run_id}/cancel",
    response_model=CancelRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses=_ERROR_RESPONSES,
)
async def cancel_run(run_id: str, request: Request) -> CancelRunResponse:
    """Cancel an active registry-owned task and allow the runner to persist its final state."""

    row = await request.app.state.store.get_run(run_id)
    if row is None:
        raise ApiError(404, "run_not_found", f"Run {run_id} does not exist")
    if not await request.app.state.runs.cancel(run_id):
        raise ApiError(
            409,
            "run_not_active",
            f"Run {run_id} is no longer active",
            f"Its persisted status is {row['status']}",
        )
    return CancelRunResponse(run_id=run_id, status="cancelling")
