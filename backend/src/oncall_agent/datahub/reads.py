"""Read-only DataHub operations using the live-verified API contract."""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from itertools import pairwise
from typing import Any, Literal

import datahub.metadata.schema_classes as models

from oncall_agent.config import get_settings
from oncall_agent.datahub.client import execute_graphql, get_client, get_graph
from oncall_agent.datahub.urns import (
    entity_type_from_urn,
    infer_layer,
    qualified_name_from_urn,
    short_display_name,
)

HEALTH_SIGNALS_QUERY = """
query signals($input: SearchAcrossEntitiesInput!) {
  searchAcrossEntities(input: $input) {
    total
    searchResults { entity { urn
      ... on Dataset {
        name
        properties { name description customProperties { key value } }
        health { type status message causes } } } } } }
"""

ASSERTION_STATUS_QUERY = """
query a($urn: String!) {
  dataset(urn: $urn) {
    assertions(start: 0, count: 20) {
      total
      assertions {
        urn
        info { type description }
        runEvents(status: COMPLETE, limit: 3) {
          total failed succeeded
          runEvents {
            timestampMillis
            status
            result {
              type
              actualAggValue
              nativeResults { key value }
            }
          }
        }
      }
    }
  }
}
"""

# `operations` is NOT returned newest-first, and `limit` truncates the series BEFORE any
# ordering — with a small limit the newest record is silently dropped and a stale dataset reads
# as fresh. Ask for a generous window and pick the maximum timestampMillis ourselves.
FRESHNESS_QUERY = """
query o($urn: String!) { dataset(urn: $urn) {
  operations(limit: 50) {
    timestampMillis operationType lastUpdatedTimestamp numAffectedRows actor } } }
"""

PROFILE_USAGE_QUERY = """
query u($urn: String!) { dataset(urn: $urn) {
  datasetProfiles(limit: 2) { timestampMillis rowCount columnCount sizeInBytes }
  usageStats(resource: $urn, range: MONTH) {
    buckets { bucket metrics { uniqueUserCount totalSqlQueries } }
    aggregations { uniqueUserCount totalSqlQueries
      users { user { urn } count } fields { fieldName count } } } } }
"""

OPEN_INCIDENTS_QUERY = """
query i($urn: String!) { dataset(urn: $urn) {
  incidents(state: ACTIVE, start: 0, count: 20) {
    total incidents { urn incidentType customType title description priority startedAt
      incidentStatus { state stage message lastUpdated { time actor } }
      created { time actor } } } } }
"""

LINEAGE_QUERY = """
query l($input: SearchAcrossLineageInput!) {
  searchAcrossLineage(input: $input) {
    total searchResults { degree entity { urn type } paths { path { urn type } } } } }
"""

POSTMORTEM_SEARCH_QUERY = """
query postmortems($input: SearchAcrossEntitiesInput!) {
  searchAcrossEntities(input: $input) {
    total
    searchResults { entity { urn type } }
  }
}
"""

log = logging.getLogger(__name__)

_GRAPH_ENTITY_TYPES = {"DATASET", "CHART", "DASHBOARD", "MLMODEL"}

DEFAULT_FRESHNESS_SLA_HOURS = 24.0


def _search_input() -> dict[str, Any]:
    return {
        "types": ["DATASET"],
        "query": "*",
        "start": 0,
        "count": 100,
        "orFilters": [
            {
                "and": [
                    {
                        "field": "platform",
                        "condition": "EQUAL",
                        "values": [f"urn:li:dataPlatform:{get_settings().platform}"],
                        "negated": False,
                    }
                ]
            }
        ],
    }


def _properties(entity: Mapping[str, Any]) -> dict[str, str]:
    raw = (entity.get("properties") or {}).get("customProperties") or []
    return {str(item["key"]): str(item["value"]) for item in raw}


