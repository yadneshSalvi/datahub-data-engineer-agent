"""Strict-schema native tools for OSS-only reads, writes, memory, and narration."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import httpx
from agents import AgentBase, RunContextWrapper, function_tool
from agents.tool_context import ToolContext

from oncall_agent.agent.context import TriageContext
from oncall_agent.agent.events import (
    ActionEvent,
    BlastRadiusEvent,
    BlastRadiusTotals,
    CausalPathEvent,
    ErrorEvent,
    FindingEvent,
    MetricEvent,
    PhaseEvent,
    PostMortemEvent,
    PostMortemUrls,
    RecallEvent,
    RecallTop,
)
from oncall_agent.agent.models import (
    ActionRecord,
    CausalNode,
    Finding,
    PostMortem,
    RecalledPostMortem,
)
from oncall_agent.config import get_settings
from oncall_agent.datahub.client import incident_url_for
from oncall_agent.datahub.urns import short_display_name

log = logging.getLogger(__name__)

PHASE_INDEX = {
    "recall": 0,
    "triage": 1,
    "root_cause": 2,
    "blast_radius": 3,
    "act": 4,
    "learn": 5,
    "done": 6,
}

TAG_DEFINITIONS = {
    "oncall_root_cause": (
        "On-Call: Root Cause",
        "Localized root cause of an active incident",
        "#EF4444",
    ),
    "oncall_impacted": (
        "On-Call: Impacted",
        "Downstream asset inside an active blast radius",
        "#F59E0B",
    ),
    "oncall_triaged": (
        "On-Call: Triaged",
        "An agent has completed triage on this asset",
        "#10B981",
    ),
}

_REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def _compact_json(value: Any, *, max_chars: int = 12_000) -> str:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    if len(encoded) <= max_chars:
        return encoded
    return json.dumps(
        {
            "truncated": True,
            "original_chars": len(encoded),
            "preview": encoded[: max_chars - 100],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _bump(ctx: ToolContext[TriageContext]) -> TriageContext:
    ctx.context.tool_calls += 1
    return ctx.context


def _native_results(values: list[Mapping[str, Any]]) -> dict[str, str]:
    return {str(item.get("key")): str(item.get("value")) for item in values if item.get("key")}


def _parse_datetime(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def rank_recalled_postmortems(
    candidates: list[Mapping[str, Any]],
    ancestor_hops: Mapping[str, int],
    *,
    signal_kind: str,
    now: datetime | None = None,
) -> list[RecalledPostMortem]:
    """Rank parsed memories using root ancestry, distance, symptom kind, and age."""

    current = now or datetime.now(UTC)
    ranked: list[RecalledPostMortem] = []
    for candidate in candidates:
        try:
            root_urn = str(candidate["root_cause_urn"])
            hops = ancestor_hops.get(root_urn, 99)
            detected = str(candidate.get("detected_at") or "")
            detected_at = _parse_datetime(detected)
            age_days = (
                max(0.0, (current - detected_at.astimezone(UTC)).total_seconds() / 86_400)
                if detected_at is not None
                else 3650.0
            )
            relevance = (50.0 if root_urn in ancestor_hops else 0.0) - 5.0 * hops - age_days
            if str(candidate.get("check_kind") or "") == signal_kind:
                relevance += 15.0
            causal_path = [
                CausalNode.model_validate(item) for item in candidate.get("causal_path", [])
            ]
            ranked.append(
                RecalledPostMortem(
                    incident_id=str(candidate["incident_id"]),
                    root_cause_urn=root_urn,
                    root_cause_name=str(
                        candidate.get("root_cause_name") or short_display_name(root_urn)
                    ),
                    symptom=str(candidate.get("symptom") or "Prior data-quality incident"),
                    causal_path=causal_path,
                    evidence=[str(item) for item in candidate.get("evidence", [])],
                    resolution=str(
                        candidate.get("recommended_action")
                        or candidate.get("resolution")
                        or "No recorded resolution"
                    ),
                    detected_at=detected,
                    relevance=round(relevance, 3),
                    hops_away=hops,
                )
            )
        except (KeyError, TypeError, ValueError):
            log.warning("Ignoring malformed post-mortem recall value", exc_info=True)
    deduplicated: dict[str, RecalledPostMortem] = {}
    for item in sorted(ranked, key=lambda value: value.relevance, reverse=True):
        deduplicated.setdefault(item.incident_id, item)
    return list(deduplicated.values())


async def _emit_read_finding(
    context: TriageContext,
    *,
    urn: str,
    check: str,
    verdict: str,
    detail: str,
) -> None:
    await context.emit(
        FindingEvent(
            urn=urn,
            name=short_display_name(urn),
            check=check,
            verdict=verdict,
            detail=detail[:500],
        )
    )


@function_tool
async def set_phase(
    ctx: ToolContext[TriageContext],
    phase: Literal["recall", "triage", "root_cause", "blast_radius", "act", "learn", "done"],
    note: str,
) -> str:
    """Move to a required playbook phase and narrate why."""

    context = _bump(ctx)
    context.phase = phase
    await context.emit(PhaseEvent(phase=phase, note=note[:500], phase_index=PHASE_INDEX[phase]))
    return _compact_json({"phase": phase, "accepted": True})


def _build_causal_path(context: TriageContext, root_urn: str) -> list[CausalNode]:
    ordered_urns = list(dict.fromkeys(item.urn for item in context.findings))
    urns = [
        urn
        for urn in ordered_urns
        if urn == root_urn
        or any(
            item.verdict in {"degraded", "broken"}
            for item in context.findings
            if item.urn == urn
        )
    ]
    nodes: list[CausalNode] = []
    priority = {"unknown": 0, "healthy": 1, "degraded": 2, "broken": 3}
    for index, urn in enumerate(urns):
        findings = [item for item in context.findings if item.urn == urn]
        worst = max(findings, key=lambda item: priority[item.verdict])
        nodes.append(
            CausalNode(
                urn=urn,
                name=worst.name,
                hops_from_symptom=index,
                verdict="root_cause" if urn == root_urn else worst.verdict,
                evidence=[item.detail for item in findings],
            )
        )
    return nodes


@function_tool
async def record_finding(
    ctx: ToolContext[TriageContext],
    urn: str,
    check: Literal["assertion", "freshness", "row_count", "schema", "usage", "query"],
    verdict: Literal["healthy", "degraded", "broken", "unknown"],
    detail: str,
) -> str:
    """Record the agent's evidence-backed verdict for one catalog asset."""

    context = _bump(ctx)
    finding = Finding(
        urn=urn,
        name=short_display_name(urn),
        check=check,
        verdict=verdict,
        detail=detail,
    )
    context.findings.append(finding)
    await context.emit(FindingEvent(**finding.model_dump()))
    root_confirmed = verdict == "broken" and detail.lstrip().upper().startswith("ROOT CAUSE:")
    if root_confirmed and context.root_cause_urn is None:
        context.root_cause_urn = urn
        context.time_to_root_cause_s = round(time.monotonic() - context.started_at, 3)
        context.causal_path = _build_causal_path(context, urn)
        await context.emit(CausalPathEvent(nodes=context.causal_path))
        await context.emit(
            MetricEvent(name="time_to_root_cause_s", value=context.time_to_root_cause_s)
        )
    return _compact_json({"recorded": True, "root_cause_confirmed": root_confirmed})


