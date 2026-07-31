"""A stored run replays without touching DataHub or OpenAI."""

from __future__ import annotations

import pytest

from oncall_agent.agent.events import MetricEvent
from oncall_agent.cli import _replay
from oncall_agent.config import Settings
from oncall_agent.store import Store


@pytest.mark.asyncio
async def test_offline_replay_uses_only_sqlite(tmp_path, capsys) -> None:
    path = tmp_path / "replay.db"
    store = await Store.open(path)
    try:
        await store.append_event(
            MetricEvent(
                seq=1,
                run_id="run-offline",
                ts="2026-08-01T00:00:00.000Z",
                name="tool_calls",
                value=12,
            )
        )
    finally:
        await store.close()

    status = await _replay("run-offline", Settings(db_path=str(path), openai_api_key=None))
    assert status == 0
    assert "tool_calls=12" in capsys.readouterr().out
