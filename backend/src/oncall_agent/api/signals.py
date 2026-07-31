"""Cached DataHub health-to-alert-inbox mapping."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Any

from fastapi import APIRouter, Query, Request

from demo.catalog import CHARTS, DASHBOARDS, DATASETS, LINEAGE, chart_urn, dashboard_urn
from oncall_agent.agent.events import utc_now_iso
from oncall_agent.api.models import Owner, Signal, SignalsResponse
from oncall_agent.datahub.urns import entity_type_from_urn

log = logging.getLogger(__name__)

router = APIRouter(tags=["signals"])


def _downstream_map() -> dict[str, set[str]]:
    by_key = {dataset.key: dataset.urn for dataset in DATASETS}
    result: dict[str, set[str]] = {}
    for edge in LINEAGE:
        result.setdefault(by_key[edge.upstream], set()).add(by_key[edge.downstream])
    for name, _display, input_key, _weekly_views in CHARTS:
        result.setdefault(by_key[input_key], set()).add(chart_urn(name))
    for name, _display, chart_names, *_ in DASHBOARDS:
        for chart_name in chart_names:
            result.setdefault(chart_urn(chart_name), set()).add(dashboard_urn(name))
    return result


_DOWNSTREAM = _downstream_map()


def _severity(dataset_urn: str) -> str:
    seen: set[str] = set()
    pending = list(_DOWNSTREAM.get(dataset_urn, set()))
    while pending:
        urn = pending.pop()
        if urn in seen:
            continue
        seen.add(urn)
        pending.extend(_DOWNSTREAM.get(urn, set()))
    if any(entity_type_from_urn(urn) == "DASHBOARD" for urn in seen):
        return "critical"
    return "high" if seen else "medium"


def _signal_id(dataset_urn: str, kind: str) -> str:
    digest = hashlib.sha1(f"{dataset_urn}{kind}".encode(), usedforsecurity=False).hexdigest()
    return f"sig-{digest}"


def _assertion_detail(record: dict[str, Any]) -> str:
    messages = [
        str(item.get("message"))
        for item in record.get("health") or []
        if item.get("type") == "ASSERTIONS"
        and item.get("status") == "FAIL"
        and item.get("message")
    ]
    return " · ".join(messages) or "One or more assertions are failing"


async def _enrich_record(request: Request, record: dict[str, Any]) -> list[Signal]:
    facade = request.app.state.dh
    urn = str(record["dataset_urn"])
    try:
        owners_raw = await asyncio.to_thread(facade.get_owners, urn)
    except Exception:
        log.warning("Signal enrichment degraded dataset_urn=%s", urn, exc_info=True)
        owners_raw = []
    owners = [
        Owner(
            urn=str(owner["urn"]),
            name=str(owner.get("name") or owner["urn"]),
            email=owner.get("email"),
        )
        for owner in owners_raw
    ]
    severity = _severity(urn)
    runs = await request.app.state.store.list_runs(limit=1000)
    generated_at = utc_now_iso()

    def triaged(kind: str) -> str | None:
        match = next(
            (
                run
                for run in runs
                if run["trigger_urn"] == urn
                and run["signal_kind"] == kind
                and run["status"] != "running"
            ),
            None,
        )
        return str(match["id"]) if match else None

    result: list[Signal] = []
    assertion_urns = [str(value) for value in record.get("assertion_urns") or []]
    name = str(record["name"])
    if assertion_urns:
        row_count = any(
            "rowcount" in value.lower() or "row-count" in value.lower()
            for value in assertion_urns
        )
        title = (
            f"Row count assertion failing on {name}"
            if row_count
            else f"Data quality assertion failing on {name}"
        )
        result.append(
            Signal(
                id=_signal_id(urn, "assertion"),
                dataset_urn=urn,
                name=name,
                layer=str(record.get("layer") or "unknown"),
                kind="assertion",
                severity=severity,
                title=title,
                detail=_assertion_detail(record),
                assertion_urns=assertion_urns,
                owners=owners,
                detected_at=generated_at,
                triaged_by_run_id=triaged("assertion"),
            )
        )
    freshness = record.get("freshness") or {}
    if freshness.get("breached"):
        hours_stale = freshness.get("hours_stale")
        sla_hours = freshness.get("sla_hours")
        detail = (
            f"{hours_stale:.1f}h stale · SLA {sla_hours:g}h"
            if hours_stale is not None and sla_hours is not None
            else "No recent operation timestamp is available"
        )
        result.append(
            Signal(
                id=_signal_id(urn, "freshness"),
                dataset_urn=urn,
                name=name,
                layer=str(record.get("layer") or "unknown"),
                kind="freshness",
                severity=severity,
                title=f"Freshness SLA breached on {name}",
                detail=detail,
                assertion_urns=[],
                hours_stale=hours_stale,
                sla_hours=sla_hours,
                owners=owners,
                detected_at=generated_at,
                triaged_by_run_id=triaged("freshness"),
            )
        )
    return result


@router.get("/signals", response_model=SignalsResponse)
async def get_signals(
    request: Request,
    refresh: bool = Query(default=False),
) -> SignalsResponse:
    """Return cached failing assertions and freshness breaches for the oncall namespace."""

    async def load() -> SignalsResponse:
        try:
            records = await asyncio.to_thread(request.app.state.dh.get_health_signals)
            groups = await asyncio.gather(*(_enrich_record(request, record) for record in records))
            signals = [signal for group in groups for signal in group]
            return SignalsResponse(
                degraded=False,
                generated_at=utc_now_iso(),
                signals=signals,
            )
        except Exception:
            log.warning("DataHub signals unavailable", exc_info=True)
            return SignalsResponse(degraded=True, generated_at=utc_now_iso(), signals=[])

    return await request.app.state.signals_cache.get("signals", load, refresh=refresh)
