"""Idempotently seed and verify the RideFlow demo warehouse in DataHub."""

# ruff: noqa: E402 -- warning filters must be installed before importing datahub.sdk.

from __future__ import annotations

import argparse
import sys
import time
import warnings

import datahub.emitter.mce_builder as builder
import datahub.metadata.schema_classes as models
from datahub.emitter.mcp import MetadataChangeProposalWrapper
from datahub.errors import ExperimentalWarning, IngestionAttributionWarning

warnings.filterwarnings("ignore", category=ExperimentalWarning)
warnings.filterwarnings("ignore", category=IngestionAttributionWarning)

from datahub.sdk import Chart, Dashboard, MLModel

from demo.catalog import (
    ASSERTIONS,
    CHARTS,
    DASHBOARDS,
    DATASETS,
    DOMAIN_URN,
    GROUPS,
    LINEAGE,
    ML_FEATURE_URN,
    ML_MODEL_ID,
    ML_MODEL_URN,
    PEOPLE,
    POSTMORTEM_PROPERTY_URN,
    QUERY_SPECS,
    TAG_NAMES,
    chart_urn,
    dashboard_urn,
)
from demo.common import (
    ACTOR_URN,
    emit_assertion_definition,
    emit_assertion_result,
    emit_operation,
    emit_profile,
    emit_usage,
    healthy_assertion_value,
    now_millis,
    upsert_dataset,
)
from oncall_agent.config import get_settings
from oncall_agent.datahub.client import execute_graphql, get_client, get_graph
from oncall_agent.datahub.reads import (
    ASSERTION_STATUS_QUERY,
    HEALTH_SIGNALS_QUERY,
    _search_input,
    get_freshness,
)
from oncall_agent.datahub.writes import ensure_structured_property_definition, ensure_tag

TOTAL_STEPS = 11


def progress(step: int, message: str) -> None:
    """Print one machine-parseable seeding progress line."""

    print(f"STEP {step}/{TOTAL_STEPS} {message}", flush=True)


def _seed_platform_people_domain() -> None:
    graph = get_graph()
    graph.emit(
        MetadataChangeProposalWrapper(
            entityUrn=builder.make_data_platform_urn(get_settings().platform),
            aspect=models.DataPlatformInfoClass(
                name="oncall",
                displayName="OnCall Demo Warehouse",
                type="RELATIONAL_DB",
                datasetNameDelimiter=".",
            ),
        )
    )
    for person in PEOPLE:
        graph.emit(
            MetadataChangeProposalWrapper(
                entityUrn=person.urn,
                aspect=models.CorpUserInfoClass(
                    active=True,
                    displayName=person.display_name,
                    email=person.email,
                    title=person.title,
                    fullName=person.display_name,
                ),
            )
        )
    for group in GROUPS:
        graph.emit(
            MetadataChangeProposalWrapper(
                entityUrn=f"urn:li:corpGroup:{group}",
                aspect=models.CorpGroupInfoClass(
                    admins=[],
                    members=[],
                    groups=[],
                    displayName=group.replace("-", " ").title(),
                    description=f"RideFlow {group} team",
                ),
            )
        )
    graph.emit(
        MetadataChangeProposalWrapper(
            entityUrn=DOMAIN_URN,
            aspect=models.DomainPropertiesClass(
                name="RideFlow Analytics",
                description="Warehouse, BI, and ML assets for the RideFlow on-call demo",
            ),
        )
    )


def _seed_tags_and_property() -> None:
    ensure_tag(
        "oncall_root_cause",
        "On-Call: Root Cause",
        "Localized root cause of an active incident",
        "#EF4444",
    )
    ensure_tag(
        "oncall_impacted",
        "On-Call: Impacted",
        "Downstream asset inside an active blast radius",
        "#F59E0B",
    )
    ensure_tag(
        "oncall_triaged",
        "On-Call: Triaged",
        "An agent has completed triage on this asset",
        "#10B981",
    )
    ensure_structured_property_definition(property_urn=POSTMORTEM_PROPERTY_URN)


def _seed_lineage() -> None:
    client = get_client()
    graph = get_graph()
    for edge in LINEAGE:
        upstream = next(dataset for dataset in DATASETS if dataset.key == edge.upstream)
        downstream = next(dataset for dataset in DATASETS if dataset.key == edge.downstream)
        client.lineage.add_lineage(
            upstream=upstream.urn,
            downstream=downstream.urn,
            column_lineage=edge.columns,
            transformation_text=edge.transformation,
        )
        aspect = graph.get_aspect(
            entity_urn=downstream.urn,
            aspect_type=models.UpstreamLineageClass,
        )
        if aspect is None or upstream.urn not in {item.dataset for item in aspect.upstreams}:
            raise RuntimeError(
                f"Lineage edge was not persisted: {edge.upstream} -> {edge.downstream}"
            )


