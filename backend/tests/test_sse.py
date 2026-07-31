"""Gap-free SSE replay, live tail, resume, and disconnect-lifetime tests."""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator

import httpx
import pytest

from oncall_agent.agent.events import MetricEvent, RunCompletedEvent, RunMetrics
from oncall_agent.agent.models import TriggerSpec
from oncall_agent.app import create_app
from oncall_agent.config import Settings


def _trigger() -> TriggerSpec:
    return TriggerSpec(
        dataset_urn=(
            "urn:li:dataset:(urn:li:dataPlatform:oncall,"
            "oncall_demo.marts.agg_daily_rides,PROD)"
        ),
        name="agg_daily_rides",
        signal_kind="assertion",
        signal_detail="fixture",
    )


def _metric(run_id: str, seq: int) -> MetricEvent:
    return MetricEvent(
        seq=seq,
        run_id=run_id,
        ts=f"2026-08-01T00:00:0{seq}.000Z",
        name="fixture",
        value=seq,
    )


def _completed(run_id: str, seq: int) -> RunCompletedEvent:
    return RunCompletedEvent(
        seq=seq,
        run_id=run_id,
        ts=f"2026-08-01T00:00:0{seq}.000Z",
        status="succeeded",
        summary="complete",
        metrics=RunMetrics(
            time_to_root_cause_s=1.0,
            tool_calls=2,
            hops_walked=1,
            recall_used=0,
        ),
        duration_s=2.0,
    )


def _ids(body: str) -> list[int]:
    return [int(value) for value in re.findall(r"^id: (\d+)$", body, flags=re.MULTILINE)]


@pytest.mark.asyncio
async def test_replay_then_tail_is_gap_free_and_completed_run_replays(tmp_path) -> None:
    settings = Settings(
        db_path=str(tmp_path / "sse.db"),
        mcp_enabled=False,
        openai_api_key=None,
        _env_file=None,
    )
    app = create_app(settings)
    run_id = "run-sse"
    release_tail = asyncio.Event()

    async def source() -> AsyncIterator[MetricEvent | RunCompletedEvent]:
        yield _metric(run_id, 1)
        await release_tail.wait()
        yield _metric(run_id, 2)
        yield _metric(run_id, 3)
        yield _completed(run_id, 4)

    async with app.router.lifespan_context(app):
        await app.state.store.create_run(run_id, _trigger())
        assert await app.state.runs.start_source(source) == run_id
        while len(await app.state.store.get_events(run_id)) < 1:
            await asyncio.sleep(0)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            live_request = asyncio.create_task(client.get(f"/api/runs/{run_id}/stream"))
            await asyncio.sleep(0.02)
            release_tail.set()
            live = await live_request
            assert live.status_code == 200
            assert live.headers["content-type"].startswith("text/event-stream")
            assert live.headers["cache-control"] == "no-cache"
            assert live.headers["x-accel-buffering"] == "no"
            assert _ids(live.text) == [1, 2, 3, 4]

            replay = await client.get(f"/api/runs/{run_id}/stream")
            assert _ids(replay.text) == [1, 2, 3, 4]

            resumed = await client.get(
                f"/api/runs/{run_id}/stream",
                headers={"Last-Event-ID": "2"},
            )
            assert _ids(resumed.text) == [3, 4]


@pytest.mark.asyncio
async def test_disconnected_stream_does_not_cancel_run(tmp_path) -> None:
    settings = Settings(
        db_path=str(tmp_path / "disconnect.db"),
        mcp_enabled=False,
        openai_api_key=None,
        _env_file=None,
    )
    app = create_app(settings)
    run_id = "run-disconnect"
    release_tail = asyncio.Event()

    async def source() -> AsyncIterator[MetricEvent | RunCompletedEvent]:
        yield _metric(run_id, 1)
        await release_tail.wait()
        yield _metric(run_id, 2)
        yield _completed(run_id, 3)

    async with app.router.lifespan_context(app):
        await app.state.store.create_run(run_id, _trigger())
        await app.state.runs.start_source(source)
        while len(await app.state.store.get_events(run_id)) < 1:
            await asyncio.sleep(0)
        queue = await app.state.runs.subscribe(run_id)
        assert queue is not None
        await app.state.runs.unsubscribe(run_id, queue)
        release_tail.set()
        for _ in range(100):
            events = await app.state.store.get_events(run_id)
            if events and events[-1].kind == "run_completed":
                break
            await asyncio.sleep(0.01)
        assert [event.seq for event in events] == [1, 2, 3]
        assert events[-1].kind == "run_completed"


@pytest.mark.asyncio
async def test_app_starts_without_openai_key_and_run_fails_as_events(tmp_path) -> None:
    settings = Settings(
        db_path=str(tmp_path / "no-key.db"),
        mcp_enabled=False,
        openai_api_key=None,
        _env_file=None,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app), httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/runs",
            json={
                "dataset_urn": _trigger().dataset_urn,
                "signal_kind": "assertion",
            },
        )
        assert response.status_code == 202
        run_id = response.json()["run_id"]
        stream = await client.get(f"/api/runs/{run_id}/stream")
        assert [
            line.removeprefix("event: ")
            for line in stream.text.splitlines()
            if line.startswith("event: ")
        ] == ["run_started", "error", "metric", "metric", "run_completed"]
        detail = await client.get(f"/api/runs/{run_id}")
        assert detail.json()["status"] == "failed"
        assert "OPENAI_API_KEY" in detail.json()["error"]