def map_health_signals(
    search_data: Mapping[str, Any],
    freshness_by_urn: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Map health search and freshness records into degraded dataset signal records."""

    records: list[dict[str, Any]] = []
    results = search_data.get("searchResults") or []
    for result in results:
        entity = result.get("entity") or {}
        urn = entity.get("urn")
        if not urn:
            continue
        health = [dict(item) for item in (entity.get("health") or [])]
        failing = [item for item in health if item.get("status") == "FAIL"]
        freshness = dict(freshness_by_urn.get(urn) or {})
        if freshness.get("breached"):
            stale = freshness.get("hours_stale")
            sla = freshness.get("sla_hours")
            message = (
                f"{stale:.1f}h stale against {sla:g}h SLA"
                if stale is not None and sla is not None
                else "no operation recorded; freshness unknown"
            )
            health.append(
                {"type": "FRESHNESS", "status": "FAIL", "message": message, "causes": [urn]}
            )
        if not failing and not freshness.get("breached"):
            continue
        properties = _properties(entity)
        qualified_name = entity.get("name") or (entity.get("properties") or {}).get("name")
        qualified_name = qualified_name or qualified_name_from_urn(urn)
        records.append(
            {
                "dataset_urn": urn,
                "name": short_display_name(qualified_name),
                "qualified_name": qualified_name,
                "layer": infer_layer(qualified_name),
                "health": health,
                "assertion_urns": [
                    cause
                    for item in failing
                    if item.get("type") == "ASSERTIONS"
                    for cause in (item.get("causes") or [])
                ],
                "freshness": freshness or None,
                "custom_properties": properties,
            }
        )
    return sorted(records, key=lambda item: item["qualified_name"])


def get_health_signals() -> list[dict[str, Any]]:
    """Return assertion failures and SLA freshness breaches for all oncall datasets."""

    data = execute_graphql(HEALTH_SIGNALS_QUERY, {"input": _search_input()})
    search = data.get("searchAcrossEntities") or {}
    freshness: dict[str, dict[str, Any]] = {}
    for result in search.get("searchResults") or []:
        entity = result.get("entity") or {}
        urn = entity.get("urn")
        if not urn:
            continue
        props = _properties(entity)
        sla_text = props.get("oncall.freshness_sla_hours")
        if sla_text is not None:
            freshness[urn] = get_freshness(urn, sla_hours=float(sla_text))
    return map_health_signals(search, freshness)


def get_assertion_status(dataset_urn: str) -> dict[str, Any]:
    """Return assertion definitions and their latest complete results for a dataset."""

    data = execute_graphql(ASSERTION_STATUS_QUERY, {"urn": dataset_urn})
    assertions = (data.get("dataset") or {}).get("assertions") or {}
    items = assertions.get("assertions") or []
    for item in items:
        run_events = (item.get("runEvents") or {}).get("runEvents") or []
        run_events.sort(key=lambda event: int(event["timestampMillis"]), reverse=True)
    return {"total": assertions.get("total", 0), "assertions": items}


def get_freshness(
    dataset_urn: str,
    *,
    sla_hours: float | None = None,
    now_ms: int | None = None,
) -> dict[str, Any]:
    """Return the newest operation-derived freshness state for a dataset."""

    if sla_hours is None:
        # Read the SLA off this one dataset's own aspect. Do NOT fall back to the namespace-wide
        # search here: the agent calls get_freshness() once per ancestor while walking lineage,
        # and a 100-dataset search per hop is an N+1 that shows up directly as demo latency.
        props = get_graph().get_aspect(
            entity_urn=dataset_urn, aspect_type=models.DatasetPropertiesClass
        )
        if props is None:
            raise ValueError(f"Dataset not found in the oncall namespace: {dataset_urn}")
        sla_text = (props.customProperties or {}).get("oncall.freshness_sla_hours")
        sla_hours = float(sla_text) if sla_text is not None else DEFAULT_FRESHNESS_SLA_HOURS
    data = execute_graphql(FRESHNESS_QUERY, {"urn": dataset_urn})
    operations = (data.get("dataset") or {}).get("operations") or []
    latest = max(operations, key=lambda item: int(item["timestampMillis"])) if operations else None
    last_updated = latest.get("lastUpdatedTimestamp") if latest else None
    current_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    hours_stale = (
        max(0.0, (current_ms - int(last_updated)) / 3_600_000) if last_updated is not None else None
    )
    return {
        "last_updated_timestamp": last_updated,
        "hours_stale": hours_stale,
        "sla_hours": sla_hours,
        "breached": hours_stale is None or hours_stale > sla_hours,
        "operation": latest,
    }


def _profile_usage(dataset_urn: str) -> dict[str, Any]:
    data = execute_graphql(PROFILE_USAGE_QUERY, {"urn": dataset_urn})
    return data.get("dataset") or {}


def get_row_count_trend(dataset_urn: str) -> list[dict[str, Any]]:
    """Return the two most recent dataset profile points from the verified profile query."""

    return _profile_usage(dataset_urn).get("datasetProfiles") or []


def get_usage_stats(dataset_urn: str) -> dict[str, Any]:
    """Return monthly usage buckets and aggregations for a dataset."""

    return _profile_usage(dataset_urn).get("usageStats") or {}


_CONSUMER_PROPERTY_ASPECTS = {
    "CHART": models.ChartInfoClass,
    "DASHBOARD": models.DashboardInfoClass,
    "MLMODEL": models.MLModelPropertiesClass,
}


def get_consumer_usage(entity_urn: str) -> dict[str, Any]:
    """Return the seeded ``weekly_views`` audience size for a chart, dashboard or ML model.

    OSS DataHub has no usage aspect for these entity types that we can populate, and the MCP
    ``get_entities`` tool omits their custom properties entirely — so the agent otherwise scores
    every dashboard at zero and the blast-radius ranking collapses. Read the properties aspect
    directly instead.
    """

    entity_type = entity_type_from_urn(entity_urn)
    aspect_type = _CONSUMER_PROPERTY_ASPECTS.get(entity_type)
    if aspect_type is None:
        return {"urn": entity_urn, "entity_type": entity_type, "weekly_views": None}
    aspect = get_graph().get_aspect(entity_urn=entity_urn, aspect_type=aspect_type)
    properties = dict(getattr(aspect, "customProperties", None) or {}) if aspect else {}
    raw_views = properties.get("weekly_views")
    return {
        "urn": entity_urn,
        "entity_type": entity_type,
        "name": short_display_name(entity_urn),
        "weekly_views": int(raw_views) if raw_views is not None and raw_views.isdigit() else None,
        "custom_properties": properties,
    }


def get_owners(entity_urn: str) -> list[dict[str, Any]]:
    """Return ownership entries enriched with display name and email.

    The notification step addresses humans, so a bare corpuser URN is not enough — resolve
    ``corpUserInfo`` / ``corpGroupInfo`` for each owner.
    """

    ownership = get_graph().get_aspect(entity_urn=entity_urn, aspect_type=models.OwnershipClass)
    if ownership is None:
        return []
    owners: list[dict[str, Any]] = []
    for owner in ownership.owners:
        record: dict[str, Any] = {
            "urn": owner.owner,
            "type": owner.type,
            "is_group": owner.owner.startswith("urn:li:corpGroup:"),
            "name": owner.owner.rsplit(":", 1)[-1],
            "email": None,
            "title": None,
        }
        try:
            if record["is_group"]:
                info = get_graph().get_aspect(
                    entity_urn=owner.owner, aspect_type=models.CorpGroupInfoClass
                )
                if info is not None:
                    record["name"] = info.displayName or record["name"]
                    record["email"] = info.email
            else:
                info = get_graph().get_aspect(
                    entity_urn=owner.owner, aspect_type=models.CorpUserInfoClass
                )
                if info is not None:
                    record["name"] = info.displayName or info.fullName or record["name"]
                    record["email"] = info.email
                    record["title"] = info.title
        except Exception:  # an unresolvable owner must not fail the whole read
            log.debug("Could not resolve owner profile for %s", owner.owner, exc_info=True)
        owners.append(record)
    return owners


def list_open_incidents(dataset_urn: str | None = None) -> list[dict[str, Any]]:
    """Return active incidents for one dataset or all datasets in the oncall namespace."""

    if dataset_urn is None:
        search_data = execute_graphql(HEALTH_SIGNALS_QUERY, {"input": _search_input()})
        search = search_data.get("searchAcrossEntities") or {}
        incidents: dict[str, dict[str, Any]] = {}
        for result in search.get("searchResults") or []:
            urn = (result.get("entity") or {}).get("urn")
            if urn:
                incidents.update({item["urn"]: item for item in list_open_incidents(urn)})
        return list(incidents.values())
    data = execute_graphql(OPEN_INCIDENTS_QUERY, {"urn": dataset_urn})
    return ((data.get("dataset") or {}).get("incidents") or {}).get("incidents") or []


def get_queries(dataset_urn: str) -> list[dict[str, Any]]:
    """Return seeded query entities whose query-subject aspect references the dataset."""

    graph = get_graph()
    queries: list[dict[str, Any]] = []
    for suffix in (
        "daily-rides",
        "zone-demand",
        "fct-trips-scan",
        "revenue-recon",
        "eta-features",
    ):
        urn = f"urn:li:query:oncall-q-{suffix}"
        subjects = graph.get_aspect(entity_urn=urn, aspect_type=models.QuerySubjectsClass)
        if subjects is None or not any(item.entity == dataset_urn for item in subjects.subjects):
            continue
        properties = graph.get_aspect(entity_urn=urn, aspect_type=models.QueryPropertiesClass)
        if properties is not None:
            queries.append(
                {
                    "urn": urn,
                    "name": properties.name,
                    "description": properties.description,
                    "source": properties.source,
                    "statement": properties.statement.value,
                }
            )
    return queries


def _lineage_input(urn: str, direction: Literal["UPSTREAM", "DOWNSTREAM"]) -> dict[str, Any]:
    return {
        "urn": urn,
        "direction": direction,
        "query": "*",
        "start": 0,
        "count": 50,
        "orFilters": [
            {
                "and": [
                    {
                        "field": "degree",
                        "condition": "EQUAL",
                        "values": ["1", "2", "3+"],
                        "negated": False,
                    }
                ]
            }
        ],
    }


def assemble_lineage_graph(
    focus_urn: str,
    upstream_results: list[Mapping[str, Any]],
    downstream_results: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """Assemble signed-depth nodes and deduplicated directed edges from lineage search paths."""

    focus_type = entity_type_from_urn(focus_urn)
    nodes: dict[str, dict[str, Any]] = {
        focus_urn: {
            "id": focus_urn,
            "name": short_display_name(focus_urn),
            "qualified_name": qualified_name_from_urn(focus_urn),
            "entity_type": focus_type,
            "layer": infer_layer(focus_urn, entity_type=focus_type),
            "depth": 0,
        }
    }
    edges: dict[tuple[str, str], dict[str, Any]] = {}

    def add_results(results: list[Mapping[str, Any]], direction: str) -> None:
        sign = -1 if direction == "UPSTREAM" else 1
        for result in results:
            entity = result.get("entity") or {}
            urn = entity.get("urn")
            if not urn:
                continue
            raw_degree = str(result.get("degree", "1")).removesuffix("+")
            degree = int(raw_degree) if raw_degree.isdigit() else 1
            entity_type = str(entity.get("type") or entity_type_from_urn(urn)).upper()
            if entity_type in _GRAPH_ENTITY_TYPES:
                candidate = {
                    "id": urn,
                    "name": short_display_name(urn),
                    "qualified_name": qualified_name_from_urn(urn),
                    "entity_type": entity_type,
                    "layer": infer_layer(urn, entity_type=entity_type),
                    "depth": sign * degree,
                }
                previous = nodes.get(urn)
                if previous is None or abs(candidate["depth"]) < abs(previous["depth"]):
                    nodes[urn] = candidate

            paths = result.get("paths") or []
            if not paths:
                paths = [
                    {
                        "path": [
                            {"urn": focus_urn, "type": focus_type},
                            {"urn": urn, "type": entity_type},
                        ]
                    }
                ]
            for wrapped in paths:
                path = [
                    {
                        "urn": item["urn"],
                        "type": str(item.get("type") or entity_type_from_urn(item["urn"])).upper(),
                    }
                    for item in (wrapped.get("path") or [])
                    if item.get("urn")
                ]
                if len(path) < 2:
                    continue
                if path[0]["urn"] != focus_urn and path[-1]["urn"] == focus_urn:
                    path.reverse()
                path = [item for item in path if item["type"] in _GRAPH_ENTITY_TYPES]
                for index, item in enumerate(path):
                    path_urn = item["urn"]
                    if path_urn == focus_urn:
                        continue
                    path_depth = sign * index
                    if path_urn in nodes:
                        if abs(path_depth) < abs(nodes[path_urn]["depth"]):
                            nodes[path_urn]["depth"] = path_depth
                        continue
                    nodes[path_urn] = {
                        "id": path_urn,
                        "name": short_display_name(path_urn),
                        "qualified_name": qualified_name_from_urn(path_urn),
                        "entity_type": item["type"],
                        "layer": infer_layer(path_urn, entity_type=item["type"]),
                        "depth": path_depth,
                    }
                for left_item, right_item in pairwise(path):
                    left = left_item["urn"]
                    right = right_item["urn"]
                    source, target = (right, left) if direction == "UPSTREAM" else (left, right)
                    key = (source, target)
                    edges[key] = {
                        "id": f"{source}->{target}",
                        "source": source,
                        "target": target,
                        "columns": [],
                    }

    add_results(upstream_results, "UPSTREAM")
    add_results(downstream_results, "DOWNSTREAM")
    return {
        "nodes": sorted(nodes.values(), key=lambda item: (item["depth"], item["qualified_name"])),
        "edges": sorted(edges.values(), key=lambda item: item["id"]),
        "focus_urn": focus_urn,
    }


def get_lineage_graph(focus_urn: str) -> dict[str, Any]:
    """Read and assemble up-to-unlimited lineage in both directions around an entity."""

    upstream_data = execute_graphql(LINEAGE_QUERY, {"input": _lineage_input(focus_urn, "UPSTREAM")})
    downstream_data = execute_graphql(
        LINEAGE_QUERY, {"input": _lineage_input(focus_urn, "DOWNSTREAM")}
    )
    upstream = (upstream_data.get("searchAcrossLineage") or {}).get("searchResults") or []
    downstream = (downstream_data.get("searchAcrossLineage") or {}).get("searchResults") or []
    return assemble_lineage_graph(focus_urn, upstream, downstream)


def get_lineage_native(
    source_urn: str,
    *,
    direction: Literal["upstream", "downstream"] = "upstream",
    max_hops: int = 1,
    source_column: str | None = None,
    count: int = 100,
) -> list[dict[str, Any]]:
    """Return a compact native-SDK lineage result for recall and MCP degradation."""

    results = get_client().lineage.get_lineage(
        source_urn=source_urn,
        source_column=source_column,
        direction=direction,
        max_hops=max_hops,
        count=count,
    )
    compact: list[dict[str, Any]] = []
    for item in results:
        compact.append(
            {
                "urn": item.urn,
                "type": str(item.type).upper(),
                "hops": int(item.hops),
                "name": item.name or short_display_name(item.urn),
                "platform": item.platform,
                "paths": [
                    {
                        "urn": path.urn,
                        "name": path.entity_name,
                        "column": path.column_name,
                    }
                    for path in (item.paths or [])
                ],
            }
        )
    return sorted(compact, key=lambda value: (value["hops"], value["urn"]))


def search_postmortem_datasets() -> list[str]:
    """Search the verified structured-property recall index and return dataset URNs."""

    search_input = {
        "types": ["DATASET"],
        "query": "*",
        "start": 0,
        "count": 50,
        "orFilters": [
            {
                "and": [
                    {
                        "field": "structuredProperties.oncall.postmortem",
                        "condition": "EXISTS",
                        "values": [],
                        "negated": False,
                    }
                ]
            }
        ],
    }
    data = execute_graphql(POSTMORTEM_SEARCH_QUERY, {"input": search_input})
    search = data.get("searchAcrossEntities") or {}
    return [
        str(entity["urn"])
        for result in search.get("searchResults") or []
        if (entity := result.get("entity") or {}).get("urn")
    ]
