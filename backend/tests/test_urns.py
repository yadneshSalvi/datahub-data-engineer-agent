"""Tests for deterministic namespace and display helpers."""

from __future__ import annotations

import pytest

from oncall_agent.datahub.urns import (
    dataset_urn,
    entity_type_from_urn,
    infer_layer,
    is_our_dataset_urn,
    middle_truncate,
    parse_dataset_urn,
    short_display_name,
)


def test_dataset_urn_round_trip_and_namespace() -> None:
    urn = dataset_urn("marts.fct_trips")
    assert urn == ("urn:li:dataset:(urn:li:dataPlatform:oncall,oncall_demo.marts.fct_trips,PROD)")
    parts = parse_dataset_urn(urn)
    assert (parts.platform, parts.name, parts.env) == (
        "oncall",
        "oncall_demo.marts.fct_trips",
        "PROD",
    )
    assert is_our_dataset_urn(urn)
    assert not is_our_dataset_urn(
        "urn:li:dataset:(urn:li:dataPlatform:repairdemo,repairdemo.fct_trips,PROD)"
    )


def test_layers_names_types_and_middle_truncation() -> None:
    urn = dataset_urn("raw.trips_raw")
    assert infer_layer(urn) == "raw"
    assert infer_layer("oncall_demo.staging.stg_trips") == "staging"
    assert infer_layer("urn:li:chart:(looker,oncall_demo_rides_by_hour)") == "bi"
    assert short_display_name(urn) == "trips_raw"
    assert entity_type_from_urn("urn:li:mlModel:(urn:li:dataPlatform:mlflow,x,PROD)") == "MLMODEL"
    assert middle_truncate("abcdefghijklmnopqrstuvwxyz", 11) == "abcde…vwxyz"
    with pytest.raises(ValueError):
        middle_truncate("abcdef", 2)