@function_tool
async def get_assertion_status(ctx: ToolContext[TriageContext], dataset_urn: str) -> str:
    """Read OSS assertion definitions and their latest complete results."""

    context = _bump(ctx)
    raw = await asyncio.to_thread(context.dh.get_assertion_status, dataset_urn)
    assertions: list[dict[str, Any]] = []
    for item in raw.get("assertions") or []:
        events = (item.get("runEvents") or {}).get("runEvents") or []
        latest_event = max(events, key=lambda event: int(event["timestampMillis"]), default=None)
        latest = None
        if latest_event is not None:
            result = latest_event.get("result") or {}
            native = _native_results(result.get("nativeResults") or [])
            latest = {
                "result": result.get("type"),
                "timestamp": latest_event.get("timestampMillis"),
                "observed": native.get("observed") or result.get("actualAggValue"),
                "expected": native.get("expected"),
            }
        assertions.append(
            {
                "urn": item.get("urn"),
                "type": (item.get("info") or {}).get("type"),
                "description": (item.get("info") or {}).get("description"),
                "latest": latest,
            }
        )
    failing = sum(
        1 for item in assertions if (item.get("latest") or {}).get("result") in {"FAILURE", "ERROR"}
    )
    payload = {
        "urn": dataset_urn,
        "total": raw.get("total", 0),
        "failing": failing,
        "assertions": assertions,
    }
    await _emit_read_finding(
        context,
        urn=dataset_urn,
        check="assertion",
        verdict="broken" if failing else "healthy",
        detail=f"{failing} of {raw.get('total', 0)} assertions failing",
    )
    return _compact_json(payload)


