"""Idempotent DataHub write helpers constrained to the oncall demo namespace."""

# ruff: noqa: E402 -- warning filters must be installed before importing datahub.sdk.

from __future__ import annotations

import json
import logging
import re
import time
import warnings
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

import datahub.metadata.schema_classes as models
from datahub.emitter.mcp import MetadataChangeProposalWrapper
from datahub.errors import ExperimentalWarning, IngestionAttributionWarning

warnings.filterwarnings("ignore", category=ExperimentalWarning)
warnings.filterwarnings("ignore", category=IngestionAttributionWarning)

from datahub.sdk import Tag, TagUrn
from datahub.specific.dataset import DatasetPatchBuilder

from oncall_agent.config import get_settings
from oncall_agent.datahub.client import datahub_url_for, execute_graphql, get_client, get_graph
from oncall_agent.datahub.reads import dataset_exists, list_open_incidents
from oncall_agent.datahub.urns import is_our_dataset_urn, qualified_name_from_urn

log = logging.getLogger(__name__)

RAISE_INCIDENT_MUTATION = """
mutation r($input: RaiseIncidentInput!) { raiseIncident(input: $input) }
"""

UPDATE_INCIDENT_MUTATION = """
mutation u($urn: String!, $input: IncidentStatusInput!) {
  updateIncidentStatus(urn: $urn, input: $input)
}
"""

_incident_cache: dict[tuple[str, str, str], str] = {}


def _assert_safe_target(urn: str) -> None:
    settings = get_settings()
    safe = is_our_dataset_urn(urn)
    if urn.startswith(("urn:li:chart:(", "urn:li:dashboard:(", "urn:li:mlModel:(")):
        safe = qualified_name_from_urn(urn).startswith(settings.name_prefix.rstrip("."))
    if urn.startswith("urn:li:document:oncall-") or urn.startswith("urn:li:assertion:oncall-"):
        safe = True
    if not safe:
        raise ValueError(f"Refusing to modify an entity outside the oncall namespace: {urn}")


def _assert_existing_dataset(urn: str) -> None:
    if urn.startswith("urn:li:dataset:") and not dataset_exists(urn):
        raise ValueError(f"Refusing to modify a dataset that does not exist: {urn}")


def ensure_tag(name: str, display_name: str, description: str, color: str) -> str:
    """Upsert a deterministic tag entity and return its URN."""

    if not name.startswith("oncall_"):
        raise ValueError("On-call tag names must start with 'oncall_'")
    get_client().entities.upsert(
        Tag(name=name, display_name=display_name, description=description, color=color)
    )
    return f"urn:li:tag:{name}"


def apply_tags(entity_urn: str, tag_names: Iterable[str], *, fields: Iterable[str] = ()) -> bool:
    """Add tags to an entity and optional dataset fields, writing only when state changes."""

    _assert_safe_target(entity_urn)
    _assert_existing_dataset(entity_urn)
    entity = get_client().entities.get(entity_urn)
    changed = False
    current = {item.tag for item in (entity.tags or [])}
    for name in dict.fromkeys(tag_names):
        tag = TagUrn(name)
        if str(tag) not in current:
            entity.add_tag(tag)
            current.add(str(tag))
            changed = True
        for field in fields:
            field_tags = {item.tag for item in (entity[field].tags or [])}
            if str(tag) not in field_tags:
                entity[field].add_tag(tag)
                changed = True
    if changed:
        get_client().entities.update(entity)
    return changed


def remove_tags(entity_urn: str, tag_names: Iterable[str], *, fields: Iterable[str] = ()) -> bool:
    """Remove tags from an entity and optional dataset fields, if present."""

    _assert_safe_target(entity_urn)
    entity = get_client().entities.get(entity_urn)
    changed = False
    current = {item.tag for item in (entity.tags or [])}
    for name in dict.fromkeys(tag_names):
        tag = TagUrn(name)
        if str(tag) in current:
            entity.remove_tag(tag)
            current.remove(str(tag))
            changed = True
        for field in fields:
            field_tags = {item.tag for item in (entity[field].tags or [])}
            if str(tag) in field_tags:
                entity[field].remove_tag(tag)
                changed = True
    if changed:
        get_client().entities.update(entity)
    return changed


def raise_incident(
    resource_urn: str,
    *,
    incident_type: str,
    title: str,
    description: str,
    priority: str = "HIGH",
    stage: str = "TRIAGE",
    message: str = "Raised by on-call agent",
) -> str:
    """Raise one active incident per resource/type/title and return its URN."""

    _assert_safe_target(resource_urn)
    _assert_existing_dataset(resource_urn)
    key = (resource_urn, incident_type, title)
    cached = _incident_cache.get(key)
    if cached is not None:
        return cached
    for incident in list_open_incidents(resource_urn):
        if incident.get("incidentType") == incident_type and incident.get("title") == title:
            urn = str(incident["urn"])
            _incident_cache[key] = urn
            return urn
    data = execute_graphql(
        RAISE_INCIDENT_MUTATION,
        {
            "input": {
                "type": incident_type,
                "title": title,
                "description": description,
                "resourceUrn": resource_urn,
                "priority": priority,
                "status": {"state": "ACTIVE", "stage": stage, "message": message},
            }
        },
    )
    urn = str(data["raiseIncident"])
    _incident_cache[key] = urn
    return urn