def _seed_consumers() -> None:
    client = get_client()
    for name, display, input_key, weekly_views in CHARTS:
        input_dataset = next(dataset for dataset in DATASETS if dataset.key == input_key)
        client.entities.upsert(
            Chart(
                name=name,
                platform="looker",
                display_name=display,
                description=f"RideFlow demo chart: {display}",
                chart_url=f"{get_settings().frontend_url}/demo/charts/{name}",
                custom_properties={
                    "seeded_by": "oncall-agent",
                    "weekly_views": str(weekly_views),
                },
                input_datasets=[input_dataset.urn],
            )
        )
    for name, display, chart_names, weekly_views, owner, group in DASHBOARDS:
        client.entities.upsert(
            Dashboard(
                name=name,
                platform="looker",
                display_name=display,
                description=f"RideFlow demo dashboard: {display}",
                dashboard_url=f"{get_settings().frontend_url}/demo/dashboards/{name}",
                custom_properties={
                    "seeded_by": "oncall-agent",
                    "weekly_views": str(weekly_views),
                },
                charts=[chart_urn(chart_name) for chart_name in chart_names],
                owners=[
                    (f"urn:li:corpuser:{owner}", models.OwnershipTypeClass.TECHNICAL_OWNER),
                    (f"urn:li:corpGroup:{group}", models.OwnershipTypeClass.DATAOWNER),
                ],
            )
        )
    client.entities.upsert(
        MLModel(
            id=ML_MODEL_ID,
            platform="mlflow",
            version="3.2.0",
            env="PROD",
            name="ETA Predictor v3",
            description="RideFlow production ETA prediction model",
            custom_properties={
                "seeded_by": "oncall-agent",
                "serving_qps": "240",
                "weekly_views": "0",
            },
            owners=[
                (
                    "urn:li:corpuser:nina.alvarez",
                    models.OwnershipTypeClass.TECHNICAL_OWNER,
                ),
                ("urn:li:corpGroup:ml-platform", models.OwnershipTypeClass.DATAOWNER),
            ],
        )
    )
    graph = get_graph()
    features = next(dataset for dataset in DATASETS if dataset.key == "ml.trip_eta_features")
    graph.emit(
        MetadataChangeProposalWrapper(
            entityUrn=ML_FEATURE_URN,
            aspect=models.MLFeaturePropertiesClass(
                description="ETA predictor training feature set",
                dataType=models.MLFeatureDataTypeClass.UNKNOWN,
                sources=[features.urn],
                customProperties={"seeded_by": "oncall-agent"},
            ),
        )
    )
    properties = graph.get_aspect(
        entity_urn=ML_MODEL_URN,
        aspect_type=models.MLModelPropertiesClass,
    )
    if properties is None:
        raise RuntimeError("ML model properties were not persisted")
    properties.mlFeatures = [ML_FEATURE_URN]
    graph.emit(MetadataChangeProposalWrapper(entityUrn=ML_MODEL_URN, aspect=properties))


def _seed_queries(event_ms: int) -> None:
    audit = models.AuditStampClass(time=event_ms, actor=ACTOR_URN)
    graph = get_graph()
    for suffix, name, dataset_key, source, sql in QUERY_SPECS:
        dataset = next(item for item in DATASETS if item.key == dataset_key)
        query_urn = f"urn:li:query:oncall-q-{suffix}"
        graph.emit(
            MetadataChangeProposalWrapper(
                entityUrn=query_urn,
                aspect=models.QueryPropertiesClass(
                    statement=models.QueryStatementClass(
                        value=sql,
                        language=models.QueryLanguageClass.SQL,
                    ),
                    source=getattr(models.QuerySourceClass, source),
                    created=audit,
                    lastModified=audit,
                    name=name,
                    description=f"Seeded query evidence for {dataset.key}",
                ),
            )
        )
        graph.emit(
            MetadataChangeProposalWrapper(
                entityUrn=query_urn,
                aspect=models.QuerySubjectsClass(
                    subjects=[
                        models.QuerySubjectClass(entity=dataset.urn),
                        models.QuerySubjectClass(
                            entity=builder.make_schema_field_urn(
                                dataset.urn,
                                dataset.columns[0][0],
                            )
                        ),
                    ]
                ),
            )
        )


def _seed_assertions(event_ms: int) -> None:
    for assertion_id, *_ in ASSERTIONS:
        emit_assertion_definition(assertion_id)
        value = healthy_assertion_value(assertion_id)
        emit_assertion_result(
            assertion_id,
            success=True,
            actual_value=value,
            observed=str(int(value)),
            event_ms=event_ms,
        )


