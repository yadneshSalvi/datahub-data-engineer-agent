"""Shared DataHub clients, resilient GraphQL execution, and UI deep links."""

from __future__ import annotations

import logging
import time
import warnings
from functools import lru_cache
from typing import Any

import httpx
from datahub.errors import ExperimentalWarning, IngestionAttributionWarning

from oncall_agent.config import get_settings
from oncall_agent.datahub.urns import entity_type_from_urn

warnings.filterwarnings("ignore", category=ExperimentalWarning)
warnings.filterwarnings("ignore", category=IngestionAttributionWarning)

from datahub.ingestion.graph.client import DatahubClientConfig, DataHubGraph  # noqa: E402
from datahub.sdk import DataHubClient  # noqa: E402

log = logging.getLogger(__name__)

_TRANSIENT_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}


class DataHubGraphQLError(RuntimeError):
    """GraphQL response contained a top-level errors array."""


class DataHubPreflightError(RuntimeError):
    """The configured DATAHUB_GMS_URL is not answering as a DataHub GMS."""


def preflight_gms(gms_url: str | None = None, *, timeout: float = 5.0) -> dict[str, Any]:
    """Assert that ``gms_url`` is really a DataHub GMS, and return its ``/config`` payload.

    Worth the extra call because the failure it prevents is so confusing: an unrelated web app
    listening on the conventional port 8080 answers ``GET /config`` with HTTP 200 and HTML, so a
    naive health check *passes* and every later DataHub call fails for reasons that look like a
    DataHub bug. Fail loudly here instead.
    """

    base = (gms_url or get_settings().datahub_gms_url).rstrip("/")
    try:
        response = httpx.get(f"{base}/config", timeout=timeout)
        response.raise_for_status()
        config = response.json()
    except httpx.HTTPError as exc:
        raise DataHubPreflightError(
            f"No DataHub GMS reachable at {base} ({exc}). Is the quickstart running? "
            f"Check `docker ps` and DATAHUB_GMS_URL."
        ) from exc
    except ValueError as exc:
        raise DataHubPreflightError(
            f"{base}/config did not return JSON — something other than DataHub is listening on "
            f"that port. Set DATAHUB_GMS_URL to the real GMS (commonly 8080, 8081 on this machine)."
        ) from exc
    if not isinstance(config, dict) or "versions" not in config:
        raise DataHubPreflightError(
            f"{base}/config returned JSON that is not a DataHub config payload. "
            f"Point DATAHUB_GMS_URL at the GMS container, not the frontend or another service."
        )
    server = config.get("datahub") or {}
    log.info(
        "DataHub preflight OK at %s (serverType=%s, version=%s)",
        base,
        server.get("serverType"),
        (config.get("versions", {}).get("acryldata/datahub") or {}).get("version"),
    )
    return config


@lru_cache(maxsize=1)
def get_client() -> DataHubClient:
    """Return the process-wide DataHub SDK client singleton."""

    return DataHubClient(server=get_settings().datahub_gms_url)


@lru_cache(maxsize=1)
def get_graph() -> DataHubGraph:
    """Return the process-wide DataHub graph client singleton."""

    return DataHubGraph(DatahubClientConfig(server=get_settings().datahub_gms_url))


def clear_client_caches() -> None:
    """Clear process-wide clients, primarily for isolated tests."""

    get_client.cache_clear()
    get_graph.cache_clear()


def execute_graphql(
    query: str,
    variables: dict[str, Any] | None = None,
    *,
    attempts: int = 3,
    backoff_seconds: float = 2.0,
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    """Execute verified GraphQL with three attempts on connection/transient failures."""

    if attempts < 1:
        raise ValueError("attempts must be at least one")
    endpoint = f"{get_settings().datahub_gms_url.rstrip('/')}/api/graphql"
    payload: dict[str, Any] = {"query": query}
    if variables is not None:
        payload["variables"] = variables

    for attempt in range(1, attempts + 1):
        try:
            response = httpx.post(endpoint, json=payload, timeout=timeout_seconds)
            if response.status_code in _TRANSIENT_STATUS_CODES:
                raise httpx.HTTPStatusError(
                    f"Transient DataHub response {response.status_code}",
                    request=response.request,
                    response=response,
                )
            response.raise_for_status()
            body = response.json()
            errors = body.get("errors")
            if errors:
                raise DataHubGraphQLError(f"DataHub GraphQL errors: {errors}")
            data = body.get("data")
            if not isinstance(data, dict):
                raise DataHubGraphQLError("DataHub GraphQL response has no data object")
            return data
        except (
            httpx.ConnectError,
            httpx.TimeoutException,
            httpx.NetworkError,
            httpx.HTTPStatusError,
        ) as exc:
            transient_http = not isinstance(exc, httpx.HTTPStatusError) or (
                exc.response.status_code in _TRANSIENT_STATUS_CODES
            )
            if not transient_http or attempt == attempts:
                raise
            log.warning(
                "Transient DataHub GraphQL failure (attempt %s/%s): %s",
                attempt,
                attempts,
                exc,
            )
            time.sleep(backoff_seconds)
    raise AssertionError("GraphQL retry loop ended unexpectedly")


def datahub_url_for(urn: str) -> str:
    """Build a clickable DataHub UI deep link for a supported entity URN."""

    route = {
        "DATASET": "dataset",
        "CHART": "chart",
        "DASHBOARD": "dashboard",
        "MLMODEL": "mlModel",
        "ASSERTION": "assertions",
        "INCIDENT": "incident",
        "DOCUMENT": "document",
    }.get(entity_type_from_urn(urn))
    if route is None:
        raise ValueError(f"Unsupported DataHub URN for deep link: {urn}")
    return f"{get_settings().datahub_ui_url.rstrip('/')}/{route}/{urn}"
