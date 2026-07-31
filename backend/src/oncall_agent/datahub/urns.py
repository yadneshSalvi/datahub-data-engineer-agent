"""URN construction, parsing, and compact display helpers for the demo namespace."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

import datahub.emitter.mce_builder as builder

from oncall_agent.config import get_settings

Layer = Literal["raw", "staging", "marts", "ml", "bi", "unknown"]

_DATASET_RE = re.compile(
    r"^urn:li:dataset:\(urn:li:dataPlatform:(?P<platform>[^,]+),"
    r"(?P<name>.+),(?P<env>[^,)]+)\)$"
)


@dataclass(frozen=True, slots=True)
class DatasetUrnParts:
    """Parsed components of a DataHub dataset URN."""

    platform: str
    name: str
    env: str


def qualify_dataset_name(name: str) -> str:
    """Return a fully qualified demo dataset name from a short or qualified name."""

    prefix = get_settings().name_prefix
    return name if name.startswith(prefix) else f"{prefix}{name}"


def dataset_urn(name: str, *, env: str = "PROD", platform: str | None = None) -> str:
    """Build a deterministic dataset URN in the configured namespace."""

    settings = get_settings()
    return builder.make_dataset_urn(platform or settings.platform, qualify_dataset_name(name), env)


def schema_field_urn(dataset: str, field_path: str) -> str:
    """Build a schema-field URN for a dataset URN and field path."""

    return builder.make_schema_field_urn(dataset, field_path)


def assertion_urn(assertion_id: str) -> str:
    """Build a deterministic assertion URN."""

    return builder.make_assertion_urn(assertion_id)


def tag_urn(tag_name: str) -> str:
    """Build a tag URN."""

    return builder.make_tag_urn(tag_name)


def parse_dataset_urn(urn: str) -> DatasetUrnParts:
    """Parse a dataset URN, raising ``ValueError`` for any other shape."""

    match = _DATASET_RE.fullmatch(urn)
    if match is None:
        raise ValueError(f"Not a dataset URN: {urn}")
    return DatasetUrnParts(**match.groupdict())


def is_our_dataset_urn(urn: str) -> bool:
    """Return whether a URN belongs to the configured demo dataset namespace."""

    try:
        parts = parse_dataset_urn(urn)
    except ValueError:
        return False
    settings = get_settings()
    return parts.platform == settings.platform and parts.name.startswith(settings.name_prefix)


def entity_type_from_urn(urn: str) -> str:
    """Return the normalized entity type encoded by a DataHub URN."""

    prefix = "urn:li:"
    if not urn.startswith(prefix):
        return "UNKNOWN"
    raw = urn[len(prefix) :].split(":", 1)[0]
    return {"mlModel": "MLMODEL"}.get(raw, raw.upper())


def qualified_name_from_urn(urn: str) -> str:
    """Extract the entity's qualified name or identifier from a supported URN."""

    if urn.startswith("urn:li:dataset:"):
        return parse_dataset_urn(urn).name
    if urn.startswith(("urn:li:chart:(", "urn:li:dashboard:(")):
        return urn.rsplit(",", 1)[-1].removesuffix(")")
    if urn.startswith("urn:li:mlModel:("):
        body = urn.removeprefix("urn:li:mlModel:(").removesuffix(")")
        return body.rsplit(",", 2)[-2]
    return urn.rsplit(":", 1)[-1]


def short_display_name(value: str) -> str:
    """Return a concise display name from a qualified name or supported URN."""

    name = qualified_name_from_urn(value) if value.startswith("urn:li:") else value
    return name.rsplit(".", 1)[-1]


def infer_layer(value: str, *, entity_type: str | None = None) -> Layer:
    """Infer the warehouse/UI layer from an entity name or URN."""

    resolved_type = entity_type or (
        entity_type_from_urn(value) if value.startswith("urn:li:") else None
    )
    if resolved_type in {"CHART", "DASHBOARD"}:
        return "bi"
    if resolved_type == "MLMODEL":
        return "ml"
    name = qualified_name_from_urn(value) if value.startswith("urn:li:") else value
    parts = name.split(".")
    for candidate in ("raw", "staging", "marts", "ml"):
        if candidate in parts:
            return candidate  # type: ignore[return-value]
    return "unknown"


def middle_truncate(value: str, max_length: int = 72, *, marker: str = "…") -> str:
    """Truncate the middle of a string while preserving both identifying ends."""

    if max_length < len(marker) + 2:
        raise ValueError("max_length is too small for middle truncation")
    if len(value) <= max_length:
        return value
    remaining = max_length - len(marker)
    left = (remaining + 1) // 2
    right = remaining // 2
    return f"{value[:left]}{marker}{value[-right:]}"