def _known_entity_urns() -> list[str]:
    urns = [assertion_urn for assertion_urn, *_ in ASSERTIONS]
    urns = [builder.make_assertion_urn(value) for value in urns]
    urns.extend(f"urn:li:query:oncall-q-{suffix}" for suffix, *_ in QUERY_SPECS)
    urns.append(ML_MODEL_URN)
    urns.append(ML_FEATURE_URN)
    urns.append(
        builder.make_data_job_urn(
            "oncall", "oncall_demo_eta_training", "oncall_demo_train_eta", "PROD"
        )
    )
    urns.append(builder.make_data_flow_urn("oncall", "oncall_demo_eta_training", "PROD"))
    urns.extend(dashboard_urn(name) for name, *_ in DASHBOARDS)
    urns.extend(chart_urn(name) for name, *_ in CHARTS)
    urns.extend(dataset.urn for dataset in DATASETS)
    urns.extend(builder.make_tag_urn(name) for name in TAG_NAMES)
    urns.extend(
        [
            POSTMORTEM_PROPERTY_URN,
            DOMAIN_URN,
            builder.make_data_platform_urn(get_settings().platform),
        ]
    )
    return urns


def wipe_namespace() -> None:
    """Hard-delete every deterministic demo entity, plus incidents attached to demo datasets."""

    from oncall_agent.datahub.reads import list_open_incidents

    graph = get_graph()
    for dataset in DATASETS:
        for incident in list_open_incidents(dataset.urn):
            graph.hard_delete_entity(incident["urn"])
    for urn in _known_entity_urns():
        get_client().entities.delete(urn, check_exists=False, hard=True)


def _assert_latest_results_passing() -> int:
    passing = 0
    seen: set[str] = set()
    for _assertion_id, dataset_key, *_ in ASSERTIONS:
        dataset = next(item for item in DATASETS if item.key == dataset_key)
        data = execute_graphql(ASSERTION_STATUS_QUERY, {"urn": dataset.urn})
        attached = ((data.get("dataset") or {}).get("assertions") or {}).get("assertions") or []
        for assertion in attached:
            urn = assertion["urn"]
            if urn in seen or not urn.startswith("urn:li:assertion:oncall-"):
                continue
            seen.add(urn)
            runs = (assertion.get("runEvents") or {}).get("runEvents") or []
            latest = max(runs, key=lambda item: int(item["timestampMillis"]), default=None)
            if latest and (latest.get("result") or {}).get("type") == "SUCCESS":
                passing += 1
    return passing


