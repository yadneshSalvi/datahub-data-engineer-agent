"""Pure recall ranking tests with no DataHub or OpenAI dependency."""

from datetime import UTC, datetime

from oncall_agent.agent.tools_native import rank_recalled_postmortems


def test_same_root_cause_ancestor_beats_unrelated_recent_memory() -> None:
    root = "urn:li:dataset:(urn:li:dataPlatform:oncall,oncall_demo.raw.trips_raw,PROD)"
    unrelated = "urn:li:dataset:(urn:li:dataPlatform:oncall,oncall_demo.raw.drivers_raw,PROD)"
    candidates = [
        {
            "incident_id": "old-related",
            "root_cause_urn": root,
            "root_cause_name": "trips_raw",
            "symptom": "daily rides failed",
            "causal_path": [],
            "evidence": ["stale"],
            "recommended_action": "restart ingestion",
            "detected_at": "2026-07-22T00:00:00Z",
            "check_kind": "assertion",
        },
        {
            "incident_id": "new-unrelated",
            "root_cause_urn": unrelated,
            "root_cause_name": "drivers_raw",
            "symptom": "driver schema failed",
            "causal_path": [],
            "evidence": ["schema drift"],
            "recommended_action": "restore rating",
            "detected_at": "2026-08-01T00:00:00Z",
            "check_kind": "assertion",
        },
    ]
    ranked = rank_recalled_postmortems(
        candidates,
        {root: 3},
        signal_kind="assertion",
        now=datetime(2026, 8, 1, tzinfo=UTC),
    )
    assert ranked[0].incident_id == "old-related"
    assert ranked[0].relevance > ranked[1].relevance


def test_cold_start_ranks_to_empty() -> None:
    assert rank_recalled_postmortems([], {}, signal_kind="freshness") == []
