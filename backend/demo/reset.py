"""Heal demo scenarios, remove agent artifacts, or purge the oncall demo namespace."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

from demo.catalog import (
    ASSERTIONS,
    CHARTS,
    DASHBOARDS,
    DATASETS,
    ML_MODEL_URN,
    POSTMORTEM_PROPERTY_URN,
    TAG_NAMES,
    chart_urn,
    dashboard_urn,
)
from demo.common import (
    emit_assertion_result,
    emit_operation,
    emit_profile,
    healthy_assertion_value,
    now_millis,
    upsert_dataset,
)
from demo.seed import verify_seed, wipe_namespace
from oncall_agent.config import get_settings
from oncall_agent.datahub.client import get_client, get_graph, preflight_gms
from oncall_agent.datahub.reads import list_open_incidents
from oncall_agent.datahub.writes import (
    patch_custom_properties,
    read_structured_property,
    remove_tags,
    set_structured_property,
    update_incident_status,
)

TOTAL_STEPS = 6
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_RECEIPT_DIR = _REPOSITORY_ROOT / "data" / "scenarios"


def progress(step: int, message: str) -> None:
    """Print one machine-parseable reset progress line."""

    print(f"STEP {step}/{TOTAL_STEPS} {message}", flush=True)


def _restore_health(event_ms: int) -> None:
    for dataset in DATASETS:
        upsert_dataset(dataset)
        emit_operation(dataset, hours_stale=dataset.sla_hours * 0.2, event_ms=event_ms)
        emit_profile(dataset, row_count=dataset.row_count, event_ms=event_ms)
    for assertion_id, *_ in ASSERTIONS:
        value = healthy_assertion_value(assertion_id)
        emit_assertion_result(
            assertion_id,
            success=True,
            actual_value=value,
            observed=str(int(value)),
            event_ms=event_ms,
        )


def _resolve_and_delete_incidents() -> int:
    graph = get_graph()
    incident_urns: set[str] = set()
    for dataset in DATASETS:
        incident_urns.update(item["urn"] for item in list_open_incidents(dataset.urn))
    for urn in incident_urns:
        update_incident_status(
            urn,
            state="RESOLVED",
            stage="FIXED",
            message="Demo reset restored the healthy baseline",
        )
        graph.hard_delete_entity(urn)
    return len(incident_urns)


def _memory_document_urns() -> set[str]:
    document_urns: set[str] = set()
    for dataset in DATASETS:
        for raw in read_structured_property(dataset.urn, POSTMORTEM_PROPERTY_URN):
            try:
                value = json.loads(str(raw))
            except json.JSONDecodeError:
                continue
            incident_id = value.get("incident_id") or value.get("id")
            if incident_id:
                document_urns.add(f"urn:li:document:oncall-postmortem-{incident_id}")
        entity = get_client().entities.get(dataset.urn)
        for link in entity.links or []:
            prefix = f"{get_settings().frontend_url.rstrip('/')}/memory/"
            if link.url.startswith(prefix):
                incident_id = link.url.removeprefix(prefix).strip("/")
                if incident_id:
                    document_urns.add(f"urn:li:document:oncall-postmortem-{incident_id}")
    return document_urns


def _consumer_urns() -> tuple[str, ...]:
    """Every non-dataset entity the agent is capable of tagging.

    Cleanup scope must match WRITE scope. `tag_assets` tags whatever the blast radius contains —
    charts, dashboards and the ML model included — so a dataset-only reset leaves residue behind
    while still asserting it is clean.
    """

    return (
        *(chart_urn(name) for name, *_ in CHARTS),
        *(dashboard_urn(name) for name, *_ in DASHBOARDS),
        ML_MODEL_URN,
    )


def _remove_agent_artifacts(*, keep_memory: bool) -> tuple[int, int]:
    graph = get_graph()
    documents = _memory_document_urns() if not keep_memory else set()
    tags_removed = 0
    for consumer_urn in _consumer_urns():
        tags_removed += int(remove_tags(consumer_urn, TAG_NAMES))
    for dataset in DATASETS:
        # Column-level tags live on editableSchemaMetadata and are invisible to an entity-level
        # remove_tags, so pass every field explicitly.
        field_paths = tuple(column[0] for column in dataset.columns)
        tags_removed += int(remove_tags(dataset.urn, TAG_NAMES, fields=field_paths))
        entity = get_client().entities.get(dataset.urn)
        if not keep_memory:
            memory_prefix = f"{get_settings().frontend_url.rstrip('/')}/memory/"
            links = [
                link.url for link in (entity.links or []) if link.url.startswith(memory_prefix)
            ]
            if links:
                for url in links:
                    entity.remove_link(url)
                get_client().entities.update(entity)
            set_structured_property(
                dataset.urn,
                [],
                property_urn=POSTMORTEM_PROPERTY_URN,
            )
        removable = {
            key: None
            for key in (entity.custom_properties or {})
            if key.startswith("oncall.") and key != "oncall.freshness_sla_hours"
        }
        if removable:
            patch_custom_properties(dataset.urn, removable)
    for document_urn in documents:
        graph.hard_delete_entity(document_urn)
    return tags_removed, len(documents)


def _truncate_local_store(*, keep_memory: bool) -> None:
    candidates = {
        (_REPOSITORY_ROOT / "backend" / get_settings().db_path).resolve(),
        (_REPOSITORY_ROOT / get_settings().db_path).resolve(),
    }
    for path in candidates:
        if not path.exists():
            continue
        connection = sqlite3.connect(path)
        try:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            # --keep-memory must preserve the RUN MIRROR too, not just post-mortems. The runs are
            # what /api/compare reads, and the UI advertises them as permanent replayable records;
            # wiping them made the documented walkthrough dead-end at "No comparable pair".
            if not keep_memory:
                for table in ("run_events", "runs", "postmortems"):
                    if table in tables:
                        connection.execute(f"DELETE FROM {table}")
            connection.commit()
        finally:
            connection.close()


def _clear_receipts() -> None:
    if not _RECEIPT_DIR.exists():
        return
    for receipt in _RECEIPT_DIR.glob("*.json"):
        receipt.unlink()


def _assert_no_oncall_tags() -> None:
    """Assert no agent-written tag survives, on ANY entity type or column.

    Previously this walked only DATASETS at entity level, so it reported a clean reset while
    `oncall_impacted` persisted on all 4 charts, 3 dashboards and the ML model, and column tags
    persisted on schema fields. An assertion narrower than the writes it guards is worse than none.
    """

    forbidden = {f"urn:li:tag:{name}" for name in TAG_NAMES}
    remaining: dict[str, set[str]] = {}

    for dataset in DATASETS:
        entity = get_client().entities.get(dataset.urn)
        present = {tag.tag for tag in (entity.tags or [])} & forbidden
        if present:
            remaining[dataset.key] = present
        for column in dataset.columns:
            field = column[0]
            field_tags = {tag.tag for tag in (entity[field].tags or [])} & forbidden
            if field_tags:
                remaining[f"{dataset.key}.{field}"] = field_tags

    for consumer_urn in _consumer_urns():
        entity = get_client().entities.get(consumer_urn)
        present = {tag.tag for tag in (entity.tags or [])} & forbidden
        if present:
            remaining[consumer_urn] = present

    if remaining:
        raise AssertionError(f"On-call tags remain after reset: {remaining}")


def reset(*, keep_memory: bool = False, purge: bool = False) -> dict[str, Any]:
    """Reset all mutable demo state; optionally preserve memory or purge entities."""

    if purge:
        progress(1, "purging deterministic oncall demo entities")
        wipe_namespace()
        progress(2, "clearing local scenario receipts")
        _clear_receipts()
        progress(3, "truncating local run and post-mortem rows")
        _truncate_local_store(keep_memory=False)
        progress(4, "incident cleanup included in namespace purge")
        progress(5, "health verification skipped because namespace is purged")
        progress(6, "purge complete")
        return {"purged": True}

    event_ms = now_millis()
    progress(1, "restoring schemas, healthy operations, profiles, and PASS assertions")
    _restore_health(event_ms)
    progress(2, "resolving and hard-deleting active incidents on demo datasets")
    incident_count = _resolve_and_delete_incidents()
    progress(3, f"removing agent tags and artifacts keep_memory={str(keep_memory).lower()}")
    tags_removed, documents_removed = _remove_agent_artifacts(keep_memory=keep_memory)
    progress(4, "clearing scenario receipts and local run state")
    _clear_receipts()
    _truncate_local_store(keep_memory=keep_memory)
    progress(5, "polling DataHub for all-PASS health and asserting tags are absent")
    report = verify_seed()
    _assert_no_oncall_tags()
    progress(6, "reset complete all_datasets=PASS oncall_tags=0")
    result: dict[str, Any] = {
        **report,
        "incidents_removed": incident_count,
        "tagged_datasets_cleaned": tags_removed,
        "documents_removed": documents_removed,
        "memory_preserved": keep_memory,
    }
    print("VERIFY " + " ".join(f"{key}={value}" for key, value in result.items()), flush=True)
    return result


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for ``python -m demo.reset``."""

    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--all", action="store_true", help="fully heal and remove memory (default)")
    modes.add_argument("--keep-memory", action="store_true", help="heal but preserve memory")
    modes.add_argument("--purge", action="store_true", help="hard-delete demo entities")
    args = parser.parse_args(argv)
    try:
        preflight_gms()
        reset(keep_memory=args.keep_memory, purge=args.purge)
    except Exception as exc:
        print(f"ERROR reset_failed={type(exc).__name__} message={exc}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