def verify_seed(*, timeout_seconds: float = 90.0) -> dict[str, int]:
    """Verify immediate aspects and poll indexed health/assertion invariants."""

    graph = get_graph()
    dataset_count = sum(
        graph.get_aspect(entity_urn=item.urn, aspect_type=models.DatasetPropertiesClass) is not None
        for item in DATASETS
    )
    chart_count = sum(
        graph.get_aspect(entity_urn=chart_urn(name), aspect_type=models.ChartInfoClass) is not None
        for name, *_ in CHARTS
    )
    dashboard_count = sum(
        graph.get_aspect(entity_urn=dashboard_urn(name), aspect_type=models.DashboardInfoClass)
        is not None
        for name, *_ in DASHBOARDS
    )
    model_count = int(
        graph.get_aspect(entity_urn=ML_MODEL_URN, aspect_type=models.MLModelPropertiesClass)
        is not None
    )
    missing_edges: list[str] = []
    for edge in LINEAGE:
        upstream = next(item for item in DATASETS if item.key == edge.upstream)
        downstream = next(item for item in DATASETS if item.key == edge.downstream)
        aspect = graph.get_aspect(
            entity_urn=downstream.urn,
            aspect_type=models.UpstreamLineageClass,
        )
        if aspect is None or upstream.urn not in {item.dataset for item in aspect.upstreams}:
            missing_edges.append(f"{edge.upstream}->{edge.downstream}")
    for name, _display, input_key, _weekly_views in CHARTS:
        chart = graph.get_aspect(
            entity_urn=chart_urn(name),
            aspect_type=models.ChartInfoClass,
        )
        expected = next(item.urn for item in DATASETS if item.key == input_key)
        actual = set(chart.inputs if chart else [])
        if expected not in actual:
            missing_edges.append(f"{input_key}->{name}")
    for name, _display, chart_names, *_ in DASHBOARDS:
        dashboard = graph.get_aspect(
            entity_urn=dashboard_urn(name),
            aspect_type=models.DashboardInfoClass,
        )
        actual = {edge.destinationUrn for edge in (dashboard.chartEdges if dashboard else [])}
        for chart_name in chart_names:
            if chart_urn(chart_name) not in actual:
                missing_edges.append(f"{chart_name}->{name}")
    ml_feature = graph.get_aspect(
        entity_urn=ML_FEATURE_URN,
        aspect_type=models.MLFeaturePropertiesClass,
    )
    ml_properties = graph.get_aspect(
        entity_urn=ML_MODEL_URN,
        aspect_type=models.MLModelPropertiesClass,
    )
    features_urn = next(item.urn for item in DATASETS if item.key == "ml.trip_eta_features")
    if (
        ml_feature is None
        or features_urn not in (ml_feature.sources or [])
        or ml_properties is None
        or ML_FEATURE_URN not in (ml_properties.mlFeatures or [])
    ):
        missing_edges.append("ml.trip_eta_features->oncall_demo_eta_predictor")

    if (dataset_count, chart_count, dashboard_count, model_count) != (15, 4, 3, 1):
        raise AssertionError(
            "Entity count mismatch: "
            f"datasets={dataset_count}, charts={chart_count}, dashboards={dashboard_count}, "
            f"models={model_count}"
        )
    if missing_edges:
        raise AssertionError(f"Missing lineage edges: {missing_edges}")

    deadline = time.monotonic() + timeout_seconds
    passing_assertions = 0
    healthy_datasets = 0
    while time.monotonic() < deadline:
        passing_assertions = _assert_latest_results_passing()
        health_data = execute_graphql(HEALTH_SIGNALS_QUERY, {"input": _search_input()})
        search = health_data.get("searchAcrossEntities") or {}
        healthy_datasets = sum(
            all(
                item.get("status") == "PASS"
                for item in (result.get("entity") or {}).get("health") or []
            )
            for result in search.get("searchResults") or []
        )
        if search.get("total") == 15 and passing_assertions == 9 and healthy_datasets == 15:
            fresh = all(
                not get_freshness(item.urn, sla_hours=item.sla_hours)["breached"]
                for item in DATASETS
            )
            if fresh:
                break
        time.sleep(2)
    else:
        raise AssertionError(
            f"Indexed invariants timed out: passing_assertions={passing_assertions}, "
            f"healthy_datasets={healthy_datasets}"
        )

    return {
        "datasets": dataset_count,
        "charts": chart_count,
        "dashboards": dashboard_count,
        "ml_models": model_count,
        "assertions_passing": passing_assertions,
        "dataset_lineage_edges": len(LINEAGE),
        "consumer_lineage_edges": len(CHARTS) + sum(len(item[2]) for item in DASHBOARDS) + 1,
        "healthy_datasets": healthy_datasets,
    }


def seed(*, wipe: bool, verify: bool) -> dict[str, int] | None:
    """Run the ordered idempotent seed workflow and optionally verify all invariants."""

    if wipe:
        progress(1, "hard-deleting deterministic oncall demo entities")
        wipe_namespace()
    else:
        progress(1, "preserving existing oncall demo entities for idempotent upsert")
    progress(2, "upserting platform, people, groups, and RideFlow domain")
    _seed_platform_people_domain()
    progress(3, "upserting tags and post-mortem structured property")
    _seed_tags_and_property()
    progress(4, "upserting 15 datasets with schemas and ownership")
    for dataset in DATASETS:
        upsert_dataset(dataset)
    progress(5, "writing and immediately verifying 15 explicit dataset lineage edges")
    _seed_lineage()
    progress(6, "upserting 4 charts, 3 dashboards, and 1 ML model")
    _seed_consumers()
    event_ms = now_millis() - 30 * 60 * 1000
    progress(7, "upserting 5 query evidence entities")
    _seed_queries(event_ms)
    progress(8, "upserting 9 assertion definitions and PASS run events")
    _seed_assertions(event_ms)
    progress(9, "emitting healthy operations and profiles for 15 datasets")
    metric_ms = now_millis()
    for dataset in DATASETS:
        emit_operation(dataset, hours_stale=dataset.sla_hours * 0.2, event_ms=metric_ms)
        emit_profile(dataset, row_count=dataset.row_count, event_ms=metric_ms)
    progress(10, "emitting seven daily usage buckets for 15 datasets")
    for dataset in DATASETS:
        emit_usage(dataset)
    progress(11, "verifying entity counts, lineage, assertion status, and health")
    if not verify:
        return None
    report = verify_seed()
    print(
        "VERIFY " + " ".join(f"{key}={value}" for key, value in report.items()),
        flush=True,
    )
    return report


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for ``python -m demo.seed``."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wipe", action="store_true", help="hard-delete demo entities first")
    parser.add_argument("--verify", action="store_true", help="verify every seeded invariant")
    args = parser.parse_args(argv)
    try:
        seed(wipe=args.wipe, verify=args.verify)
    except Exception as exc:
        print(f"ERROR seed_failed={type(exc).__name__} message={exc}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
