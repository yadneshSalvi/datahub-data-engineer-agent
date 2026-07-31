"""Offline contract tests for every explicit event DTO."""

from __future__ import annotations

import asyncio

import pytest

from oncall_agent.agent.context import EventEmitter
from oncall_agent.agent.events import (
    ActionEvent,
    AgentMessageEvent,
    BlastRadiusEvent,
    BlastRadiusTotals,
    CausalPathEvent,
    ErrorEvent,
    FindingEvent,
    MetricEvent,
    PhaseEvent,
    PostMortemEvent,
    PostMortemUrls,
    ReasoningEvent,
    RecallEvent,
    RecallTop,
    RunCompletedEvent,
    RunMetrics,
    RunStartedEvent,
    ToolCallEvent,
    ToolResultEvent,
    TriggerPayload,
    event_from_json,
)
from oncall_agent.agent.models import BlastRadiusItem, CausalNode


def _events():
    node = CausalNode(
        urn="urn:root",
        name="trips_raw",
        hops_from_symptom=3,
        verdict="root_cause",
        evidence=["31h stale"],
    )
    impact = BlastRadiusItem(
        urn="urn:impact",
        name="fct_trips",
        entity_type="DATASET",
        hops=2,
        usage_score=312,
        owners=["urn:li:corpuser:sam.patel"],
        severity="critical",
    )
    return [
        RunStartedEvent(
            trigger=TriggerPayload(
                dataset_urn="urn:symptom",
                name="agg_daily_rides",
                signal_kind="assertion",
                signal_detail="row count failed",
            ),
            model="gpt-5.6-sol",
        ),
        PhaseEvent(phase="recall", note="searching memory", phase_index=0),
        AgentMessageEvent(agent="On-Call Data Engineer", text="Starting", delta=False),
        ReasoningEvent(agent="On-Call Data Engineer", summary="Need upstream evidence"),
        ToolCallEvent(
            call_id="call-1",
            tool="recall_postmortems",
            origin="native",
            args={"dataset_urn": "urn:symptom"},
            agent="On-Call Data Engineer",
        ),
        ToolResultEvent(
            call_id="call-1",
            tool="recall_postmortems",
            ok=True,
            duration_ms=12,
            summary="found 0",
            payload={"found": 0},
        ),
        RecallEvent(
            found=1,
            top=RecallTop(
                incident_id="pm-1", root_cause_name="trips_raw", relevance=52, hops_away=3
            ),
            all=[],
        ),
        FindingEvent(
            urn="urn:root",
            name="trips_raw",
            check="freshness",
            verdict="broken",
            detail="31h stale",
        ),
        CausalPathEvent(nodes=[node]),
        BlastRadiusEvent(
            items=[impact], totals=BlastRadiusTotals(datasets=1, charts=0, dashboards=0, models=0)
        ),
        ActionEvent(action="tag", summary="tagged", urns=["urn:root"], detail="pickup_ts"),
        PostMortemEvent(
            postmortem_id="pm-1",
            title="Trips ingestion stalled",
            datahub_urls=PostMortemUrls(
                structured_property="http://datahub/dataset/root",
                document="http://datahub/document/pm-1",
                link="http://localhost:3001/memory/pm-1",
            ),
        ),
        MetricEvent(name="tool_calls", value=17),
        RunCompletedEvent(
            status="succeeded",
            summary="Done",
            metrics=RunMetrics(
                time_to_root_cause_s=2.4,
                tool_calls=17,
                hops_walked=3,
                recall_used=0,
            ),
            duration_s=4.0,
        ),
        ErrorEvent(message="quota exceeded", where="agent_run"),
    ]


@pytest.mark.parametrize("event", _events())
def test_every_event_round_trips_through_json(event) -> None:
    restored = event_from_json(event.model_dump_json())
    assert restored == event


@pytest.mark.asyncio
async def test_emitter_assigns_monotonic_sequence_numbers() -> None:
    queue: asyncio.Queue = asyncio.Queue()
    emitter = EventEmitter("run-test", queue)
    await asyncio.gather(
        emitter.emit(MetricEvent(name="a", value=1)),
        emitter.emit(MetricEvent(name="b", value=2)),
        emitter.emit(MetricEvent(name="c", value=3)),
    )
    assert [event.seq for event in emitter.events] == [1, 2, 3]
    assert {event.run_id for event in emitter.events} == {"run-test"}
    assert all(event.ts.endswith("Z") for event in emitter.events)
