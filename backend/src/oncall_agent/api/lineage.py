"""Cached, server-assembled lineage graph with per-node operational enrichment."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Query, Request

from demo.catalog import (
    CHARTS,
    DASHBOARDS,
    DATASETS,
    LINEAGE,
    ML_MODEL_URN,
    chart_urn,
    dashboard_urn,
)
from oncall_agent.api.errors import ApiError
from oncall_agent.api.models import ErrorResponse, GraphEdge, GraphNode, LineageGraphResponse
from oncall_agent.datahub import reads
from oncall_agent.datahub.urns import (
    entity_type_from_urn,
    infer_layer,
    short_display_name,
)

log = logging.getLogger(__name__)

router = APIRouter(tags=["lineage"])

_ERROR_RESPONSES = {422: {"model": ErrorResponse}, 503: {"model": ErrorResponse}}


def _safe[T](call: Callable[[], T], fallback: T) -> T:
    try:
        return call()
    except Exception:
        return fallback


def _known_nodes() -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = [
        {
            "id": dataset.urn,
            "name": short_display_name(dataset.name),
            "qualified_name": dataset.name,
            "entity_type": "DATASET",
            "layer": infer_layer(dataset.name),
            "depth": 0,
        }
        for dataset in DATASETS
    ]
    nodes.extend(
        {
            "id": chart_urn(name),
            "name": display,
            "qualified_name": name,
            "entity_type": "CHART",
            "layer": "bi",
            "depth": 0,
        }
        for name, display, *_ in CHARTS
    )
    nodes.extend(
        {
            "id": dashboard_urn(name),
            "name": display,
            "qualified_name": name,
            "entity_type": "DASHBOARD",
            "layer": "bi",
            "depth": 0,
        }
        for name, display, *_ in DASHBOARDS
    )
    nodes.append(
        {
            "id": ML_MODEL_URN,
            "name": "ETA Predictor v3",
            "qualified_name": "oncall_demo_eta_predictor",
            "entity_type": "MLMODEL",
            "layer": "ml",
            "depth": 0,
        }
    )
    return nodes


def _known_edges() -> list[dict[str, Any]]:
    by_key = {dataset.key: dataset.urn for dataset in DATASETS}
    edges: list[dict[str, Any]] = []
    for edge in LINEAGE:
        source = by_key[edge.upstream]
        target = by_key[edge.downstream]
        columns = [
            {"from": upstream_column, "to": downstream_column}
            for downstream_column, upstream_columns in edge.columns.items()
            for upstream_column in upstream_columns
        ]
        edges.append(
            {"id": f"{source}->{target}", "source": source, "target": target, "columns": columns}
        )
    for name, _display, input_key, _weekly_views in CHARTS:
        source = by_key[input_key]
        target = chart_urn(name)
        edges.append(
            {"id": f"{source}->{target}", "source": source, "target": target, "columns": []}
        )
    for name, _display, chart_names, *_ in DASHBOARDS:
        target = dashboard_urn(name)
        for chart_name in chart_names:
            source = chart_urn(chart_name)
            edges.append(
                {"id": f"{source}->{target}", "source": source, "target": target, "columns": []}
            )
    features = by_key["ml.trip_eta_features"]
    edges.append(
        {
            "id": f"{features}->{ML_MODEL_URN}",
            "source": features,
            "target": ML_MODEL_URN,
            "columns": [],
        }
    )
    return edges


_KNOWN_EDGE_MAP = {(edge["source"], edge["target"]): edge for edge in _known_edges()}
_DATASET_SLA = {dataset.urn: float(dataset.sla_hours) for dataset in DATASETS}


def _latest_assertion_failures(status: dict[str, Any]) -> tuple[int, int]:
    assertions = status.get("assertions") or []
    failures = 0
    for assertion in assertions:
        events = (assertion.get("runEvents") or {}).get("runEvents") or []
        latest = max(events, key=lambda item: int(item.get("timestampMillis") or 0), default=None)
        if latest and (latest.get("result") or {}).get("type") in {"FAILURE", "ERROR"}:
            failures += 1
    return failures, int(status.get("total") or len(assertions))


def _deep_link(ui_url: str, entity_type: str, urn: str) -> str:
    route = {
        "DATASET": "dataset",
        "CHART": "chart",
        "DASHBOARD": "dashboard",
        "MLMODEL": "mlModel",
    }[entity_type]
    return f"{ui_url.rstrip('/')}/{route}/{urn}"


def _enrich_node_sync(request: Request, node: dict[str, Any]) -> GraphNode:
    facade = request.app.state.dh
    entity_type = str(node["entity_type"])
    urn = str(node["id"])
    owners_raw = _safe(lambda: facade.get_owners(urn), [])
    owners = [
        {"urn": str(owner["urn"]), "name": str(owner.get("name") or owner["urn"])}
        for owner in owners_raw
    ]
    row_count: int | None = None
    hours_stale: float | None = None
    sla_hours: float | None = None
    queries_30d: int | None = None
    weekly_views: int | None = None
    failing_assertions = 0
    total_assertions = 0
    health = "unknown"
    if entity_type == "DATASET":
        assertion_status = _safe(lambda: facade.get_assertion_status(urn), {})
        failing_assertions, total_assertions = _latest_assertion_failures(assertion_status)
        sla = _DATASET_SLA.get(urn)
        freshness = _safe(
            lambda: facade.get_freshness(urn, **({"sla_hours": sla} if sla is not None else {})),
            {},
        )
        profiles = _safe(lambda: facade.get_row_count_trend(urn), [])
        latest_profile = max(
            profiles,
            key=lambda item: int(item.get("timestampMillis") or 0),
            default=None,
        )
        if latest_profile and latest_profile.get("rowCount") is not None:
            row_count = int(latest_profile["rowCount"])
        usage = _safe(lambda: facade.get_usage_stats(urn), {})
        raw_queries = (usage.get("aggregations") or {}).get("totalSqlQueries")
        queries_30d = int(raw_queries) if raw_queries is not None else None
        hours_stale = freshness.get("hours_stale")
        sla_hours = freshness.get("sla_hours")
        if failing_assertions:
            health = "broken"
        elif freshness.get("breached"):
            health = "degraded"
        elif freshness:
            health = "healthy"
    else:
        usage = _safe(lambda: facade.get_consumer_usage(urn), {})
        raw_views = usage.get("weekly_views")
        weekly_views = int(raw_views) if raw_views is not None else None
        health = "healthy" if usage else "unknown"
    platform = (
        "oncall"
        if entity_type == "DATASET"
        else "mlflow"
        if entity_type == "MLMODEL"
        else "looker"
    )
    return GraphNode(
        id=urn,
        name=str(node["name"]),
        qualified_name=str(node["qualified_name"]),
        entity_type=entity_type,
        layer=node["layer"],
        platform=platform,
        health=health,
        depth=int(node["depth"]),
        row_count=row_count,
        hours_stale=hours_stale,
        sla_hours=sla_hours,
        queries_30d=queries_30d,
        weekly_views=weekly_views,
        failing_assertions=failing_assertions,
        total_assertions=total_assertions,
        owners=owners,
        datahub_url=_deep_link(request.app.state.settings.datahub_ui_url, entity_type, urn),
    )


async def _enrich_nodes(request: Request, nodes: list[dict[str, Any]]) -> list[GraphNode]:
    semaphore = asyncio.Semaphore(8)

    async def one(node: dict[str, Any]) -> GraphNode:
        async with semaphore:
            return await asyncio.to_thread(_enrich_node_sync, request, node)

    return list(await asyncio.gather(*(one(node) for node in nodes)))


def _focus_base(urn: str, up: int, down: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    graph = reads.get_lineage_graph(urn)
    nodes = [
        node for node in graph["nodes"] if -up <= int(node["depth"]) <= down
    ]
    node_ids = {str(node["id"]) for node in nodes}
    edges: list[dict[str, Any]] = []
    for edge in graph["edges"]:
        source = str(edge["source"])
        target = str(edge["target"])
        if source not in node_ids or target not in node_ids:
            continue
        known = _KNOWN_EDGE_MAP.get((source, target))
        edges.append(known or edge)
    return nodes, edges


@router.get(
    "/lineage/graph",
    response_model=LineageGraphResponse,
    responses=_ERROR_RESPONSES,
)
async def get_lineage_graph(
    request: Request,
    urn: str | None = Query(default=None),
    up: int = Query(default=3, ge=0, le=3),
    down: int = Query(default=3, ge=0, le=3),
    whole_namespace: bool = Query(default=False),
) -> LineageGraphResponse:
    """Return an enriched focus graph or the complete 23-node demo namespace graph."""

    if not whole_namespace and not urn:
        raise ApiError(
            422,
            "lineage_scope_required",
            "Provide urn or set whole_namespace=true",
            "The focused graph accepts up and down depths from 0 through 3",
        )
    cache_key = "whole" if whole_namespace else f"{urn}|{up}|{down}"

    async def load() -> LineageGraphResponse:
        try:
            if whole_namespace:
                nodes = _known_nodes()
                edges = _known_edges()
                focus = None
            else:
                assert urn is not None
                entity_type = entity_type_from_urn(urn)
                if entity_type not in {"DATASET", "CHART", "DASHBOARD", "MLMODEL"}:
                    raise ApiError(
                        422,
                        "unsupported_lineage_urn",
                        "The lineage focus must be a dataset, chart, dashboard, or ML model URN",
                    )
                nodes, edges = await asyncio.to_thread(_focus_base, urn, up, down)
                focus = urn
            enriched = await _enrich_nodes(request, nodes)
            return LineageGraphResponse(
                nodes=enriched,
                edges=[GraphEdge.model_validate(edge) for edge in edges],
                focus_urn=focus,
            )
        except ApiError:
            raise
        except Exception as exc:
            log.warning("Lineage graph unavailable", exc_info=True)
            raise ApiError(
                503,
                "lineage_unavailable",
                f"DataHub could not assemble the lineage graph: {exc}",
                "Confirm GMS is running at the configured :8081 URL",
            ) from exc

    return await request.app.state.lineage_cache.get(cache_key, load)
