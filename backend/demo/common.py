"""Shared, verified DataHub emission primitives for demo commands."""

# ruff: noqa: E402 -- warning filters must be installed before importing datahub.sdk.

from __future__ import annotations

import time
import uuid
import warnings
from datetime import UTC, datetime, timedelta

import datahub.emitter.mce_builder as builder
import datahub.metadata.schema_classes as models
from datahub.emitter.mcp import MetadataChangeProposalWrapper
from datahub.errors import ExperimentalWarning, IngestionAttributionWarning

warnings.filterwarnings("ignore", category=ExperimentalWarning)
warnings.filterwarnings("ignore", category=IngestionAttributionWarning)

from datahub.sdk import Dataset

from demo.catalog import ASSERTIONS, DATASET_BY_KEY, DOMAIN_URN, PEOPLE, DatasetSpec
from oncall_agent.config import get_settings
from oncall_agent.datahub.client import get_client, get_graph
from oncall_agent.datahub.urns import assertion_urn, schema_field_urn

ACTOR_URN = "urn:li:corpuser:datahub"


def now_millis() -> int:
    """Return the current wall-clock time in milliseconds."""

    return int(time.time() * 1000)


def upsert_dataset(spec: DatasetSpec, *, columns: tuple[tuple[str, str], ...] | None = None) -> str:
    """Upsert a seeded dataset with its complete schema, ownership, domain, and markers."""

    get_client().entities.upsert(
        Dataset(
            platform=get_settings().platform,
            name=spec.name,
            env="PROD",
            description=f"RideFlow demo warehouse table: {spec.key}",
            schema=list(columns if columns is not None else spec.columns),
            custom_properties={
                "seeded_by": "oncall-agent",
                "oncall.freshness_sla_hours": str(spec.sla_hours),
            },
            owners=[
                (
                    f"urn:li:corpuser:{spec.owner}",
                    models.OwnershipTypeClass.TECHNICAL_OWNER,
                ),
                (
                    f"urn:li:corpGroup:{spec.group}",
                    models.OwnershipTypeClass.DATAOWNER,
                ),
            ],
            domain=DOMAIN_URN,
        )
    )
    return spec.urn


def emit_operation(spec: DatasetSpec, *, hours_stale: float, event_ms: int | None = None) -> None:
    """Emit a dataset operation that carries the freshness signal."""

    timestamp_ms = event_ms if event_ms is not None else now_millis()
    get_graph().emit(
        MetadataChangeProposalWrapper(
            entityUrn=spec.urn,
            aspect=models.OperationClass(
                timestampMillis=timestamp_ms,
                operationType=models.OperationTypeClass.INSERT,
                lastUpdatedTimestamp=timestamp_ms - int(hours_stale * 3_600_000),
                actor=ACTOR_URN,
                numAffectedRows=0,
                sourceType=models.OperationSourceTypeClass.DATA_PROCESS,
            ),
        )
    )


def emit_profile(spec: DatasetSpec, *, row_count: int, event_ms: int | None = None) -> None:
    """Emit one dataset profile point with representative field metrics."""

    timestamp_ms = event_ms if event_ms is not None else now_millis()
    first_field = spec.columns[0][0]
    get_graph().emit(
        MetadataChangeProposalWrapper(
            entityUrn=spec.urn,
            aspect=models.DatasetProfileClass(
                timestampMillis=timestamp_ms,
                rowCount=row_count,
                columnCount=len(spec.columns),
                sizeInBytes=max(row_count, 1) * max(len(spec.columns), 1) * 16,
                fieldProfiles=[
                    models.DatasetFieldProfileClass(
                        fieldPath=first_field,
                        uniqueCount=row_count,
                        nullCount=0,
                    )
                ],
            ),
        )
    )