@function_tool
async def get_freshness(ctx: ToolContext[TriageContext], dataset_urn: str) -> str:
    """Read operation-derived freshness against the dataset's configured SLA."""

    context = _bump(ctx)
    raw = await asyncio.to_thread(context.dh.get_freshness, dataset_urn)
    timestamp = raw.get("last_updated_timestamp")
    iso = (
        datetime.fromtimestamp(int(timestamp) / 1000, UTC).isoformat().replace("+00:00", "Z")
        if timestamp is not None
        else None
    )
    hours_stale = raw.get("hours_stale")
    sla = raw.get("sla_hours")
    payload = {
        "urn": dataset_urn,
        "last_updated_iso": iso,
        "hours_stale": round(hours_stale, 2) if hours_stale is not None else None,
        "sla_hours": sla,
        "breaching": bool(raw.get("breached")),
        "margin_hours": round(hours_stale - sla, 2)
        if hours_stale is not None and sla is not None
        else None,
    }
    await _emit_read_finding(
        context,
        urn=dataset_urn,
        check="freshness",
        verdict="broken" if raw.get("breached") else "healthy",
        detail=(
            f"{payload['hours_stale']}h stale against {sla}h SLA"
            if hours_stale is not None
            else "No freshness operation found"
        ),
    )
    return _compact_json(payload)


@function_tool
async def get_row_count_trend(ctx: ToolContext[TriageContext], dataset_urn: str) -> str:
    """Read the two returned profile points and calculate the row-count change."""

    context = _bump(ctx)
    raw = await asyncio.to_thread(context.dh.get_row_count_trend, dataset_urn)
    profiles = sorted(raw, key=lambda item: int(item.get("timestampMillis") or 0), reverse=True)
    latest = profiles[0] if profiles else None
    previous = profiles[1] if len(profiles) > 1 else None
    latest_count = (
        int(latest["rowCount"]) if latest and latest.get("rowCount") is not None else None
    )
    previous_count = (
        int(previous["rowCount"]) if previous and previous.get("rowCount") is not None else None
    )
    pct_change = (
        round((latest_count - previous_count) / previous_count * 100, 2)
        if latest_count is not None and previous_count
        else None
    )
    payload = {
        "urn": dataset_urn,
        "latest_row_count": latest_count,
        "previous_row_count": previous_count,
        "pct_change": pct_change,
        "profiled_at": latest.get("timestampMillis") if latest else None,
    }
    verdict = "degraded" if pct_change is not None and pct_change <= -50 else "healthy"
    await _emit_read_finding(
        context,
        urn=dataset_urn,
        check="row_count",
        verdict=verdict,
        detail=f"latest={latest_count}, previous={previous_count}, change={pct_change}%",
    )
    return _compact_json(payload)


@function_tool
async def check_schema_drift(ctx: ToolContext[TriageContext], dataset_urn: str) -> str:
    """Check live schema against columns that direct downstream lineage consumes.

    This check is mandatory at every node in every signal-relevant upstream branch, continuing to
    a confirmed source even when a direct parent looks healthy. A missing dependency column is an
    intrinsic breach even when assertions, freshness, and row-count trend look healthy.
    """

    context = _bump(ctx)
    payload = await asyncio.to_thread(context.dh.get_schema_drift, dataset_urn)
    missing = [str(item) for item in payload.get("missing_columns") or []]
    verdict = str(payload.get("verdict") or "unknown")
    detail = (
        f"missing downstream dependency columns: {', '.join(missing)}"
        if missing
        else str(payload.get("guidance") or "Schema comparison unavailable")
    )
    await _emit_read_finding(
        context,
        urn=dataset_urn,
        check="schema",
        verdict=verdict,
        detail=detail,
    )
    return _compact_json(payload)


