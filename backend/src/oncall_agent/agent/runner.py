"""Agent construction and fully drained, replayable triage streaming."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from agents import (
    Agent,
    AgentToolStreamEvent,
    ItemHelpers,
    ModelBehaviorError,
    ModelSettings,
    Runner,
    set_default_openai_key,
)
from agents.mcp import MCPServer, MCPServerManager
from agents.result import RunResult, RunResultStreaming
from openai.types.shared import Reasoning
from pydantic import BaseModel

from oncall_agent.agent.context import DataHubFacade, EventEmitter, TriageContext
from oncall_agent.agent.events import (
    AgentMessageEvent,
    ErrorEvent,
    Event,
    MetricEvent,
    ReasoningEvent,
    RunCompletedEvent,
    RunMetrics,
    RunStartedEvent,
    ToolCallEvent,
    ToolResultEvent,
    TriggerPayload,
)
from oncall_agent.agent.models import PostMortem, TriageReport, TriggerSpec
from oncall_agent.agent.prompts import POSTMORTEM_INSTRUCTIONS, TRIAGE_INSTRUCTIONS
from oncall_agent.agent.tools_native import NATIVE_TOOLS
from oncall_agent.config import Settings, get_settings
from oncall_agent.datahub.urns import short_display_name
from oncall_agent.store import Store

log = logging.getLogger(__name__)


@dataclass(slots=True)
class Deps:
    """Runtime dependencies supplied by the CLI now and the API lifespan later."""

    store: Store
    dh: DataHubFacade = field(default_factory=DataHubFacade)
    mcp_manager: MCPServerManager | None = None
    settings: Settings = field(default_factory=get_settings)
    scenario: str | None = None


@dataclass(frozen=True, slots=True)
class AgentBundle:
    """Primary and nested agents built for one shared context."""

    triage_agent: Agent[TriageContext]
    postmortem_agent: Agent[TriageContext]


def _reasoning_summary(item: Any) -> str:
    raw = item.raw_item
    parts = getattr(raw, "summary", None) or []
    text = " ".join(
        str(getattr(part, "text", "") or (part.get("text", "") if isinstance(part, dict) else ""))
        for part in parts
    ).strip()
    return text[:1000]


async def _forward_nested_stream(
    wrapper: AgentToolStreamEvent,
    context: TriageContext,
) -> None:
    event = wrapper["event"]
    if event.type != "run_item_stream_event":
        return
    item = event.item
    if item.type == "message_output_item":
        text = ItemHelpers.text_message_output(item)
        if text:
            await context.emit(
                AgentMessageEvent(agent="Post-Mortem Author", text=text, delta=False)
            )
    elif item.type == "reasoning_item":
        summary = _reasoning_summary(item)
        if summary:
            await context.emit(ReasoningEvent(agent="Post-Mortem Author", summary=summary))


async def _postmortem_extractor(result: RunResult | RunResultStreaming) -> str:
    output = result.final_output
    if not isinstance(output, PostMortem):
        raise ModelBehaviorError("Post-mortem sub-agent did not return a PostMortem")
    return json.dumps(output.model_dump(mode="json"), separators=(",", ":"))


def build_agents(
    context: TriageContext,
    *,
    mcp_servers: list[MCPServer] | None = None,
    settings: Settings | None = None,
) -> AgentBundle:
    """Build the primary agent and its visible strict-output post-mortem tool."""

    resolved = settings or get_settings()
    postmortem_agent = Agent[TriageContext](
        name="Post-Mortem Author",
        instructions=POSTMORTEM_INSTRUCTIONS,
        model=resolved.agent_model,
        model_settings=ModelSettings(
            reasoning=Reasoning(effort="medium"),
            verbosity="low",
        ),
        output_type=PostMortem,
    )

    async def on_substream(event: AgentToolStreamEvent) -> None:
        await _forward_nested_stream(event, context)

    postmortem_tool = postmortem_agent.as_tool(
        tool_name="author_postmortem",
        tool_description=(
            "Write the structured post-mortem after root cause confirmation and blast-radius "
            "ranking. Pass the current run_id as incident_id plus the symptom, causal path with "
            "evidence per node, blast radius, and recalled prior incidents."
        ),
        custom_output_extractor=_postmortem_extractor,
        on_stream=on_substream,
        max_turns=10,
    )
    triage_agent = Agent[TriageContext](
        name="On-Call Data Engineer",
        instructions=TRIAGE_INSTRUCTIONS,
        model=resolved.agent_model,
        model_settings=ModelSettings(
            reasoning=Reasoning(effort="high"),
            verbosity="low",
            parallel_tool_calls=True,
        ),
        tools=[*NATIVE_TOOLS, postmortem_tool],
        mcp_servers=mcp_servers or [],
        mcp_config={
            "include_server_in_tool_names": True,
            "convert_schemas_to_strict": True,
        },
    )
    return AgentBundle(triage_agent=triage_agent, postmortem_agent=postmortem_agent)


def _safe_tool_payload(output: Any) -> tuple[Any, str, bool]:
    if isinstance(output, BaseModel):
        value: Any = output.model_dump(mode="json")
    elif isinstance(output, str):
        try:
            value = json.loads(output)
        except json.JSONDecodeError:
            value = output
    else:
        try:
            value = json.loads(json.dumps(output, default=str))
        except (TypeError, ValueError):
            value = str(output)
    encoded = json.dumps(value, ensure_ascii=False, default=str)
    summary = (value if isinstance(value, str) else encoded).replace("\n", " ")[:300]
    if len(encoded) > 4000:
        value = {
            "truncated": True,
            "original_chars": len(encoded),
            "preview": encoded[:3800],
        }
    ok = not (isinstance(value, dict) and value.get("ok") is False)
    return value, summary, ok


class _StreamMapper:
    def __init__(self, context: TriageContext) -> None:
        self.context = context
        self.calls: dict[str, tuple[str, float]] = {}

    async def map(self, event: Any) -> None:
        if event.type != "run_item_stream_event":
            return
        item = event.item
        agent_name = getattr(item.agent, "name", "On-Call Data Engineer")
        if item.type == "tool_call_item":
            sdk_tool_name = item.tool_name or "unknown_tool"
            is_mcp = sdk_tool_name.startswith(("datahub_", "mcp_datahub__"))
            tool = (
                f"datahub_{sdk_tool_name.removeprefix('mcp_datahub__')}"
                if sdk_tool_name.startswith("mcp_datahub__")
                else sdk_tool_name
            )
            call_id = item.call_id or f"call-{uuid.uuid4().hex[:10]}"
            raw_arguments = getattr(item.raw_item, "arguments", "{}")
            try:
                args = (
                    json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
                )
            except json.JSONDecodeError:
                args = {"unparsed": str(raw_arguments)[:1000]}
            if not isinstance(args, dict):
                args = {"value": args}
            origin = "mcp" if is_mcp else "subagent" if tool == "author_postmortem" else "native"
            if origin in {"mcp", "subagent"}:
                self.context.tool_calls += 1
            self.calls[call_id] = (tool, time.monotonic())
            await self.context.emit(
                ToolCallEvent(
                    call_id=call_id,
                    tool=tool,
                    origin=origin,
                    args=args,
                    agent=agent_name,
                )
            )
        elif item.type == "tool_call_output_item":
            call_id = item.call_id or "unknown_call"
            tool, started = self.calls.pop(call_id, ("unknown_tool", time.monotonic()))
            payload, summary, ok = _safe_tool_payload(item.output)
            await self.context.emit(
                ToolResultEvent(
                    call_id=call_id,
                    tool=tool,
                    ok=ok,
                    duration_ms=max(0, round((time.monotonic() - started) * 1000)),
                    summary=summary,
                    payload=payload,
                )
            )
        elif item.type == "message_output_item":
            text = ItemHelpers.text_message_output(item)
            if text:
                await self.context.emit(AgentMessageEvent(agent=agent_name, text=text, delta=False))
        elif item.type == "reasoning_item":
            summary = _reasoning_summary(item)
            if summary:
                await self.context.emit(ReasoningEvent(agent=agent_name, summary=summary))


def _trigger_prompt(run_id: str, trigger: TriggerSpec) -> str:
    assertion = trigger.assertion_urn or "none"
    return (
        f"run_id={run_id}\n"
        f"failing_dataset_urn={trigger.dataset_urn}\n"
        f"failing_dataset_name={trigger.name}\n"
        f"signal_kind={trigger.signal_kind}\n"
        f"signal_detail={trigger.signal_detail}\n"
        f"assertion_urn={assertion}\n\n"
        "Execute the complete playbook now. Recall must be the first catalog-memory operation."
    )


def _root_name(context: TriageContext) -> str | None:
    for node in context.causal_path:
        if node.urn == context.root_cause_urn:
            return node.name
    return short_display_name(context.root_cause_urn) if context.root_cause_urn else None


async def run_triage(trigger: TriggerSpec, deps: Deps) -> AsyncIterator[Event]:
    """Yield a complete live event stream while always persisting the drained run."""

    run_id = f"run_{uuid.uuid4().hex[:16]}"
    queue: asyncio.Queue[Event | None] = asyncio.Queue()
    emitter = EventEmitter(run_id, queue)
    active_servers = list(deps.mcp_manager.active_servers) if deps.mcp_manager else []
    context = TriageContext.start(
        run_id=run_id,
        trigger=trigger,
        emitter=emitter,
        store=deps.store,
        dh=deps.dh,
        mcp_available=bool(active_servers),
    )
    await deps.store.create_run(run_id, trigger, scenario=deps.scenario)
    await emitter.emit(
        RunStartedEvent(
            trigger=TriggerPayload(
                dataset_urn=trigger.dataset_urn,
                name=trigger.name,
                signal_kind=trigger.signal_kind,
                signal_detail=trigger.signal_detail,
            ),
            model=deps.settings.agent_model,
        )
    )
    result_ref: dict[str, RunResultStreaming] = {}
    cancel_requested = asyncio.Event()

    async def produce() -> None:
        status = "failed"
        summary = "Triage did not complete."
        error: str | None = None
        try:
            if deps.settings.openai_api_key:
                set_default_openai_key(deps.settings.openai_api_key)
            bundle = build_agents(
                context,
                mcp_servers=active_servers,
                settings=deps.settings,
            )
            result = Runner.run_streamed(
                bundle.triage_agent,
                input=_trigger_prompt(run_id, trigger),
                context=context,
                max_turns=deps.settings.max_turns,
            )
            result_ref["result"] = result
            mapper = _StreamMapper(context)
            async for sdk_event in result.stream_events():
                await mapper.map(sdk_event)
            if result.run_loop_exception is not None:
                raise result.run_loop_exception
            if result.final_output is None:
                raise ModelBehaviorError("Agent stream ended without a final output")
            summary = str(result.final_output)
            status = "cancelled" if cancel_requested.is_set() else "succeeded"
        except asyncio.CancelledError:
            status = "cancelled"
            error = "Run cancelled"
            result = result_ref.get("result")
            if result is not None:
                result.cancel(mode="after_turn")
                try:
                    async for sdk_event in result.stream_events():
                        await _StreamMapper(context).map(sdk_event)
                except Exception:
                    log.debug("Error while draining cancelled agent run", exc_info=True)
        except Exception as exc:
            status = "failed"
            error = f"{type(exc).__name__}: {exc}"
            summary = f"Triage failed: {exc}"
            log.error("Triage run failed run_id=%s error=%s", run_id, error)
            await emitter.emit(ErrorEvent(message=str(exc), where="agent_run"))
        finally:
            duration = round(time.monotonic() - context.started_at, 3)
            hops_walked = max((node.hops_from_symptom for node in context.causal_path), default=0)
            await emitter.emit(MetricEvent(name="tool_calls", value=context.tool_calls))
            await emitter.emit(MetricEvent(name="hops_walked", value=hops_walked))
            public_status = "succeeded" if status == "succeeded" else "failed"
            metrics = RunMetrics(
                time_to_root_cause_s=context.time_to_root_cause_s,
                tool_calls=context.tool_calls,
                hops_walked=hops_walked,
                recall_used=int(bool(context.recalled)),
            )
            await emitter.emit(
                RunCompletedEvent(
                    status=public_status,
                    summary=summary,
                    metrics=metrics,
                    duration_s=duration,
                )
            )
            report = TriageReport(
                run_id=run_id,
                status=status,
                summary=summary,
                root_cause_urn=context.root_cause_urn,
                root_cause_name=_root_name(context),
                incident_urn=context.incident_urn,
                postmortem_id=context.postmortem_id,
                causal_path=context.causal_path,
                blast_radius=context.blast_radius,
                actions=context.actions,
                findings=context.findings,
                tool_calls=context.tool_calls,
                hops_walked=hops_walked,
                recall_used=bool(context.recalled),
                recalled_ids=[item.incident_id for item in context.recalled],
                time_to_root_cause_s=context.time_to_root_cause_s,
                duration_s=duration,
                error=error,
            )
            try:
                await deps.store.append_events(emitter.events)
                await deps.store.finish_run(report)
            except Exception:
                log.exception("Run persistence failed run_id=%s", run_id)
            finally:
                await emitter.close()

    producer = asyncio.create_task(produce(), name=f"triage-{run_id}")
    try:
        while True:
            event = await queue.get()
            if event is None:
                break
            yield event
    except (asyncio.CancelledError, GeneratorExit):
        cancel_requested.set()
        result = result_ref.get("result")
        if result is not None:
            result.cancel(mode="after_turn")
        await asyncio.shield(producer)
        raise
    finally:
        if not producer.done():
            cancel_requested.set()
            result = result_ref.get("result")
            if result is not None:
                result.cancel(mode="after_turn")
            await asyncio.shield(producer)
