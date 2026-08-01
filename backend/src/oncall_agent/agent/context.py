"""Per-run dependencies, mutable triage state, and monotonic event emission."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from oncall_agent.agent.events import Event, utc_now_iso
from oncall_agent.agent.models import (
    ActionRecord,
    BlastRadiusItem,
    CausalNode,
    Finding,
    RecalledPostMortem,
    TriggerSpec,
)
from oncall_agent.datahub import reads, writes

if TYPE_CHECKING:
    from oncall_agent.store import Store


class DataHubFacade:
    """Bound facade over Slice 1's verified DataHub read/write functions."""

    get_health_signals = staticmethod(reads.get_health_signals)
    get_assertion_status = staticmethod(reads.get_assertion_status)
    get_freshness = staticmethod(reads.get_freshness)
    get_row_count_trend = staticmethod(reads.get_row_count_trend)
    get_schema_drift = staticmethod(reads.get_schema_drift)
    has_upstream_edges = staticmethod(reads.has_upstream_edges)
    dataset_exists = staticmethod(reads.dataset_exists)
    get_usage_stats = staticmethod(reads.get_usage_stats)
    get_consumer_usage = staticmethod(reads.get_consumer_usage)
    get_owners = staticmethod(reads.get_owners)
    list_open_incidents = staticmethod(reads.list_open_incidents)
    get_lineage = staticmethod(reads.get_lineage_native)
    search_postmortem_datasets = staticmethod(reads.search_postmortem_datasets)
    read_structured_property = staticmethod(writes.read_structured_property)
    raise_incident = staticmethod(writes.raise_incident)
    ensure_tag = staticmethod(writes.ensure_tag)
    apply_tags = staticmethod(writes.apply_tags)
    update_incident_status = staticmethod(writes.update_incident_status)
    write_postmortem_artifacts = staticmethod(writes.write_postmortem_artifacts)


class EventEmitter:
    """Assign per-run sequence numbers and fan events into an asyncio queue."""

    def __init__(self, run_id: str, queue: asyncio.Queue[Event | None] | None = None) -> None:
        self.run_id = run_id
        self.queue = queue or asyncio.Queue()
        self._sequence = 0
        self._events: list[Event] = []
        self._lock = asyncio.Lock()

    @property
    def events(self) -> list[Event]:
        """Return a snapshot of all events in emission order."""

        return list(self._events)

    async def emit(self, event: Event) -> None:
        """Stamp and enqueue an event atomically."""

        async with self._lock:
            self._sequence += 1
            stamped = event.model_copy(
                update={"seq": self._sequence, "run_id": self.run_id, "ts": utc_now_iso()}
            )
            self._events.append(stamped)
            await self.queue.put(stamped)

    async def close(self) -> None:
        """Place the terminal queue sentinel after all events."""

        await self.queue.put(None)


@dataclass(slots=True)
class TriageContext:
    """Dependencies and mutable accumulators shared by every tool in a run."""

    run_id: str
    trigger: TriggerSpec
    emit: Callable[[Event], Awaitable[None]]
    dh: DataHubFacade
    store: Store
    started_at: float
    phase: str = "init"
    findings: list[Finding] = field(default_factory=list)
    causal_path: list[CausalNode] = field(default_factory=list)
    blast_radius: list[BlastRadiusItem] = field(default_factory=list)
    actions: list[ActionRecord] = field(default_factory=list)
    recalled: list[RecalledPostMortem] = field(default_factory=list)
    tool_calls: int = 0
    root_cause_urn: str | None = None
    incident_urn: str | None = None
    incident_resource_urn: str | None = None
    postmortem_id: str | None = None
    time_to_root_cause_s: float | None = None
    mcp_available: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def start(
        cls,
        *,
        run_id: str,
        trigger: TriggerSpec,
        emitter: EventEmitter,
        store: Store,
        dh: DataHubFacade | None = None,
        mcp_available: bool = True,
    ) -> TriageContext:
        """Construct a context using the process monotonic clock."""

        return cls(
            run_id=run_id,
            trigger=trigger,
            emit=emitter.emit,
            dh=dh or DataHubFacade(),
            store=store,
            started_at=time.monotonic(),
            mcp_available=mcp_available,
        )
