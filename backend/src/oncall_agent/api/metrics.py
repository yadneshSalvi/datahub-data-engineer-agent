"""Aggregate incident-triage and memory-loop metrics."""

from __future__ import annotations

import statistics
from typing import Any

from fastapi import APIRouter, Request

from oncall_agent.api.models import MetricsResponse, TrendPoint

router = APIRouter(tags=["metrics"])


@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics(request: Request) -> MetricsResponse:
    """Aggregate completed runs into operational proof points and a chronological trend."""

    runs: list[dict[str, Any]] = await request.app.state.store.list_runs(limit=1000)
    completed = [run for run in runs if run["status"] != "running"]
    succeeded = [run for run in runs if run["status"] == "succeeded"]
    times = [
        float(run["time_to_root_cause_s"])
        for run in succeeded
        if run["time_to_root_cause_s"] is not None
    ]
    tool_calls = [int(run["tool_calls"]) for run in succeeded]
    protected = {
        str(item["urn"])
        for run in succeeded
        for item in run.get("blast_radius", [])
        if isinstance(item, dict) and item.get("urn")
    }
    trend = [
        TrendPoint(
            run_id=str(run["id"]),
            created_at=str(run["created_at"]),
            time_to_root_cause_s=run.get("time_to_root_cause_s"),
            tool_calls=int(run.get("tool_calls") or 0),
            recall_used=int(run.get("recall_used") or 0),
        )
        for run in reversed(completed[:50])
    ]
    return MetricsResponse(
        runs_total=len(runs),
        runs_succeeded=len(succeeded),
        avg_time_to_root_cause_s=round(statistics.fmean(times), 3) if times else None,
        median_tool_calls=float(statistics.median(tool_calls)) if tool_calls else None,
        recall_hit_rate=(
            round(sum(int(run.get("recall_used") or 0) for run in succeeded) / len(succeeded), 4)
            if succeeded
            else 0.0
        ),
        assets_protected=len(protected),
        incidents_filed=len({str(run["incident_urn"]) for run in runs if run.get("incident_urn")}),
        postmortems_written=await request.app.state.store.count_postmortems(),
        trend=trend,
    )
