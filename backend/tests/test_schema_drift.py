"""Offline schema-drift detection against fine-grained downstream dependencies."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

import oncall_agent.datahub.reads as reads
from oncall_agent.datahub.urns import dataset_urn


class _Graph:
    def __init__(self, upstream: str, downstream: str, live_columns: list[str]) -> None:
        self.upstream = upstream
        self.downstream = downstream
        self.schema = SimpleNamespace(
            fields=[SimpleNamespace(fieldPath=column) for column in live_columns]
        )
        self.lineage = SimpleNamespace(
            fineGrainedLineages=[
                SimpleNamespace(
                    upstreams=[f"urn:li:schemaField:({upstream},rating)"],
                    downstreams=[f"urn:li:schemaField:({downstream},rating)"],
                )
            ]
        )

    def get_aspect(self, *, entity_urn: str, aspect_type: type[Any]) -> object | None:
        if entity_urn == self.upstream and aspect_type.__name__ == "SchemaMetadataClass":
            return self.schema
        if entity_urn == self.downstream and aspect_type.__name__ == "UpstreamLineageClass":
            return self.lineage
        return None


@pytest.mark.parametrize(
    ("live_columns", "expected_verdict", "expected_missing"),
    [
        (["driver_id", "driver_name"], "broken", ["rating"]),
        (["driver_id", "driver_name", "rating"], "healthy", []),
    ],
)
def test_schema_drift_compares_live_schema_to_downstream_dependency(
    monkeypatch: pytest.MonkeyPatch,
    live_columns: list[str],
    expected_verdict: str,
    expected_missing: list[str],
) -> None:
    upstream = dataset_urn("raw.drivers_raw")
    downstream = dataset_urn("staging.stg_drivers")
    graph = _Graph(upstream, downstream, live_columns)
    monkeypatch.setattr(reads, "get_graph", lambda: graph)
    monkeypatch.setattr(
        reads,
        "get_lineage_native",
        lambda *_args, **_kwargs: [
            {"urn": downstream, "type": "DATASET", "hops": 1, "paths": []}
        ],
    )

    result = reads.get_schema_drift(upstream)

    assert result["verdict"] == expected_verdict
    assert result["missing_columns"] == expected_missing
    assert result["added_columns"] == []
    assert result["dependency_columns"] == ["rating"]