@function_tool
async def confirm_no_upstreams(ctx: ToolContext[TriageContext], dataset_urn: str) -> str:
    """Confirm an empty search-backed lineage result before declaring a source root cause.

    This tool is mandatory whenever an upstream lineage read returns empty.
    """

    context = _bump(ctx)
    has_edges = await asyncio.to_thread(context.dh.has_upstream_edges, dataset_urn)
    if has_edges is None:
        verdict = "unknown"
        guidance = "Aspect read failed. Do NOT declare root cause here; retry."
    elif has_edges:
        verdict = "contradicted"
        guidance = (
            "The lineage index returned no upstreams but the upstreamLineage aspect HAS them; "
            "the index is stale. Re-read lineage for this node and keep walking. Do NOT stop here."
        )
    else:
        verdict = "confirmed"
        guidance = "Genuine source node. The stop rule is satisfied."
    await _emit_read_finding(
        context,
        urn=dataset_urn,
        check="lineage",
        verdict="healthy" if has_edges is False else "unknown",
        detail=f"source-node check: {verdict}",
    )
    return _compact_json(
        {
            "urn": dataset_urn,
            "verdict": verdict,
            "guidance": guidance,
        }
    )


@function_tool
async def get_usage_stats(ctx: ToolContext[TriageContext], dataset_urn: str) -> str:
    """Read how heavily an asset is used, for ranking blast radius by real audience size.

    Accepts a dataset URN (30-day query and user aggregations) or a chart / dashboard / ML model
    URN (weekly viewer count). Always use this before assigning blast-radius severity.
    """

    context = _bump(ctx)
    if not dataset_urn.startswith("urn:li:dataset:"):
        consumer = await asyncio.to_thread(context.dh.get_consumer_usage, dataset_urn)
        await _emit_read_finding(
            context,
            urn=dataset_urn,
            check="usage",
            verdict="unknown",
            detail=f"weekly_views={consumer.get('weekly_views')}",
        )
        return _compact_json(consumer)
    raw = await asyncio.to_thread(context.dh.get_usage_stats, dataset_urn)
    aggregations = raw.get("aggregations") or {}
    payload = {
        "urn": dataset_urn,
        "queries_30d": int(aggregations.get("totalSqlQueries") or 0),
        "unique_users": int(aggregations.get("uniqueUserCount") or 0),
        "top_users": [
            {"urn": (item.get("user") or {}).get("urn"), "count": item.get("count")}
            for item in (aggregations.get("users") or [])[:5]
        ],
        "top_fields": [
            {"field": item.get("fieldName"), "count": item.get("count")}
            for item in (aggregations.get("fields") or [])[:5]
        ],
    }
    await _emit_read_finding(
        context,
        urn=dataset_urn,
        check="usage",
        verdict="unknown",
        detail=f"{payload['queries_30d']} queries and {payload['unique_users']} users in 30d",
    )
    return _compact_json(payload)


@function_tool
async def get_owners(ctx: ToolContext[TriageContext], urns: list[str]) -> str:
    """Resolve owners, display names, emails, ownership types, and groups for assets."""

    context = _bump(ctx)

    def read_all() -> list[dict[str, Any]]:
        return [{"urn": urn, "owners": context.dh.get_owners(urn)} for urn in urns[:50]]

    payload = await asyncio.to_thread(read_all)
    await context.emit(MetricEvent(name="owners_assets_read", value=len(payload)))
    return _compact_json({"assets": payload})


@function_tool
async def list_open_incidents(ctx: ToolContext[TriageContext], dataset_urn: str) -> str:
    """List active incidents so the agent does not file a duplicate."""

    context = _bump(ctx)
    incidents = await asyncio.to_thread(context.dh.list_open_incidents, dataset_urn)
    compact = [
        {
            "urn": item.get("urn"),
            "type": item.get("incidentType"),
            "title": item.get("title"),
            "priority": item.get("priority"),
            "stage": (item.get("incidentStatus") or {}).get("stage"),
        }
        for item in incidents[:20]
    ]
    await context.emit(MetricEvent(name="open_incidents_read", value=len(compact)))
    return _compact_json({"urn": dataset_urn, "total": len(compact), "incidents": compact})