def update_incident_status(
    incident_urn: str,
    *,
    state: str,
    stage: str,
    message: str,
) -> bool:
    """Set an incident's current status; repeating the same transition is safe."""

    if not incident_urn.startswith("urn:li:incident:"):
        raise ValueError(f"Not an incident URN: {incident_urn}")
    data = execute_graphql(
        UPDATE_INCIDENT_MUTATION,
        {
            "urn": incident_urn,
            "input": {"state": state, "stage": stage, "message": message},
        },
    )
    if state == "RESOLVED":
        for key, cached_urn in list(_incident_cache.items()):
            if cached_urn == incident_urn:
                del _incident_cache[key]
    return bool(data.get("updateIncidentStatus"))


def add_link(entity_urn: str, url: str, label: str) -> bool:
    """Add one institutional-memory link if its URL is not already present."""

    _assert_safe_target(entity_urn)
    entity = get_client().entities.get(entity_urn)
    if any(link.url == url for link in (entity.links or [])):
        return False
    entity.add_link((url, label))
    get_client().entities.update(entity)
    return True


def remove_link(entity_urn: str, url: str) -> bool:
    """Remove one institutional-memory link by URL if present."""

    _assert_safe_target(entity_urn)
    entity = get_client().entities.get(entity_urn)
    if not any(link.url == url for link in (entity.links or [])):
        return False
    entity.remove_link(url)
    get_client().entities.update(entity)
    return True


def patch_custom_properties(entity_urn: str, values: Mapping[str, str | None]) -> bool:
    """Merge or remove dataset custom properties without replacing unrelated keys."""

    _assert_safe_target(entity_urn)
    entity = get_client().entities.get(entity_urn)
    current = dict(entity.custom_properties or {})
    changes = {key: value for key, value in values.items() if current.get(key) != value}
    if not changes:
        return False
    builder = DatasetPatchBuilder(entity_urn)
    for key, value in changes.items():
        if value is None:
            if key in current:
                builder.remove_custom_property(key)
        else:
            builder.add_custom_property(key, value)
    for proposal in builder.build():
        get_graph().emit(proposal)
    return True


def ensure_structured_property_definition(
    *,
    property_urn: str = "urn:li:structuredProperty:oncall.postmortem",
    qualified_name: str = "oncall.postmortem",
    display_name: str = "On-Call Post-Mortem",
    description: str = "Structured post-mortem written back by the On-Call Data Engineer Agent",
    registration_wait_seconds: float = 3.0,
) -> str:
    """Create the post-mortem structured-property definition once and wait for registration."""

    if not property_urn.startswith("urn:li:structuredProperty:oncall."):
        raise ValueError("Structured properties must use the oncall namespace")
    graph = get_graph()
    existing = graph.get_aspect(
        entity_urn=property_urn,
        aspect_type=models.StructuredPropertyDefinitionClass,
    )
    if existing is not None:
        return property_urn
    graph.emit(
        MetadataChangeProposalWrapper(
            entityUrn=property_urn,
            aspect=models.StructuredPropertyDefinitionClass(
                qualifiedName=qualified_name,
                displayName=display_name,
                valueType="urn:li:dataType:datahub.rich_text",
                description=description,
                entityTypes=["urn:li:entityType:datahub.dataset"],
                cardinality=models.PropertyCardinalityClass.MULTIPLE,
            ),
        )
    )
    if registration_wait_seconds:
        time.sleep(registration_wait_seconds)
    return property_urn


def read_structured_property(
    entity_urn: str,
    property_urn: str = "urn:li:structuredProperty:oncall.postmortem",
) -> list[Any]:
    """Read all values assigned to one structured property."""

    _assert_safe_target(entity_urn)
    entity = get_client().entities.get(entity_urn)
    for assignment in entity.structured_properties or []:
        if assignment.propertyUrn == property_urn:
            return list(assignment.values)
    return []


def set_structured_property(
    entity_urn: str,
    values: Sequence[Any],
    *,
    property_urn: str = "urn:li:structuredProperty:oncall.postmortem",
    append: bool = False,
) -> bool:
    """Set or append deduplicated structured-property values, writing only on change."""

    _assert_safe_target(entity_urn)
    entity = get_client().entities.get(entity_urn)
    current: list[Any] = []
    for assignment in entity.structured_properties or []:
        if assignment.propertyUrn == property_urn:
            current = list(assignment.values)
            break
    desired = current.copy() if append else []
    for value in values:
        if value not in desired:
            desired.append(value)
    if desired == current:
        return False
    entity.set_structured_property(property_urn, desired)
    get_client().entities.update(entity)
    return True


