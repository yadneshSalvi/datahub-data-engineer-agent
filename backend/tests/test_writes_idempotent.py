"""Idempotency tests for tags, incidents, and document write helpers."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import httpx
import pytest
import respx

import oncall_agent.datahub.writes as writes
from oncall_agent.datahub.urns import dataset_urn


class FakeEntity:
    """Small SDK entity stand-in for tag mutation tests."""

    def __init__(self) -> None:
        self.tags: list[SimpleNamespace] = []

    def add_tag(self, tag: object) -> None:
        self.tags.append(SimpleNamespace(tag=str(tag)))


class FakeEntities:
    """In-memory entity facade that records effective updates."""

    def __init__(self, entity: FakeEntity) -> None:
        self.entity = entity
        self.updates = 0
        self.upserted: dict[str, object] = {}

    def get(self, _urn: str) -> FakeEntity:
        return self.entity

    def update(self, _entity: FakeEntity) -> None:
        self.updates += 1

    def upsert(self, entity: Any) -> None:
        self.upserted[str(entity.urn)] = entity


class FakeGraph:
    """Aspect store that models deterministic document upserts."""

    def __init__(self) -> None:
        self.entities: dict[str, dict[str, object]] = {}

    def emit(self, proposal: Any) -> None:
        self.entities.setdefault(proposal.entityUrn, {})[type(proposal.aspect).__name__] = (
            proposal.aspect
        )


def test_tag_helpers_are_effectively_idempotent(monkeypatch: Any) -> None:
    entity = FakeEntity()
    entities = FakeEntities(entity)
    client = SimpleNamespace(entities=entities)
    monkeypatch.setattr(writes, "get_client", lambda: client)
    monkeypatch.setattr(writes, "dataset_exists", lambda _urn: True)

    writes.ensure_tag("oncall_impacted", "Impacted", "desc", "#F59E0B")
    writes.ensure_tag("oncall_impacted", "Impacted", "desc", "#F59E0B")
    assert len(entities.upserted) == 1

    urn = dataset_urn("marts.fct_trips")
    assert writes.apply_tags(urn, ["oncall_impacted"])
    assert not writes.apply_tags(urn, ["oncall_impacted"])
    assert entities.updates == 1
    assert len(entity.tags) == 1


@respx.mock
def test_raise_incident_reuses_the_first_artifact(monkeypatch: Any) -> None:
    writes._incident_cache.clear()
    monkeypatch.setattr(writes, "dataset_exists", lambda _urn: True)
    resource = dataset_urn("marts.fct_trips")
    incident = "urn:li:incident:stable-fixture"
    route = respx.post("http://gms.test/api/graphql")
    route.side_effect = [
        httpx.Response(
            200,
            json={"data": {"dataset": {"incidents": {"total": 0, "incidents": []}}}},
        ),
        httpx.Response(200, json={"data": {"raiseIncident": incident}}),
    ]
    kwargs = {
        "incident_type": "FRESHNESS",
        "title": "stale trips",
        "description": "fixture",
    }
    assert writes.raise_incident(resource, **kwargs) == incident
    assert writes.raise_incident(resource, **kwargs) == incident
    assert route.call_count == 2


def test_dataset_writes_refuse_nonexistent_targets(monkeypatch: Any) -> None:
    missing = dataset_urn("raw.ghost")
    monkeypatch.setattr(writes, "dataset_exists", lambda _urn: False)

    with pytest.raises(ValueError, match="does not exist"):
        writes.apply_tags(missing, ["oncall_impacted"])
    with pytest.raises(ValueError, match="does not exist"):
        writes.raise_incident(
            missing,
            incident_type="FRESHNESS",
            title="ghost",
            description="must not materialize",
        )


def test_document_urn_is_deterministic(monkeypatch: Any) -> None:
    graph = FakeGraph()
    monkeypatch.setattr(writes, "get_graph", lambda: graph)
    root = dataset_urn("raw.trips_raw")
    symptom = dataset_urn("marts.fct_trips")
    kwargs = {
        "incident_id": "inc-001",
        "title": "Trips stalled",
        "markdown_body": "# Post-mortem",
        "root_cause_urn": root,
        "symptom_urn": symptom,
        "timestamp_ms": 123,
    }
    first = writes.write_document(**kwargs)
    second = writes.write_document(**kwargs)
    assert first == second == "urn:li:document:oncall-postmortem-inc-001"
    assert list(graph.entities) == [first]
    assert len(graph.entities[first]) == 2