@function_tool
async def recall_postmortems(
    ctx: ToolContext[TriageContext], dataset_urn: str, max_hops: int = 3
) -> str:
    """Recall and rank post-mortems stored on this dataset and its ancestors."""

    context = _bump(ctx)
    lineage = await asyncio.to_thread(
        context.dh.get_lineage,
        dataset_urn,
        direction="upstream",
        max_hops=max_hops,
    )
    ancestor_hops = {dataset_urn: 0, **{str(item["urn"]): int(item["hops"]) for item in lineage}}
    indexed = await asyncio.to_thread(context.dh.search_postmortem_datasets)
    urns = list(dict.fromkeys([*ancestor_hops, *(urn for urn in indexed if urn in ancestor_hops)]))

    def read_values() -> list[Mapping[str, Any]]:
        values: list[Mapping[str, Any]] = []
        for urn in urns:
            for raw in context.dh.read_structured_property(urn):
                try:
                    parsed = json.loads(str(raw))
                except (TypeError, json.JSONDecodeError):
                    log.warning("Ignoring non-JSON post-mortem value on %s", urn)
                    continue
                if isinstance(parsed, Mapping) and parsed.get("root_cause_urn") in ancestor_hops:
                    values.append(parsed)
        return values

    candidates = await asyncio.to_thread(read_values)
    ranked = rank_recalled_postmortems(
        candidates,
        ancestor_hops,
        signal_kind=context.trigger.signal_kind,
    )[:3]
    context.recalled = ranked
    if ranked:
        await context.store.increment_reused_count(
            [item.incident_id for item in ranked if item.relevance >= 0]
        )
    tops = [
        RecallTop(
            incident_id=item.incident_id,
            root_cause_name=item.root_cause_name,
            relevance=item.relevance,
            hops_away=item.hops_away,
        )
        for item in ranked
    ]
    await context.emit(RecallEvent(found=len(ranked), top=tops[0] if tops else None, all=tops))
    if not ranked:
        return _compact_json(
            {"found": 0, "message": "No prior post-mortems on this dataset or its ancestors."}
        )
    return _compact_json(
        {"found": len(ranked), "postmortems": [item.model_dump() for item in ranked]}
    )


@function_tool
async def raise_incident(
    ctx: ToolContext[TriageContext],
    dataset_urn: str,
    incident_type: Literal["FRESHNESS", "VOLUME", "FIELD", "SQL", "DATA_SCHEMA", "OPERATIONAL"],
    title: str,
    description_markdown: str,
    priority: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"],
) -> str:
    """Idempotently raise one active DataHub incident on the symptom dataset."""

    context = _bump(ctx)
    try:
        urn = await asyncio.to_thread(
            context.dh.raise_incident,
            dataset_urn,
            incident_type=incident_type,
            title=title,
            description=description_markdown,
            priority=priority,
        )
        context.incident_urn = urn
        context.incident_resource_urn = dataset_urn
        record = ActionRecord(
            action="incident",
            summary=f"Active {priority.lower()} {incident_type.lower()} incident",
            urns=[urn, dataset_urn],
            datahub_url=incident_url_for(dataset_urn),
            detail=title,
        )
    except Exception as exc:
        log.exception("Incident write failed")
        record = ActionRecord(
            action="incident",
            summary="Incident write failed",
            urns=[dataset_urn],
            detail=str(exc),
            ok=False,
        )
    context.actions.append(record)
    await context.emit(ActionEvent(**record.model_dump()))
    return _compact_json(record.model_dump())


@function_tool
async def tag_assets(
    ctx: ToolContext[TriageContext],
    urns: list[str],
    tag: Literal["oncall_root_cause", "oncall_impacted", "oncall_triaged"],
    column_paths: list[str] | None = None,
) -> str:
    """Idempotently tag supported assets and optional positionally matched columns."""

    context = _bump(ctx)
    if column_paths is not None and len(column_paths) != len(urns):
        message = "column_paths must be omitted or have exactly one entry per urn"
        record = ActionRecord(
            action="tag", summary="Tag request rejected", urns=urns, detail=message, ok=False
        )
        context.actions.append(record)
        await context.emit(ActionEvent(**record.model_dump()))
        return _compact_json(record.model_dump())

    def apply_all() -> int:
        display, description, color = TAG_DEFINITIONS[tag]
        context.dh.ensure_tag(tag, display, description, color)
        changed = 0
        for index, urn in enumerate(urns):
            column = column_paths[index] if column_paths is not None else ""
            changed += int(context.dh.apply_tags(urn, [tag], fields=[column] if column else []))
        return changed

    try:
        changed = await asyncio.to_thread(apply_all)
        record = ActionRecord(
            action="tag",
            summary=f"Applied {tag} to {len(urns)} assets ({changed} changed)",
            urns=urns,
            detail=f"column_paths={column_paths or []}",
        )
    except Exception as exc:
        log.exception("Tag write failed")
        record = ActionRecord(
            action="tag", summary="Tag write failed", urns=urns, detail=str(exc), ok=False
        )
    context.actions.append(record)
    await context.emit(ActionEvent(**record.model_dump()))
    return _compact_json(record.model_dump())


