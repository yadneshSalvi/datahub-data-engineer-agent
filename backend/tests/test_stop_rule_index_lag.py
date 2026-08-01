"""Index-independent source-node corroboration tests for the root-cause stop rule."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from agents.tool_context import ToolContext

import oncall_agent.datahub.reads as reads
from oncall_agent.agent.tools_native import confirm_no_upstreams
from oncall_agent.datahub.urns import dataset_urn


class _Graph:
    def __init__(self, state: bool | None) -> None:
        self.state = state

    def get_aspect(self, **_kwargs: object) -> object | None:
        if self.state is None:
            raise RuntimeError("aspect API unavailable")
        if self.state:
            return SimpleNamespace(upstreams=[SimpleNamespace(dataset="urn:parent")])
        return None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("aspect_state", "expected_verdict", "guidance_fragment"),
    [
        (False, "confirmed", "stop rule is satisfied"),
        (True, "contradicted", "keep walking"),
        (None, "unknown", "Do NOT declare root cause"),
    ],
)
async def test_confirm_no_upstreams_has_three_explicit_verdicts(
    monkeypatch: pytest.MonkeyPatch,
    aspect_state: bool | None,
    expected_verdict: str,
    guidance_fragment: str,
) -> None:
    monkeypatch.setattr(reads, "get_graph", lambda: _Graph(aspect_state))
    emitted: list[object] = []

    async def emit(event: object) -> None:
        emitted.append(event)

    # The search-backed lineage result is deliberately empty. The tool must rely on the aspect,
    # not reinterpret this empty list as proof that the node is a source.
    facade = SimpleNamespace(
        get_lineage=lambda *_args, **_kwargs: [],
        has_upstream_edges=reads.has_upstream_edges,
    )
    context = SimpleNamespace(tool_calls=0, dh=facade, emit=emit)
    tool_context = ToolContext(
        context=context,
        tool_name="confirm_no_upstreams",
        tool_call_id="call-source-check",
        tool_arguments="{}",
    )
    urn = dataset_urn("staging.stg_drivers")
    assert facade.get_lineage(urn, direction="upstream") == []

    raw = await confirm_no_upstreams.on_invoke_tool(
        tool_context,
        json.dumps({"dataset_urn": urn}),
    )
    result = json.loads(raw)

    assert result["verdict"] == expected_verdict
    assert guidance_fragment in result["guidance"]
    assert context.tool_calls == 1
    assert emitted
