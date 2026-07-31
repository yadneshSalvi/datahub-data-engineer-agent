"""Opt-in end-to-end tests against the shared local DataHub GMS."""

from __future__ import annotations

from importlib import import_module

import pytest

from demo.reset import reset
from demo.seed import seed
from oncall_agent.datahub.reads import get_assertion_status, get_health_signals
from oncall_agent.datahub.urns import dataset_urn

arm_scenario = import_module("demo.break").arm_scenario

pytestmark = pytest.mark.live


def test_live_seed_break_signals_and_reset() -> None:
    seed(wipe=True, verify=True)
    seed(wipe=False, verify=True)
    arm_scenario("stale_upstream")
    signals = get_health_signals()
    by_name = {signal["name"]: signal for signal in signals}
    assert any(item["type"] == "ASSERTIONS" for item in by_name["fct_trips"]["health"])
    assert 25.5 <= by_name["trips_raw"]["freshness"]["hours_stale"] <= 26.5
    reset()
    assert get_health_signals() == []


def test_live_schema_drift_is_independent() -> None:
    arm_scenario("schema_drift")
    dim_status = get_assertion_status(dataset_urn("marts.dim_driver"))
    rating = next(
        item
        for item in dim_status["assertions"]
        if item["urn"].endswith("dim_driver-rating-notnull")
    )
    assert rating["runEvents"]["runEvents"][0]["result"]["type"] == "FAILURE"
    assert all(signal["name"] != "trips_raw" for signal in get_health_signals())
    reset()