def _write_notification_receipt(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


@function_tool
async def notify_owners(
    ctx: ToolContext[TriageContext],
    owner_urns: list[str],
    subject: str,
    body_markdown: str,
) -> str:
    """Notify owners through Slack when configured and always save the exact payload."""

    context = _bump(ctx)
    notification_id = (context.incident_urn or context.run_id).rsplit(":", 1)[-1]
    payload = {
        "run_id": context.run_id,
        "incident_urn": context.incident_urn,
        "owner_urns": list(dict.fromkeys(owner_urns)),
        "subject": subject,
        "body_markdown": body_markdown,
    }
    # Runtime receipts belong under data/ (gitignored). examples/ is a curated, committed set;
    # letting every run write there silently grows the repo with unreviewed artifacts.
    path = _REPOSITORY_ROOT / "data" / "notifications" / f"{notification_id}.json"
    await asyncio.to_thread(_write_notification_receipt, path, payload)
    ok = True
    detail = f"mock receipt: {path.relative_to(_REPOSITORY_ROOT)}"
    webhook = get_settings().slack_webhook_url
    if webhook:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    webhook, json={"text": f"*{subject}*\n{body_markdown}"}
                )
                response.raise_for_status()
            detail = "Slack webhook delivered; exact receipt saved"
        except Exception as exc:
            log.exception("Owner notification webhook failed")
            ok = False
            detail = f"Webhook failed, receipt preserved: {exc}"
    record = ActionRecord(
        action="notify",
        summary=f"Notified {len(payload['owner_urns'])} owners: {subject}",
        urns=payload["owner_urns"],
        detail=f"{detail}\n{body_markdown[:500]}",
        ok=ok,
    )
    context.actions.append(record)
    await context.emit(ActionEvent(**record.model_dump()))
    return _compact_json({**record.model_dump(), "receipt": str(path)})


def _postmortem_markdown(postmortem: PostMortem) -> str:
    path = " → ".join(node.name for node in postmortem.causal_path)
    evidence = "\n".join(f"- {item}" for item in postmortem.evidence)
    impacts = "\n".join(
        f"- {item.severity.upper()}: {item.name} ({item.usage_score} usage score)"
        for item in postmortem.blast_radius
    )
    return (
        f"# {postmortem.title}\n\n"
        f"**Symptom:** {postmortem.symptom}\n\n"
        f"**Root cause:** {postmortem.root_cause_summary}\n\n"
        f"## Causal path\n{path}\n\n"
        f"## Evidence\n{evidence or '- No evidence recorded'}\n\n"
        f"## Blast radius\n{impacts or '- No downstream impacts recorded'}\n\n"
        f"## Human action\n{postmortem.recommended_action}\n\n"
        f"## Prevention\n{postmortem.prevention}\n"
    )


