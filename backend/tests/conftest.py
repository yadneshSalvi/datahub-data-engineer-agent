"""Shared isolated configuration for the backend unit tests."""

from __future__ import annotations

import pytest

from oncall_agent.config import get_settings
from oncall_agent.datahub.client import clear_client_caches


@pytest.fixture(autouse=True)
def isolated_clients(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> None:
    """Point unit tests at a stub URL and clear process-wide client caches."""

    if request.node.get_closest_marker("live") is None:
        monkeypatch.setenv("DATAHUB_GMS_URL", "http://gms.test")
        monkeypatch.setenv("DATAHUB_UI_URL", "http://ui.test")
    else:
        monkeypatch.delenv("DATAHUB_GMS_URL", raising=False)
        monkeypatch.delenv("DATAHUB_UI_URL", raising=False)
    get_settings.cache_clear()
    clear_client_caches()
    yield
    get_settings.cache_clear()
    clear_client_caches()
