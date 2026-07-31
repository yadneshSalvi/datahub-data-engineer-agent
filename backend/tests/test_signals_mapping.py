"""Health search and operation freshness mapping with a stubbed GMS."""

from __future__ import annotations

import time

import httpx
import respx

from oncall_agent.datahub.reads import get_health_signals
from oncall_agent.datahub.urns import dataset_urn


def _entity(urn: str, name: str, health: list[dict[str, object]]) -> dict[str, object]:
    return {
        "entity": {
            "urn": urn,
            "name": name,
            "properties": {
                "name": name,
                "description": "fixture",
                "customProperties": [
                    {"key": "seeded_by", "value": "oncall-agent"},
                    {"key": "oncall.freshness_sla_hours", "value": "6"},
                ],
            },
            "health": health,
        }
    }


@respx.mock
def test_assertion_fail_shape_and_freshness_only_breach() -> None:
    fct = dataset_urn("marts.fct_trips")
    raw = dataset_urn("raw.trips_raw")
    assertion = "urn:li:assertion:oncall-fct_trips-rowcount"
    now_ms = int(time.time() * 1000)
    route = respx.post("http://gms.test/api/graphql")
    route.side_effect = [
        httpx.Response(
            200,
            json={
                "data": {
                    "searchAcrossEntities": {
                        "total": 2,
                        "searchResults": [
                            _entity(
                                fct,
                                "oncall_demo.marts.fct_trips",
                                [
                                    {
                                        "type": "INCIDENTS",
                                        "status": "PASS",
                                        "message": None,
                                        "causes": None,
                                    },
                                    {
                                        "type": "ASSERTIONS",
                                        "status": "FAIL",
                                        "message": "1 of 2 assertions are failing",
                                        "causes": [assertion],
                                    },
                                ],
                            ),
                            _entity(
                                raw,
                                "oncall_demo.raw.trips_raw",
                                [
                                    {
                                        "type": "INCIDENTS",
                                        "status": "PASS",
                                        "message": None,
                                        "causes": None,
                                    },
                                    {
                                        "type": "ASSERTIONS",
                                        "status": "PASS",
                                        "message": None,
                                        "causes": None,
                                    },
                                ],
                            ),
                        ],
                    }
                }
            },
        ),
        httpx.Response(
            200,
            json={
                "data": {
                    "dataset": {
                        "operations": [
                            {
                                "timestampMillis": now_ms,
                                "operationType": "INSERT",
                                "lastUpdatedTimestamp": now_ms - 60_000,
                                "numAffectedRows": 0,
                                "actor": "urn:li:corpuser:datahub",
                            }
                        ]
                    }
                }
            },
        ),
        httpx.Response(
            200,
            json={
                "data": {
                    "dataset": {
                        "operations": [
                            {
                                "timestampMillis": now_ms,
                                "operationType": "INSERT",
                                "lastUpdatedTimestamp": now_ms - 26 * 3_600_000,
                                "numAffectedRows": 0,
                                "actor": "urn:li:corpuser:datahub",
                            }
                        ]
                    }
                }
            },
        ),
    ]

    signals = get_health_signals()

    by_name = {item["name"]: item for item in signals}
    assert by_name["fct_trips"]["assertion_urns"] == [assertion]
    assert any(
        item
        == {
            "type": "ASSERTIONS",
            "status": "FAIL",
            "message": "1 of 2 assertions are failing",
            "causes": [assertion],
        }
        for item in by_name["fct_trips"]["health"]
    )
    raw_freshness = by_name["trips_raw"]["freshness"]
    assert 25.9 <= raw_freshness["hours_stale"] <= 26.1
    assert raw_freshness["sla_hours"] == 6
    assert any(item["type"] == "FRESHNESS" for item in by_name["trips_raw"]["health"])
    assert route.call_count == 3
