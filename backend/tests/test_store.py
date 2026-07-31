"""Offline SQLite lifecycle, replay, and memory-counter tests."""

from __future__ import annotations

import pytest

from oncall_agent.agent.events import MetricEvent
from oncall_agent.agent.models import PostMortem, TriageReport, TriggerSpec
from oncall_agent.store import Store


def _trigger() -> TriggerSpec:
    return TriggerSpec(
        dataset_urn="urn:li:dataset:(urn:li:dataPlatform:oncall,oncall_demo.marts.agg_daily_rides,PROD)",
        name="agg_daily_rides",
        signal_kind="assertion",
        signal_detail="row count failed",
    )


def _postmortem() -> PostMortem:
    return PostMortem(
        incident_id="run-store",
        title="Trips ingestion stalled",
        symptom="daily rides row count collapsed",
        symptom_urn=_trigger().dataset_urn,
        root_cause_urn="urn:li:dataset:(urn:li:dataPlatform:oncall,oncall_demo.raw.trips_raw,PROD)",
        root_cause_name="trips_raw",
        root_cause_summary="Raw trips feed is stale",
        causal_path=[],
        evidence=["26h stale against 6h SLA"],
        blast_radius=[],
        recommended_action="Restart trips ingestion and backfill",
        prevention="Add a 6h freshness monitor on trips_raw",
        recalled_incident_ids=[],
        confidence="high",
    )


@pytest.mark.asyncio
async def test_store_lifecycle_replay_and_reuse(tmp_path) -> None:
    store = await Store.open(tmp_path / "oncall.db")
    try:
        await store.create_run("run-store", _trigger(), scenario="stale_upstream")
        second = MetricEvent(
            seq=2,
            run_id="run-store",
            ts="2026-08-01T00:00:02.000Z",
            name="tool_calls",
            value=9,
        )
        first = MetricEvent(
            seq=1,
            run_id="run-store",
            ts="2026-08-01T00:00:01.000Z",
            name="hops_walked",
            value=3,
        )
        await store.append_events([second, first])
        await store.save_postmortem(
            run_id="run-store",
            postmortem=_postmortem(),
            markdown="# Post-mortem",
            document_urn="urn:li:document:oncall-postmortem-run-store",
            datahub_links=["http://localhost:9002/document/test"],
        )
        await store.increment_reused_count(["run-store", "run-store"])
        await store.finish_run(
            TriageReport(
                run_id="run-store",
                status="succeeded",
                summary="Root cause confirmed",
                root_cause_urn=_postmortem().root_cause_urn,
                root_cause_name="trips_raw",
                incident_urn="urn:li:incident:test",
                postmortem_id="run-store",
                causal_path=[],
                blast_radius=[],
                actions=[],
                findings=[],
                tool_calls=9,
                hops_walked=3,
                recall_used=False,
                recalled_ids=[],
                time_to_root_cause_s=2.5,
                duration_s=5.0,
                error=None,
            )
        )

        replay = await store.get_events("run-store")
        assert [event.seq for event in replay] == [1, 2]
        run = await store.get_run("run-store")
        assert run is not None and run["status"] == "succeeded"
        memory = await store.get_postmortem("run-store")
        assert memory is not None and memory["reused_count"] == 1
    finally:
        await store.close()