def write_document(
    *,
    incident_id: str,
    title: str,
    markdown_body: str,
    root_cause_urn: str,
    symptom_urn: str,
    timestamp_ms: int | None = None,
) -> str:
    """Upsert a deterministic published DataHub document for an incident post-mortem."""

    _assert_safe_target(root_cause_urn)
    _assert_safe_target(symptom_urn)
    document_urn = f"urn:li:document:oncall-postmortem-{incident_id}"
    _assert_safe_target(document_urn)
    now_ms = timestamp_ms if timestamp_ms is not None else int(time.time() * 1000)
    audit = models.AuditStampClass(time=now_ms, actor="urn:li:corpuser:datahub")
    graph = get_graph()
    graph.emit(
        MetadataChangeProposalWrapper(
            entityUrn=document_urn,
            aspect=models.DocumentInfoClass(
                title=title,
                status=models.DocumentStatusClass(state=models.DocumentStateClass.PUBLISHED),
                contents=models.DocumentContentsClass(text=markdown_body),
                created=audit,
                lastModified=audit,
                source=models.DocumentSourceClass(
                    sourceType=models.DocumentSourceTypeClass.EXTERNAL,
                    externalUrl=f"{get_settings().frontend_url}/memory/{incident_id}",
                    externalId=incident_id,
                ),
                relatedAssets=[
                    models.RelatedAssetClass(asset=root_cause_urn),
                    models.RelatedAssetClass(asset=symptom_urn),
                ],
                customProperties={"seeded_by": "oncall-agent", "incident_id": incident_id},
            ),
        )
    )
    graph.emit(
        MetadataChangeProposalWrapper(
            entityUrn=document_urn,
            aspect=models.DocumentSettingsClass(showInGlobalContext=True, lastModified=audit),
        )
    )
    return document_urn


def read_document(document_urn: str) -> dict[str, Any] | None:
    """Read a DataHub document by deterministic URN."""

    _assert_safe_target(document_urn)
    aspect = get_graph().get_aspect(entity_urn=document_urn, aspect_type=models.DocumentInfoClass)
    if aspect is None:
        return None
    return {
        "urn": document_urn,
        "title": aspect.title,
        "contents": aspect.contents.text,
        "related_assets": [item.asset for item in aspect.relatedAssets or []],
        "custom_properties": dict(aspect.customProperties or {}),
        "source_url": aspect.source.externalUrl if aspect.source else None,
    }


def encode_postmortem(value: Mapping[str, Any]) -> str:
    """Encode a post-mortem mapping deterministically for deduplicated property storage."""

    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def write_postmortem_artifacts(
    postmortem: Mapping[str, Any],
    *,
    markdown_body: str,
) -> dict[str, Any]:
    """Idempotently write all four verified DataHub post-mortem surfaces.

    Each surface is attempted independently so a partial DataHub failure does not prevent the
    remaining durable artifacts from being created. The returned ``errors`` mapping is empty on a
    complete write and names the failed surfaces otherwise.
    """

    root_cause_urn = str(postmortem["root_cause_urn"])
    symptom_urn = str(postmortem["symptom_urn"])
    incident_id = str(postmortem["incident_id"])
    _assert_safe_target(root_cause_urn)
    _assert_safe_target(symptom_urn)
    safe_incident_id = re.sub(r"[^A-Za-z0-9_-]", "-", incident_id).strip("-")
    document_urn = f"urn:li:document:oncall-postmortem-{safe_incident_id}"
    link = f"{get_settings().frontend_url.rstrip('/')}/memory/{incident_id}"
    encoded = encode_postmortem(postmortem)
    errors: dict[str, str] = {}

    try:
        ensure_structured_property_definition()
        set_structured_property(root_cause_urn, [encoded], append=True)
    except Exception as exc:  # continue with the other three independently durable surfaces
        log.exception("Structured-property post-mortem write failed")
        errors["structured_property"] = str(exc)

    try:
        document_urn = write_document(
            incident_id=safe_incident_id,
            title=str(postmortem["title"]),
            markdown_body=markdown_body,
            root_cause_urn=root_cause_urn,
            symptom_urn=symptom_urn,
        )
    except Exception as exc:
        log.exception("Document post-mortem write failed")
        errors["document"] = str(exc)

    try:
        add_link(root_cause_urn, link, f"On-Call post-mortem {incident_id}")
    except Exception as exc:
        log.exception("Institutional-memory link write failed")
        errors["link"] = str(exc)

    try:
        entity = get_client().entities.get(root_cause_urn)
        current = dict(entity.custom_properties or {})
        previous_id = current.get("oncall.last_incident_id")
        count = int(current.get("oncall.incident_count", "0") or 0)
        if previous_id != incident_id:
            count += 1
        patch_custom_properties(
            root_cause_urn,
            {
                "oncall.last_incident_id": incident_id,
                "oncall.last_root_cause": str(postmortem["root_cause_name"]),
                "oncall.incident_count": str(count),
            },
        )
    except Exception as exc:
        log.exception("Post-mortem custom-property patch failed")
        errors["custom_properties"] = str(exc)

    return {
        "postmortem_id": incident_id,
        "document_urn": document_urn,
        "datahub_urls": {
            "structured_property": datahub_url_for(root_cause_urn),
            "document": datahub_url_for(document_urn),
            "link": link,
        },
        "errors": errors,
    }
