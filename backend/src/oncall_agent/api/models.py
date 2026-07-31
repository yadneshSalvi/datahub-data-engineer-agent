"""Pydantic request and response models for every JSON API surface."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from oncall_agent.agent.events import Event


class ApiModel(BaseModel):
    """Strict base for public API models."""

    model_config = ConfigDict(extra="forbid")


class ErrorDetail(ApiModel):
    """Machine-readable API error details."""

    code: str
    message: str
    hint: str | None = None


class ErrorResponse(ApiModel):
    """Uniform error envelope returned for every HTTP failure."""

    error: ErrorDetail


class DataHubHealth(ApiModel):
    """DataHub connectivity and namespace census."""

    status: Literal["up", "down"]
    gms_url: str
    server_version: str | None = None
    seeded_entities: int = 0


class MCPHealth(ApiModel):
    """MCP connection status and advertised read tools."""

    status: Literal["connected", "unavailable"]
    tools: list[str]


class OpenAIHealth(ApiModel):
    """Whether a non-empty OpenAI key is configured."""

    configured: bool


class DatabaseHealth(ApiModel):
    """SQLite mirror location and run count."""

    path: str
    runs: int


class HealthResponse(ApiModel):
    """Overall backend health response."""

    ok: bool
    version: str
    datahub: DataHubHealth
    mcp: MCPHealth
    openai: OpenAIHealth
    db: DatabaseHealth


class ConfigResponse(ApiModel):
    """Non-secret configuration required by the UI."""

    datahub_ui_url: str
    platform: str
    scenarios: list[str]
    agent_model: str


class Owner(ApiModel):
    """Human or group owner attached to a catalog entity."""

    urn: str
    name: str
    email: str | None = None


class Signal(ApiModel):
    """One stable alert-inbox row derived from DataHub health."""

    id: str
    dataset_urn: str
    name: str
    layer: str
    kind: Literal["assertion", "freshness"]
    severity: Literal["critical", "high", "medium"]
    title: str
    detail: str
    assertion_urns: list[str]
    hours_stale: float | None = None
    sla_hours: float | None = None
    owners: list[Owner]
    detected_at: str
    triaged_by_run_id: str | None = None


class SignalsResponse(ApiModel):
    """Alert inbox plus a graceful-degradation flag."""

    degraded: bool
    generated_at: str
    signals: list[Signal]


class RunCreateRequest(ApiModel):
    """Manual or signal-derived triage trigger."""

    dataset_urn: str
    signal_kind: Literal["assertion", "freshness"]
    signal_detail: str | None = None
    assertion_urn: str | None = None


class RunAccepted(ApiModel):
    """Identifier returned after a background run starts."""

    run_id: str


class RunRecord(ApiModel):
    """Expanded SQLite run record used by history, detail, and compare."""

    id: str
    created_at: str
    finished_at: str | None = None
    status: Literal["running", "succeeded", "failed", "cancelled"]
    trigger_urn: str
    trigger_name: str
    signal_kind: str
    signal_detail: str | None = None
    scenario: str | None = None
    root_cause_urn: str | None = None
    root_cause_name: str | None = None
    incident_urn: str | None = None
    postmortem_id: str | None = None
    summary: str | None = None
    duration_s: float | None = None
    time_to_root_cause_s: float | None = None
    tool_calls: int = 0
    hops_walked: int = 0
    recall_used: int = 0
    recalled_ids: list[str] = Field(default_factory=list)
    causal_path: list[JsonValue] = Field(default_factory=list)
    blast_radius: list[JsonValue] = Field(default_factory=list)
    actions: list[JsonValue] = Field(default_factory=list)
    findings: list[JsonValue] = Field(default_factory=list)
    error: str | None = None


class RunEventsResponse(ApiModel):
    """HTTP replay representation for one run."""

    run_id: str
    events: list[Event]


class CancelRunResponse(ApiModel):
    """Cancellation acknowledgement."""

    run_id: str
    status: Literal["cancelling"]


class DemoSeedRequest(ApiModel):
    """Seeder options."""

    wipe: bool = False


class DemoBreakRequest(ApiModel):
    """Scenario arming request."""

    scenario: Literal["stale_upstream", "recall_hit", "schema_drift"]


class DemoResetRequest(ApiModel):
    """Reset and teardown options."""

    keep_memory: bool = False
    purge: bool = False


class DemoJobAccepted(ApiModel):
    """Identifier for an asynchronous demo subprocess."""

    job_id: str


class DemoJobEvent(ApiModel):
    """One replayable demo subprocess progress event."""

    seq: int
    job_id: str
    kind: Literal["progress", "completed", "error"]
    line: str
    step: int | None = None
    total: int | None = None
    returncode: int | None = None


class DemoState(ApiModel):
    """Seed and scenario state used by the command deck."""

    seeded: bool
    entity_count: int
    armed_scenario: str | None = None
    armed_at: str | None = None
    healthy: bool


class GraphOwner(ApiModel):
    """Compact owner shown on a lineage node."""

    urn: str
    name: str


class GraphColumn(ApiModel):
    """One fine-grained upstream-to-downstream column mapping."""

    from_: str = Field(alias="from", serialization_alias="from")
    to: str


class GraphNode(ApiModel):
    """Fully enriched lineage node."""

    id: str
    name: str
    qualified_name: str
    entity_type: Literal["DATASET", "CHART", "DASHBOARD", "MLMODEL"]
    layer: Literal["raw", "staging", "marts", "ml", "bi", "unknown"]
    platform: str
    health: Literal["healthy", "degraded", "broken", "unknown"]
    depth: int
    row_count: int | None = None
    hours_stale: float | None = None
    sla_hours: float | None = None
    queries_30d: int | None = None
    weekly_views: int | None = None
    failing_assertions: int = 0
    total_assertions: int = 0
    owners: list[GraphOwner]
    datahub_url: str


class GraphEdge(ApiModel):
    """Directed lineage edge and its optional column mappings."""

    id: str
    source: str
    target: str
    columns: list[GraphColumn]


class LineageGraphResponse(ApiModel):
    """One-call lineage graph response."""

    nodes: list[GraphNode]
    edges: list[GraphEdge]
    focus_urn: str | None


class PostmortemRecord(ApiModel):
    """Local post-mortem mirror with DataHub links."""

    id: str
    run_id: str
    created_at: str
    title: str
    symptom: str | None = None
    symptom_urn: str | None = None
    root_cause_urn: str
    root_cause_name: str | None = None
    doc_markdown: str
    doc_json: dict[str, JsonValue]
    datahub_document_urn: str | None = None
    datahub_links: list[str]
    reused_count: int = 0
    used_by_runs: list[RunRecord] = Field(default_factory=list)


class TrendPoint(ApiModel):
    """Compact per-run metrics trend point."""

    run_id: str
    created_at: str
    time_to_root_cause_s: float | None
    tool_calls: int
    recall_used: int


class MetricsResponse(ApiModel):
    """Aggregate operational and memory-loop metrics."""

    runs_total: int
    runs_succeeded: int
    avg_time_to_root_cause_s: float | None
    median_tool_calls: float | None
    recall_hit_rate: float
    assets_protected: int
    incidents_filed: int
    postmortems_written: int
    trend: list[TrendPoint]


class MetricDelta(ApiModel):
    """Recall-run change relative to its cold baseline."""

    absolute: float | int | None
    pct: float | None


class CompareDeltas(ApiModel):
    """Delta block for the three memory-loop proof metrics."""

    time_to_root_cause_s: MetricDelta
    tool_calls: MetricDelta
    hops_walked: MetricDelta


class CompareResponse(ApiModel):
    """Cold and recall runs plus recall-minus-cold deltas."""

    a: RunRecord
    b: RunRecord
    deltas: CompareDeltas
