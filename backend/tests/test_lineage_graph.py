"""Lineage assembly tests, including depth signs and a deduplicated diamond."""

from __future__ import annotations

import httpx
import respx

from oncall_agent.datahub.reads import get_lineage_graph
from oncall_agent.datahub.urns import dataset_urn


def _result(urn: str, degree: int, path: list[str]) -> dict[str, object]:
    return {
        "degree": str(degree),
        "entity": {"urn": urn, "type": "DATASET"},
        "paths": [{"path": [{"urn": item, "type": "DATASET"} for item in path]}],
    }


@respx.mock
def test_lineage_layers_depths_and_diamond_deduplication() -> None:
    focus = dataset_urn("staging.stg_trips")
    raw = dataset_urn("raw.trips_raw")
    fct_trips = dataset_urn("marts.fct_trips")
    payments = dataset_urn("staging.stg_payments")
    revenue = dataset_urn("marts.fct_revenue")
    route = respx.post("http://gms.test/api/graphql")
    route.side_effect = [
        httpx.Response(
            200,
            json={
                "data": {
                    "searchAcrossLineage": {
                        "total": 1,
                        "searchResults": [_result(raw, 1, [focus, raw])],
                    }
                }
            },
        ),
        httpx.Response(
            200,
            json={
                "data": {
                    "searchAcrossLineage": {
                        "total": 4,
                        "searchResults": [
                            _result(fct_trips, 1, [focus, fct_trips]),
                            _result(revenue, 2, [focus, fct_trips, revenue]),
                            _result(payments, 1, [focus, payments]),
                            _result(revenue, 2, [focus, payments, revenue]),
                        ],
                    }
                }
            },
        ),
    ]

    graph = get_lineage_graph(focus)

    nodes = {node["id"]: node for node in graph["nodes"]}
    assert nodes[raw]["depth"] == -1
    assert nodes[raw]["layer"] == "raw"
    assert nodes[focus]["depth"] == 0
    assert nodes[focus]["layer"] == "staging"
    assert nodes[revenue]["depth"] == 2
    assert nodes[revenue]["layer"] == "marts"
    assert [node["id"] for node in graph["nodes"]].count(revenue) == 1
    edge_pairs = {(edge["source"], edge["target"]) for edge in graph["edges"]}
    assert (raw, focus) in edge_pairs
    assert (fct_trips, revenue) in edge_pairs
    assert (payments, revenue) in edge_pairs
    assert route.call_count == 2
