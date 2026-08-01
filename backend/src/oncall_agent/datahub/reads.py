"""Read-only DataHub operations using the live-verified API contract."""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable, Mapping
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

# `operations` is NOT returned newest-first, and `limit` truncates the series BEFORE any ordering,
# so the newest record can be silently dropped and a stale dataset reads as FRESH. Raising the
# limit only moves the ceiling — a long demo session accumulated 68 points and broke a limit of 50.
# The count-independent fix is to bound by TIME: ask for a recent window, which cannot be truncated
# past the newest record, and fall back to a large limit only if the window is empty (a dataset
# genuinely untouched for longer than the window). Always take max(timestampMillis) ourselves.
FRESHNESS_WINDOW_QUERY = """
query o($urn: String!, $start: Long!) { dataset(urn: $urn) {
  operations(startTimeMillis: $start, limit: 200) {
    timestampMillis operationType lastUpdatedTimestamp numAffectedRows actor } } }
"""

FRESHNESS_QUERY = """
query o($urn: String!) { dataset(urn: $urn) {
  operations(limit: 1000) {
    timestampMillis operationType lastUpdatedTimestamp numAffectedRows actor } } }
"""

# How far back the bounded freshness window reaches. Comfortably longer than the longest SLA in
# the demo warehouse (168 h) so a breach is always inside it.
FRESHNESS_WINDOW_HOURS = 24 * 30

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


def dataset_exists(dataset_urn: str) -> bool:
    """Return whether a dataset has its canonical index-independent key aspect."""

    return (
        get_graph().get_aspect(
            entity_urn=dataset_urn,
            aspect_type=models.DatasetKeyClass,
        )
        is not None
    )


def has_upstream_edges(dataset_urn: str) -> bool | None:
    """Check the upstream-lineage aspect without relying on the search index.

    ``True`` and ``False`` are authoritative aspect results. ``None`` means the aspect read
    itself failed, so a caller must not interpret an empty search-backed lineage result as proof
    that the dataset is a source node.
    """

    try:
        aspect = get_graph().get_aspect(
            entity_urn=dataset_urn,
            aspect_type=models.UpstreamLineageClass,
        )
    except Exception:
        log.warning("upstreamLineage aspect read failed for %s", dataset_urn, exc_info=True)
        return None
    return bool(aspect and aspect.upstreams)


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
    current_ms_for_window = now_ms if now_ms is not None else int(time.time() * 1000)
    window_start = current_ms_for_window - int(FRESHNESS_WINDOW_HOURS * 3_600_000)
    data = execute_graphql(
        FRESHNESS_WINDOW_QUERY, {"urn": dataset_urn, "start": window_start}
    )
    operations = (data.get("dataset") or {}).get("operations") or []
    if not operations:
        # Nothing in the recent window — the dataset may genuinely be ancient. Fall back to an
        # unbounded-ish read rather than reporting unknown freshness.
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


def _schema_field_path(field_urn: str, dataset_urn: str) -> str | None:
    prefix = f"urn:li:schemaField:({dataset_urn},"
    if not field_urn.startswith(prefix) or not field_urn.endswith(")"):
        return None
    return field_urn[len(prefix) : -1]


def get_schema_drift(dataset_urn: str) -> dict[str, Any]:
    """Compare live schema fields with columns referenced by direct downstream lineage.

    Fine-grained lineage on each downstream is the durable declaration of which source columns
    that consumer reads. A referenced source column missing from the source's live
    ``schemaMetadata`` aspect is an intrinsic schema breach.
    """

    graph = get_graph()
    schema = graph.get_aspect(
        entity_urn=dataset_urn,
        aspect_type=models.SchemaMetadataClass,
    )
    if schema is None:
        return {
            "urn": dataset_urn,
            "missing_columns": [],
            "added_columns": [],
            "verdict": "unknown",
            "guidance": "Live schemaMetadata is unavailable; do not treat schema as healthy.",
        }

    live_columns = {str(field.fieldPath) for field in schema.fields}
    downstreams = get_lineage_native(dataset_urn, direction="downstream", max_hops=1)
    dependency_columns: set[str] = set()
    inspected_downstreams: list[str] = []
    for downstream in downstreams:
        if downstream.get("type") != "DATASET" or int(downstream.get("hops") or 0) != 1:
            continue
        downstream_urn = str(downstream["urn"])
        lineage = graph.get_aspect(
            entity_urn=downstream_urn,
            aspect_type=models.UpstreamLineageClass,
        )
        if lineage is None:
            continue
        inspected_downstreams.append(downstream_urn)
        for fine_grained in lineage.fineGrainedLineages or []:
            for upstream_field in fine_grained.upstreams or []:
                field_path = _schema_field_path(str(upstream_field), dataset_urn)
                if field_path is not None:
                    dependency_columns.add(field_path)

    missing_columns = sorted(dependency_columns - live_columns)
    if missing_columns:
        verdict = "broken"
        guidance = "Downstream lineage consumes columns absent from the live upstream schema."
    elif dependency_columns:
        verdict = "healthy"
        guidance = "Every column referenced by direct downstream lineage exists in the live schema."
    else:
        verdict = "unknown"
        guidance = "No direct downstream column dependencies were available for comparison."
    return {
        "urn": dataset_urn,
        "missing_columns": missing_columns,
        # Dependency lineage can prove removals but cannot distinguish a legitimate unused field
        # from a newly added one. Keep this explicit rather than inventing a baseline.
        "added_columns": [],
        "verdict": verdict,
        "dependency_columns": sorted(dependency_columns),
        "downstreams_checked": sorted(set(inspected_downstreams)),
        "guidance": guidance,
    }


def missing_indexed_upstream_edges(edges: Iterable[tuple[str, str]]) -> list[str]:
    """Return expected upstream edges absent from the aspect or search-backed lineage read."""

    expected_by_downstream: dict[str, set[str]] = {}
    for upstream_urn, downstream_urn in edges:
        expected_by_downstream.setdefault(downstream_urn, set()).add(upstream_urn)

    missing: list[str] = []
    graph = get_graph()
    for downstream_urn, expected_upstreams in expected_by_downstream.items():
        aspect = graph.get_aspect(
            entity_urn=downstream_urn,
            aspect_type=models.UpstreamLineageClass,
        )
        aspect_upstreams = {item.dataset for item in (aspect.upstreams if aspect else [])}
        indexed_upstreams = {
            str(item["urn"])
            for item in get_lineage_native(
                downstream_urn,
                direction="upstream",
                max_hops=1,
            )
            if int(item.get("hops") or 0) == 1
        }
        for upstream_urn in sorted(expected_upstreams):
            edge = f"{upstream_urn}->{downstream_urn}"
            if upstream_urn not in aspect_upstreams:
                missing.append(f"{edge} (aspect)")
            elif upstream_urn not in indexed_upstreams:
                missing.append(f"{edge} (index)")
    return missing


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
