"""A failed GMS probe never delays or prevents the backend health response."""

from __future__ import annotations

import time

import httpx
import pytest
import respx

from oncall_agent.app import create_app
from oncall_agent.config import Settings


@pytest.mark.asyncio
@respx.mock
async def test_health_answers_under_two_seconds_when_gms_is_down(tmp_path) -> None:
    settings = Settings(
        datahub_gms_url="http://gms-down.test",
        db_path=str(tmp_path / "health.db"),
        mcp_enabled=False,
        openai_api_key=None,
        _env_file=None,
    )
    respx.get("http://gms-down.test/config").mock(
        side_effect=httpx.ConnectError("connection refused")
    )
    respx.post("http://gms-down.test/api/graphql").mock(
        side_effect=httpx.ConnectError("connection refused")
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app), httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        started = time.monotonic()
        response = await client.get("/api/health")
        elapsed = time.monotonic() - started
    assert response.status_code == 200
    assert response.json()["datahub"]["status"] == "down"
    assert elapsed < 2.0
