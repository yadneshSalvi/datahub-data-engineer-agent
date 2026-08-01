"""Serializable event DTOs forming the live-stream and replay contract."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter

from oncall_agent.agent.models import BlastRadiusItem, CausalNode


def utc_now_iso() -> str:
    """Return a millisecond-resolution UTC timestamp ending in ``Z``."""

    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class EventBase(BaseModel):
    """Fields present on every emitted event."""

    model_config = ConfigDict(extra="forbid")

    seq: int = 0
    run_id: str = ""
    ts: str = ""


class TriggerPayload(BaseModel):
    """Trigger fields exposed in the run-start event."""

    model_config = ConfigDict(extra="forbid")

    dataset_urn: str
    name: str
    signal_kind: str
    signal_detail: str


class RunStartedEvent(EventBase):
    """A triage run was accepted and initialized."""

    kind: Literal["run_started"] = "run_started"
    trigger: TriggerPayload
    model: str


class PhaseEvent(EventBase):
    """The agent moved to another playbook phase."""

    kind: Literal["phase"] = "phase"
    phase: str
    note: str
    phase_index: int


class AgentMessageEvent(EventBase):
    """Assistant output from the primary or nested agent."""

    kind: Literal["agent_message"] = "agent_message"
    agent: str
    text: str
    delta: bool = False


class ReasoningEvent(EventBase):
    """A concise model-provided reasoning summary."""

    kind: Literal["reasoning"] = "reasoning"
    agent: str
    summary: str


class ToolCallEvent(EventBase):
    """An SDK or MCP tool invocation."""

    kind: Literal["tool_call"] = "tool_call"
    call_id: str
    tool: str
    origin: Literal["mcp", "native", "subagent"]
    args: dict[str, JsonValue]
    agent: str


class ToolResultEvent(EventBase):
    """A bounded, explicit representation of a tool result."""

    kind: Literal["tool_result"] = "tool_result"
    call_id: str
    tool: str
    ok: bool
    duration_ms: int
    summary: str
    payload: JsonValue | None = None


class RecallTop(BaseModel):
    """The highest-ranked prior incident in a recall event."""

    model_config = ConfigDict(extra="forbid")

    incident_id: str
    root_cause_name: str
    relevance: float
    hops_away: int


class RecallEvent(EventBase):
    """Memory lookup results."""

    kind: Literal["recall"] = "recall"
    found: int
    top: RecallTop | None
    all: list[RecallTop]


class FindingEvent(EventBase):
    """An evidence check lights up one catalog node."""

    kind: Literal["finding"] = "finding"
    urn: str
    name: str
    check: str
    verdict: str
    detail: str


class CausalPathEvent(EventBase):
    """The confirmed symptom-to-root path."""

    kind: Literal["causal_path"] = "causal_path"
    nodes: list[CausalNode]


class BlastRadiusTotals(BaseModel):
    """Counts of impacted assets by supported entity type."""

    model_config = ConfigDict(extra="forbid")

    datasets: int
    charts: int
    dashboards: int
    models: int


class BlastRadiusEvent(EventBase):
    """Ranked downstream impact assessment."""

    kind: Literal["blast_radius"] = "blast_radius"
    items: list[BlastRadiusItem]
    totals: BlastRadiusTotals


class ActionEvent(EventBase):
    """A DataHub write or owner notification outcome."""

    kind: Literal["action"] = "action"
    action: Literal["incident", "tag", "notify", "resolve"]
    summary: str
    urns: list[str]
    datahub_url: str | None = None
    detail: str = ""
    ok: bool = True


class PostMortemUrls(BaseModel):
    """Deep links for the three visible DataHub memory surfaces."""

    model_config = ConfigDict(extra="forbid")

    structured_property: str
    document: str
    link: str


class PostMortemEvent(EventBase):
    """A post-mortem was persisted locally and into DataHub."""

    kind: Literal["postmortem"] = "postmortem"
    postmortem_id: str
    title: str
    datahub_urls: PostMortemUrls


class MetricEvent(EventBase):
    """One named run metric."""

    kind: Literal["metric"] = "metric"
    name: str
    value: int | float | str


class RunMetrics(BaseModel):
    """Metrics attached to the terminal event."""

    model_config = ConfigDict(extra="forbid")

    time_to_root_cause_s: float | None
    tool_calls: int
    hops_walked: int
    recall_used: int


class RunCompletedEvent(EventBase):
    """Terminal event for successful, failed, and invalid runs."""

    kind: Literal["run_completed"] = "run_completed"
    status: Literal["succeeded", "failed", "invalid"]
    summary: str
    metrics: RunMetrics
    duration_s: float


class ErrorEvent(EventBase):
    """A user-visible failure with its stage of origin."""

    kind: Literal["error"] = "error"
    message: str
    where: str


Event = Annotated[
    RunStartedEvent
    | PhaseEvent
    | AgentMessageEvent
    | ReasoningEvent
    | ToolCallEvent
    | ToolResultEvent
    | RecallEvent
    | FindingEvent
    | CausalPathEvent
    | BlastRadiusEvent
    | ActionEvent
    | PostMortemEvent
    | MetricEvent
    | RunCompletedEvent
    | ErrorEvent,
    Field(discriminator="kind"),
]

EVENT_ADAPTER = TypeAdapter(Event)


def event_from_json(value: str) -> Event:
    """Validate an event serialized by the store."""

    return EVENT_ADAPTER.validate_json(value)


def event_from_dict(value: object) -> Event:
    """Validate a Python mapping as one of the event DTOs."""

    return EVENT_ADAPTER.validate_python(value)