@function_tool
async def write_postmortem(ctx: ToolContext[TriageContext], postmortem: PostMortem) -> str:
    """Persist an authored post-mortem to four DataHub surfaces and SQLite."""

    context = _bump(ctx)
    normalized = postmortem.model_copy(update={"incident_id": context.run_id})
    detected_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    indexed_value = {
        **normalized.model_dump(mode="json"),
        "detected_at": detected_at,
        "check_kind": context.trigger.signal_kind,
    }
    markdown = _postmortem_markdown(normalized)
    result = await asyncio.to_thread(
        context.dh.write_postmortem_artifacts,
        indexed_value,
        markdown_body=markdown,
    )
    urls = result["datahub_urls"]
    await context.store.save_postmortem(
        run_id=context.run_id,
        postmortem=normalized,
        markdown=markdown,
        document_urn=result.get("document_urn"),
        datahub_links=list(urls.values()),
    )
    context.postmortem_id = normalized.incident_id
    context.root_cause_urn = normalized.root_cause_urn
    context.causal_path = normalized.causal_path
    context.blast_radius = normalized.blast_radius
    if context.time_to_root_cause_s is None:
        context.time_to_root_cause_s = round(time.monotonic() - context.started_at, 3)
        await context.emit(
            MetricEvent(name="time_to_root_cause_s", value=context.time_to_root_cause_s)
        )
    await context.emit(CausalPathEvent(nodes=context.causal_path))
    totals = BlastRadiusTotals(
        datasets=sum(item.entity_type == "DATASET" for item in context.blast_radius),
        charts=sum(item.entity_type == "CHART" for item in context.blast_radius),
        dashboards=sum(item.entity_type == "DASHBOARD" for item in context.blast_radius),
        models=sum(item.entity_type == "MLMODEL" for item in context.blast_radius),
    )
    await context.emit(BlastRadiusEvent(items=context.blast_radius, totals=totals))
    await context.emit(
        PostMortemEvent(
            postmortem_id=normalized.incident_id,
            title=normalized.title,
            datahub_urls=PostMortemUrls.model_validate(urls),
        )
    )
    if result.get("errors"):
        await context.emit(
            ErrorEvent(
                message=f"Partial post-mortem write: {result['errors']}",
                where="write_postmortem",
            )
        )
    return _compact_json(result)


@function_tool
async def resolve_incident(
    ctx: ToolContext[TriageContext],
    incident_urn: str,
    stage: Literal["INVESTIGATION", "WORK_IN_PROGRESS", "FIXED", "NO_ACTION_REQUIRED"],
    message: str,
) -> str:
    """Move an incident to a truthful stage without pretending data was fixed."""

    context = _bump(ctx)
    state = "RESOLVED" if stage in {"FIXED", "NO_ACTION_REQUIRED"} else "ACTIVE"
    try:
        ok = await asyncio.to_thread(
            context.dh.update_incident_status,
            incident_urn,
            state=state,
            stage=stage,
            message=message,
        )
        record = ActionRecord(
            action="resolve",
            summary=f"Incident moved to {stage}",
            urns=[incident_urn],
            datahub_url=(
                incident_url_for(context.incident_resource_urn)
                if context.incident_resource_urn
                else None
            ),
            detail=message,
            ok=ok,
        )
    except Exception as exc:
        log.exception("Incident status write failed")
        record = ActionRecord(
            action="resolve",
            summary="Incident status write failed",
            urns=[incident_urn],
            detail=str(exc),
            ok=False,
        )
    context.actions.append(record)
    await context.emit(ActionEvent(**record.model_dump()))
    return _compact_json(record.model_dump())


def _mcp_unavailable(
    ctx: RunContextWrapper[TriageContext], _agent: AgentBase[TriageContext]
) -> bool:
    return not ctx.context.mcp_available


@function_tool(is_enabled=_mcp_unavailable)
async def get_lineage_native(
    ctx: ToolContext[TriageContext],
    urn: str,
    direction: Literal["upstream", "downstream"],
    max_hops: int = 1,
    column: str | None = None,
) -> str:
    """Native lineage fallback exposed only when the DataHub MCP server is unavailable."""

    context = _bump(ctx)
    results = await asyncio.to_thread(
        context.dh.get_lineage,
        urn,
        direction=direction,
        max_hops=max_hops,
        source_column=column,
    )
    compact = results[:50]
    await context.emit(MetricEvent(name="native_lineage_results", value=len(compact)))
    return _compact_json(
        {
            "urn": urn,
            "direction": direction,
            "returned": len(compact),
            "results": compact,
            "truncated": len(results) > len(compact),
        }
    )


NATIVE_TOOLS = [
    set_phase,
    record_finding,
    get_assertion_status,
    get_freshness,
    get_row_count_trend,
    check_schema_drift,
    confirm_no_upstreams,
    get_usage_stats,
    get_owners,
    list_open_incidents,
    recall_postmortems,
    raise_incident,
    tag_assets,
    notify_owners,
    write_postmortem,
    resolve_incident,
    get_lineage_native,
]
