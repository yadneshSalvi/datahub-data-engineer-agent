"""Strict structured models shared by agents, tools, events, and persistence."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    """Base model that rejects fields outside the public contract."""

    model_config = ConfigDict(extra="forbid")


class CausalNode(StrictModel):
    """One evidence-bearing node in the symptom-to-root-cause path."""

    urn: str
    name: str
    hops_from_symptom: int
    verdict: Literal["healthy", "degraded", "broken", "root_cause"]
    evidence: list[str]


class BlastRadiusItem(StrictModel):
    """One downstream asset ranked by operational impact."""

    urn: str
    name: str
    entity_type: Literal["DATASET", "CHART", "DASHBOARD", "MLMODEL"]
    hops: int
    usage_score: int
    owners: list[str]
    severity: Literal["critical", "high", "medium", "low"]


class PostMortem(StrictModel):
    """Strict post-mortem authored by the nested agent."""

    incident_id: str
    title: str
    symptom: str
    symptom_urn: str
    root_cause_urn: str
    root_cause_name: str
    root_cause_summary: str
    causal_path: list[CausalNode]
    evidence: list[str]
    blast_radius: list[BlastRadiusItem]
    recommended_action: str
    prevention: str
    recalled_incident_ids: list[str]
    confidence: Literal["high", "medium", "low"]


class TriggerSpec(StrictModel):
    """Normalized signal that starts one triage run."""

    dataset_urn: str
    name: str
    signal_kind: Literal["assertion", "freshness"]
    signal_detail: str
    assertion_urn: str | None = None


class Finding(StrictModel):
    """A recorded evidence check and its verdict."""

    urn: str
    name: str
    check: Literal["assertion", "freshness", "row_count", "schema", "usage", "query"]
    verdict: Literal["healthy", "degraded", "broken", "unknown"]
    detail: str


class ActionRecord(StrictModel):
    """Outcome of a catalog or notification action."""

    action: Literal["incident", "tag", "notify", "resolve"]
    summary: str
    urns: list[str]
    datahub_url: str | None = None
    detail: str = ""
    ok: bool = True


class RecalledPostMortem(StrictModel):
    """Compact prior incident returned by the recall index."""

    incident_id: str
    root_cause_urn: str
    root_cause_name: str
    symptom: str
    causal_path: list[CausalNode]
    evidence: list[str]
    resolution: str
    detected_at: str
    relevance: float
    hops_away: int


class TriageReport(StrictModel):
    """Structured in-memory summary used to finalize a run record."""

    run_id: str
    status: Literal["succeeded", "failed", "cancelled", "invalid"]
    summary: str
    root_cause_urn: str | None
    root_cause_name: str | None
    incident_urn: str | None
    postmortem_id: str | None
    causal_path: list[CausalNode]
    blast_radius: list[BlastRadiusItem]
    actions: list[ActionRecord]
    findings: list[Finding]
    tool_calls: int
    hops_walked: int
    recall_used: bool
    recalled_ids: list[str]
    time_to_root_cause_s: float | None
    duration_s: float
    error: str | None