def emit_usage(spec: DatasetSpec, *, reference: datetime | None = None) -> None:
    """Emit seven daily usage buckets for ranking the demo blast radius."""

    reference_day = (reference or datetime.now(UTC)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    owner_email = next(
        (person.email for person in PEOPLE if person.username == spec.owner),
        f"{spec.owner}@rideflow.example",
    )
    for day in range(7):
        timestamp_ms = int((reference_day - timedelta(days=day)).timestamp() * 1000)
        query_count = max(1, spec.daily_queries - day * 3)
        unique_users = max(
            1, spec.unique_users + (1 if day % 3 == 1 else -1 if day % 3 == 2 else 0)
        )
        get_graph().emit(
            MetadataChangeProposalWrapper(
                entityUrn=spec.urn,
                aspect=models.DatasetUsageStatisticsClass(
                    timestampMillis=timestamp_ms,
                    eventGranularity=models.TimeWindowSizeClass(
                        unit=models.CalendarIntervalClass.DAY
                    ),
                    uniqueUserCount=unique_users,
                    totalSqlQueries=query_count,
                    topSqlQueries=[f"SELECT * FROM {spec.name} LIMIT 100"],
                    userCounts=[
                        models.DatasetUserUsageCountsClass(
                            user=f"urn:li:corpuser:{spec.owner}",
                            count=query_count,
                            userEmail=owner_email,
                        )
                    ],
                    fieldCounts=[
                        models.DatasetFieldUsageCountsClass(
                            fieldPath=spec.columns[0][0],
                            count=max(1, query_count - 1),
                        )
                    ],
                ),
            )
        )


def _assertion_spec(assertion_id: str) -> tuple[str, str, str, str, str | None, str | None]:
    for candidate_id, dataset_key, aggregation, operator, minimum, maximum, field in ASSERTIONS:
        if candidate_id == assertion_id:
            return dataset_key, aggregation, operator, minimum, maximum, field
    raise KeyError(assertion_id)


def emit_assertion_definition(assertion_id: str) -> str:
    """Emit a deterministic OSS assertion definition and platform instance."""

    dataset_key, aggregation, operator, minimum, maximum, field = _assertion_spec(assertion_id)
    dataset = DATASET_BY_KEY[dataset_key]
    urn = assertion_urn(assertion_id)
    now_ms = now_millis()
    audit = models.AuditStampClass(time=now_ms, actor=ACTOR_URN)
    parameter_type = models.AssertionStdParameterTypeClass.NUMBER
    if operator == "BETWEEN":
        parameters = models.AssertionStdParametersClass(
            minValue=models.AssertionStdParameterClass(type=parameter_type, value=minimum),
            maxValue=models.AssertionStdParameterClass(type=parameter_type, value=maximum),
        )
        expected = f"{minimum}..{maximum}"
    else:
        parameters = models.AssertionStdParametersClass(
            value=models.AssertionStdParameterClass(type=parameter_type, value=minimum)
        )
        expected = str(minimum)
    target = f"{dataset.key}.{field}" if field else dataset.key
    graph = get_graph()
    graph.emit(
        MetadataChangeProposalWrapper(
            entityUrn=urn,
            aspect=models.AssertionInfoClass(
                type=models.AssertionTypeClass.DATASET,
                description=f"{target} {aggregation.lower()} must satisfy {operator}: {expected}",
                datasetAssertion=models.DatasetAssertionInfoClass(
                    dataset=dataset.urn,
                    scope=(
                        models.DatasetAssertionScopeClass.DATASET_COLUMN
                        if field
                        else models.DatasetAssertionScopeClass.DATASET_ROWS
                    ),
                    operator=getattr(models.AssertionStdOperatorClass, operator),
                    fields=[schema_field_urn(dataset.urn, field)] if field else None,
                    aggregation=getattr(models.AssertionStdAggregationClass, aggregation),
                    parameters=parameters,
                    nativeType=("not_null" if field else "row_count_between"),
                ),
                source=models.AssertionSourceClass(
                    type=models.AssertionSourceTypeClass.EXTERNAL,
                    created=audit,
                ),
                lastUpdated=audit,
            ),
        )
    )
    graph.emit(
        MetadataChangeProposalWrapper(
            entityUrn=urn,
            aspect=models.DataPlatformInstanceClass(
                platform=builder.make_data_platform_urn(get_settings().platform)
            ),
        )
    )
    return urn


def emit_assertion_result(
    assertion_id: str,
    *,
    success: bool,
    actual_value: float,
    observed: str | None = None,
    event_ms: int | None = None,
) -> None:
    """Emit a complete OSS assertion run event; its timestamp controls the visible status."""

    dataset_key, _aggregation, operator, minimum, maximum, _field = _assertion_spec(assertion_id)
    dataset = DATASET_BY_KEY[dataset_key]
    timestamp_ms = event_ms if event_ms is not None else now_millis()
    expected = f"{minimum}..{maximum}" if operator == "BETWEEN" else str(minimum)
    get_graph().emit(
        MetadataChangeProposalWrapper(
            entityUrn=assertion_urn(assertion_id),
            aspect=models.AssertionRunEventClass(
                timestampMillis=timestamp_ms,
                runId=str(uuid.uuid4()),
                asserteeUrn=dataset.urn,
                assertionUrn=assertion_urn(assertion_id),
                status=models.AssertionRunStatusClass.COMPLETE,
                result=models.AssertionResultClass(
                    type=(
                        models.AssertionResultTypeClass.SUCCESS
                        if success
                        else models.AssertionResultTypeClass.FAILURE
                    ),
                    actualAggValue=actual_value,
                    rowCount=int(actual_value) if actual_value >= 0 else None,
                    nativeResults={
                        "expected": expected,
                        "observed": observed or str(actual_value),
                    },
                ),
            ),
        )
    )


def healthy_assertion_value(assertion_id: str) -> float:
    """Return a representative passing value for a seeded assertion."""

    dataset_key, aggregation, _operator, _minimum, _maximum, _field = _assertion_spec(assertion_id)
    if aggregation == "NULL_COUNT":
        return 0.0
    return float(DATASET_BY_KEY[dataset_key].row_count)
