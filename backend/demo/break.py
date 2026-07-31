"""Arm one deterministic RideFlow warehouse breakage scenario."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import datahub.metadata.schema_classes as models
from datahub.emitter.mcp import MetadataChangeProposalWrapper

from demo.catalog import ASSERTIONS, DATASET_BY_KEY, DATASETS
from demo.common import (
    emit_assertion_result,
    emit_operation,
    emit_profile,
    healthy_assertion_value,
    now_millis,
    upsert_dataset,
)
from oncall_agent.datahub.client import get_graph
from oncall_agent.datahub.reads import (
    get_assertion_status,
    get_freshness,
    get_health_signals,
)
from oncall_agent.datahub.writes import read_structured_property

SCENARIOS = ("stale_upstream", "recall_hit", "schema_drift")
TOTAL_STEPS = 4
_RECEIPT_DIR = Path(__file__).resolve().parents[2] / "data" / "scenarios"


def progress(step: int, message: str) -> None:
    """Print one machine-parseable scenario progress line."""

    print(f"STEP {step}/{TOTAL_STEPS} {message}", flush=True)


def _baseline(
    event_ms: int,
    *,
    skip_datasets: frozenset[str] = frozenset(),
    skip_assertions: frozenset[str] = frozenset(),
) -> None:
    """Restore healthy timeseries points, skipping whatever the scenario is about to override.

    Emitting a healthy point and then a broken point for the SAME (entity, aspect) in one run is
    a race: the REST sink batches asynchronously and the two writes can be coalesced, which
    intermittently leaves the healthy value winning and the scenario silently un-armed. Separating
    the timestamps is not sufficient — the only reliable fix is to write each series once.
    """

    for dataset in DATASETS:
        if dataset.key == "raw.drivers_raw":
            upsert_dataset(dataset)
        if dataset.key in skip_datasets:
            continue
        emit_operation(dataset, hours_stale=dataset.sla_hours * 0.2, event_ms=event_ms)
        emit_profile(dataset, row_count=dataset.row_count, event_ms=event_ms)
    for assertion_id, *_ in ASSERTIONS:
        if assertion_id in skip_assertions:
            continue
        value = healthy_assertion_value(assertion_id)
        emit_assertion_result(
            assertion_id,
            success=True,
            actual_value=value,
            observed=str(int(value)),
            event_ms=event_ms,
        )


# Datasets and assertions each scenario rewrites — the baseline must not touch these.
_SCENARIO_OVERRIDES: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    "stale_upstream": (
        frozenset(
            {"raw.trips_raw", "staging.stg_trips", "marts.fct_trips", "marts.agg_daily_rides"}
        ),
        frozenset({
            "oncall-stg_trips-rowcount",
            "oncall-fct_trips-rowcount",
            "oncall-agg_daily_rides-rowcount",
        }),
    ),
    "recall_hit": (
        frozenset(
            {"raw.trips_raw", "staging.stg_trips", "marts.fct_trips", "marts.agg_zone_demand"}
        ),
        frozenset({
            "oncall-stg_trips-rowcount",
            "oncall-fct_trips-rowcount",
            "oncall-agg_zone_demand-rowcount",
        }),
    ),
    "schema_drift": (
        frozenset({"raw.drivers_raw", "staging.stg_drivers", "marts.dim_driver"}),
        frozenset({"oncall-dim_driver-rating-notnull"}),
    ),
}


def _fresh(spec: Any, event_ms: int, *, row_count: int | None = None) -> None:
    """Emit a healthy operation (and optionally a profile) for a scenario-owned dataset.

    Scenario-owned datasets are excluded from the baseline, so anything the scenario does not
    itself restate would keep an ever-ageing ``lastUpdatedTimestamp`` and eventually read as a
    spurious freshness breach.
    """

    emit_operation(spec, hours_stale=spec.sla_hours * 0.2, event_ms=event_ms)
    if row_count is not None:
        emit_profile(spec, row_count=row_count, event_ms=event_ms)


def _fail(assertion_id: str, observed: int, event_ms: int) -> None:
    emit_assertion_result(
        assertion_id,
        success=False,
        actual_value=float(observed),
        observed=str(observed),
        event_ms=event_ms,
    )


def _stale_upstream(event_ms: int) -> list[dict[str, Any]]:
    trips_raw = DATASET_BY_KEY["raw.trips_raw"]
    stg_trips = DATASET_BY_KEY["staging.stg_trips"]
    fct_trips = DATASET_BY_KEY["marts.fct_trips"]
    daily = DATASET_BY_KEY["marts.agg_daily_rides"]
    # trips_raw is STALE but not empty — the row count is unchanged, which is what makes this
    # subtler than an obviously-broken table and forces a real lineage walk.
    emit_operation(trips_raw, hours_stale=26, event_ms=event_ms)
    emit_profile(trips_raw, row_count=trips_raw.row_count, event_ms=event_ms)
    emit_operation(stg_trips, hours_stale=25, event_ms=event_ms)
    emit_profile(stg_trips, row_count=3_120, event_ms=event_ms)
    # fct_trips and agg_daily_rides DID run on time; they just processed almost no rows.
    _fresh(fct_trips, event_ms, row_count=3_120)
    _fresh(daily, event_ms, row_count=4)
    _fail("oncall-stg_trips-rowcount", 3_120, event_ms)
    _fail("oncall-fct_trips-rowcount", 3_120, event_ms)
    _fail("oncall-agg_daily_rides-rowcount", 4, event_ms)
    return [
        {"dataset": trips_raw.urn, "freshness_hours": 26},
        {"dataset": stg_trips.urn, "freshness_hours": 25, "row_count": 3120},
        {"dataset": fct_trips.urn, "row_count": 3120},
        {"dataset": daily.urn, "row_count": 4},
    ]


def _recall_hit(event_ms: int) -> list[dict[str, Any]]:
    trips_raw = DATASET_BY_KEY["raw.trips_raw"]
    stg_trips = DATASET_BY_KEY["staging.stg_trips"]
    fct_trips = DATASET_BY_KEY["marts.fct_trips"]
    demand = DATASET_BY_KEY["marts.agg_zone_demand"]
    emit_operation(trips_raw, hours_stale=31, event_ms=event_ms)
    emit_profile(trips_raw, row_count=trips_raw.row_count, event_ms=event_ms)
    emit_operation(stg_trips, hours_stale=30, event_ms=event_ms)
    emit_profile(stg_trips, row_count=3_120, event_ms=event_ms)
    _fresh(fct_trips, event_ms, row_count=3_120)
    _fresh(demand, event_ms, row_count=90)
    _fail("oncall-stg_trips-rowcount", 3_120, event_ms)
    _fail("oncall-fct_trips-rowcount", 3_120, event_ms)
    _fail("oncall-agg_zone_demand-rowcount", 90, event_ms)
    return [
        {"dataset": trips_raw.urn, "freshness_hours": 31},
        {"dataset": stg_trips.urn, "freshness_hours": 30, "row_count": 3120},
        {"dataset": fct_trips.urn, "row_count": 3120},
        {"dataset": demand.urn, "row_count": 90},
    ]


def _schema_drift(event_ms: int) -> list[dict[str, Any]]:
    drivers = DATASET_BY_KEY["raw.drivers_raw"]
    stg_drivers = DATASET_BY_KEY["staging.stg_drivers"]
    dim_driver = DATASET_BY_KEY["marts.dim_driver"]
    columns_without_rating = tuple(column for column in drivers.columns if column[0] != "rating")
    upsert_dataset(drivers, columns=columns_without_rating)
    # drivers_raw is FRESH — the failure is schema drift, not staleness. The agent must not
    # reach for the previous scenario's culprit.
    _fresh(drivers, event_ms, row_count=drivers.row_count)
    _fresh(dim_driver, event_ms, row_count=dim_driver.row_count)
    emit_operation(stg_drivers, hours_stale=stg_drivers.sla_hours * 0.2, event_ms=event_ms)
    get_graph().emit(
        MetadataChangeProposalWrapper(
            entityUrn=stg_drivers.urn,
            aspect=models.DatasetProfileClass(
                timestampMillis=event_ms,
                rowCount=stg_drivers.row_count,
                columnCount=len(stg_drivers.columns),
                sizeInBytes=stg_drivers.row_count * len(stg_drivers.columns) * 16,
                fieldProfiles=[
                    models.DatasetFieldProfileClass(
                        fieldPath="rating",
                        nullCount=stg_drivers.row_count,
                        nullProportion=1.0,
                    )
                ],
            ),
        )
    )
    _fail("oncall-dim_driver-rating-notnull", dim_driver.row_count, event_ms)
    return [
        {"dataset": drivers.urn, "removed_column": "rating"},
        {"dataset": stg_drivers.urn, "rating_null_count": stg_drivers.row_count},
        {"dataset": dim_driver.urn, "rating_null_count": dim_driver.row_count},
    ]


def _write_receipt(scenario: str, event_ms: int, changes: list[dict[str, Any]]) -> Path:
    _RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
    for existing in _RECEIPT_DIR.glob("*.json"):
        existing.unlink()
    path = _RECEIPT_DIR / f"{scenario}.json"
    path.write_text(
        json.dumps(
            {"scenario": scenario, "armed_at_ms": event_ms, "changes": changes},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


_EXPECTED_FAILURES: dict[str, tuple[str, ...]] = {
    "stale_upstream": (
        "oncall-stg_trips-rowcount",
        "oncall-fct_trips-rowcount",
        "oncall-agg_daily_rides-rowcount",
    ),
    "recall_hit": (
        "oncall-stg_trips-rowcount",
        "oncall-fct_trips-rowcount",
        "oncall-agg_zone_demand-rowcount",
    ),
    "schema_drift": ("oncall-dim_driver-rating-notnull",),
}

# Datasets that must be reported unhealthy once the scenario is fully armed. Anything else
# reporting unhealthy means the PREVIOUS scenario's damage has not finished clearing.
_EXPECTED_UNHEALTHY: dict[str, frozenset[str]] = {
    "stale_upstream": frozenset({"trips_raw", "stg_trips", "fct_trips", "agg_daily_rides"}),
    "recall_hit": frozenset({"trips_raw", "stg_trips", "fct_trips", "agg_zone_demand"}),
    "schema_drift": frozenset({"dim_driver"}),
}


def _wait_until_indexed(scenario: str, event_ms: int, timeout_seconds: float = 120.0) -> None:
    """Block until the scenario's own failures AND the restored baseline are both query-visible.

    Waiting only for the new failures is not enough: arming a scenario also restores every other
    dataset, and those healthy points index independently. Returning early leaves the previous
    scenario's damage visible in the signal feed.
    """

    expected = _EXPECTED_FAILURES[scenario]
    expected_unhealthy = _EXPECTED_UNHEALTHY[scenario]
    deadline = time.monotonic() + timeout_seconds
    last_extra: set[str] = set()
    while time.monotonic() < deadline:
        all_failed = True
        for assertion_id in expected:
            dataset_key = next(item[1] for item in ASSERTIONS if item[0] == assertion_id)
            status = get_assertion_status(DATASET_BY_KEY[dataset_key].urn)
            assertion = next(
                (item for item in status["assertions"] if item["urn"].endswith(assertion_id)),
                None,
            )
            runs = (assertion or {}).get("runEvents", {}).get("runEvents", [])
            latest = max(runs, key=lambda item: int(item["timestampMillis"]), default=None)
            if (
                latest is None
                or int(latest["timestampMillis"]) < event_ms
                or (latest.get("result") or {}).get("type") != "FAILURE"
            ):
                all_failed = False
                break
        if all_failed:
            if scenario in {"stale_upstream", "recall_hit"}:
                raw = DATASET_BY_KEY["raw.trips_raw"]
                if not get_freshness(raw.urn, sla_hours=raw.sla_hours)["breached"]:
                    time.sleep(2)
                    continue
            unhealthy = {signal["name"] for signal in get_health_signals()}
            last_extra = unhealthy - expected_unhealthy
            if not last_extra and expected_unhealthy <= unhealthy:
                return
        time.sleep(2)
    raise TimeoutError(
        f"Scenario did not become query-visible before timeout: {scenario} "
        f"(stale signals still present: {sorted(last_extra) or 'none'})"
    )


def arm_scenario(scenario: str) -> Path:
    """Restore a healthy baseline, apply one scenario, and write its receipt."""

    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown scenario: {scenario}")
    if scenario == "recall_hit" and not read_structured_property(
        DATASET_BY_KEY["raw.trips_raw"].urn
    ):
        raise RuntimeError(
            "recall_hit requires a prior trips_raw post-mortem; run stale_upstream triage first"
        )
    event_ms = now_millis()
    skip_datasets, skip_assertions = _SCENARIO_OVERRIDES[scenario]
    progress(1, f"restoring healthy baseline before arming {scenario}")
    # Baseline and scenario share one timestamp on purpose. The skip sets make the two write
    # disjoint series, so they cannot collide — and back-dating the baseline would let it land
    # OLDER than the previous scenario's damage, which then wins the max(timestampMillis) pick
    # and leaves stale failures in the signal feed.
    _baseline(event_ms, skip_datasets=skip_datasets, skip_assertions=skip_assertions)
    progress(2, f"applying deterministic mutations for {scenario}")
    changes = {
        "stale_upstream": _stale_upstream,
        "recall_hit": _recall_hit,
        "schema_drift": _schema_drift,
    }[scenario](event_ms)
    progress(3, f"writing scenario receipt with {len(changes)} changed assets")
    receipt = _write_receipt(scenario, event_ms, changes)
    _wait_until_indexed(scenario, event_ms)
    progress(4, f"scenario armed and indexed name={scenario} receipt={receipt}")
    return receipt


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for ``python -m demo.break``."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=SCENARIOS, required=True)
    args = parser.parse_args(argv)
    try:
        arm_scenario(args.scenario)
    except Exception as exc:
        print(f"ERROR break_failed={type(exc).__name__} message={exc}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
