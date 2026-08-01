"""Standalone CLI for signals, live triage, stored runs, and offline replay."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

from oncall_agent.agent.context import DataHubFacade
from oncall_agent.agent.events import Event
from oncall_agent.agent.models import TriggerSpec
from oncall_agent.agent.runner import Deps, run_triage
from oncall_agent.agent.tools_mcp import build_mcp_manager
from oncall_agent.config import Settings, get_settings
from oncall_agent.datahub.urns import short_display_name
from oncall_agent.store import Store

log = logging.getLogger(__name__)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_RESET = "\033[0m"
_COLORS = {
    "dim": "\033[2m",
    "cyan": "\033[36m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
    "magenta": "\033[35m",
    "bold": "\033[1m",
}


def _color(text: str, color: str) -> str:
    if not sys.stdout.isatty():
        return text
    return f"{_COLORS[color]}{text}{_RESET}"


def _event_line(event: Event) -> str:
    prefix = f"{event.seq:03d} {event.kind:14}"
    if event.kind == "run_started":
        body = f"{event.trigger.name} · {event.trigger.signal_kind} · model={event.model}"
    elif event.kind == "phase":
        body = f"[{event.phase_index + 1}/7] {event.phase.upper()} — {event.note}"
    elif event.kind == "agent_message":
        body = f"{event.agent}: {event.text}"
    elif event.kind == "reasoning":
        body = f"{event.agent}: {event.summary}"
    elif event.kind == "tool_call":
        body = f"{event.origin}:{event.tool} {json.dumps(event.args, ensure_ascii=False)}"
    elif event.kind == "tool_result":
        body = (
            f"{event.tool} {'ok' if event.ok else 'failed'} {event.duration_ms}ms · {event.summary}"
        )
    elif event.kind == "recall":
        body = (
            f"found={event.found} top={event.top.root_cause_name} "
            f"hops={event.top.hops_away} relevance={event.top.relevance:.1f}"
            if event.top
            else "cold start — no prior post-mortems"
        )
    elif event.kind == "finding":
        body = f"{event.name} · {event.check}={event.verdict} · {event.detail}"
    elif event.kind == "causal_path":
        body = " → ".join(node.name for node in event.nodes)
    elif event.kind == "blast_radius":
        body = f"{len(event.items)} ranked assets · totals={event.totals.model_dump()}"
    elif event.kind == "action":
        body = f"{event.action} {'ok' if event.ok else 'failed'} · {event.summary}"
    elif event.kind == "postmortem":
        body = f"{event.postmortem_id} · {event.title} · {event.datahub_urls.document}"
    elif event.kind == "metric":
        body = f"{event.name}={event.value}"
    elif event.kind == "error":
        body = f"{event.where}: {event.message}"
    else:
        body = f"{event.status} · {event.summary}"
    palette = {
        "phase": "magenta",
        "finding": "cyan",
        "action": "yellow",
        "postmortem": "green",
        "run_completed": "green" if getattr(event, "status", "") == "succeeded" else "red",
        "error": "red",
        "reasoning": "dim",
    }
    return f"{_color(prefix, palette.get(event.kind, 'dim'))} {body}"


def render_event(event: Event) -> None:
    """Render one live or replayed event using the same timeline representation."""

    print(_event_line(event), flush=True)
    if event.kind == "run_completed":
        print(f"time_to_root_cause_s={event.metrics.time_to_root_cause_s}", flush=True)
        print(f"tool_calls={event.metrics.tool_calls}", flush=True)


def _signal_detail(record: dict[str, Any]) -> str:
    messages = [
        str(item.get("message"))
        for item in record.get("health") or []
        if item.get("status") == "FAIL" and item.get("message")
    ]
    return " · ".join(messages) or "Data-quality signal is failing"


def _signal_kind(record: dict[str, Any]) -> str:
    return "assertion" if record.get("assertion_urns") else "freshness"


def _scenario_name() -> str | None:
    directory = _REPOSITORY_ROOT / "data" / "scenarios"
    if not directory.exists():
        return None
    receipts = sorted(directory.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not receipts:
        return None
    try:
        return str(json.loads(receipts[0].read_text(encoding="utf-8")).get("scenario"))
    except (OSError, json.JSONDecodeError):
        return None


def _choose_auto_signal(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        raise RuntimeError("No open oncall signals were found")
    scenario = _scenario_name()
    preferred = {
        "stale_upstream": "agg_daily_rides",
        "recall_hit": "agg_zone_demand",
        "schema_drift": "dim_driver",
    }.get(scenario)
    if preferred:
        selected = next((item for item in records if item.get("name") == preferred), None)
        if selected is not None:
            return selected
    assertion_records = [item for item in records if item.get("assertion_urns")]
    return (assertion_records or records)[0]


async def _signals() -> int:
    records = await asyncio.to_thread(DataHubFacade().get_health_signals)
    print(f"open_signals={len(records)}")
    for item in records:
        kind = _signal_kind(item)
        detail = _signal_detail(item)
        print(f"{kind:10} {item['name']:24} {detail}")
        print(f"           {item['dataset_urn']}")
    return 0


async def _triage(args: argparse.Namespace, settings: Settings) -> int:
    facade = DataHubFacade()
    scenario = _scenario_name()
    if args.auto:
        records = await asyncio.to_thread(facade.get_health_signals)
        record = _choose_auto_signal(records)
        trigger = TriggerSpec(
            dataset_urn=record["dataset_urn"],
            name=record["name"],
            signal_kind=_signal_kind(record),
            signal_detail=_signal_detail(record),
            assertion_urn=(record.get("assertion_urns") or [None])[0],
        )
    else:
        trigger = TriggerSpec(
            dataset_urn=args.urn,
            name=short_display_name(args.urn),
            signal_kind=args.signal,
            signal_detail=f"Manual {args.signal} triage requested from CLI",
        )
    store = await Store.open(settings.db_path)
    manager = None
    entered = False
    try:
        if settings.mcp_enabled:
            manager = build_mcp_manager(settings)
            try:
                await manager.__aenter__()
                entered = True
                if not manager.active_servers:
                    log.warning("MCP unavailable; native lineage fallback enabled")
            except Exception as exc:
                log.warning("MCP unavailable; native lineage fallback enabled: %s", exc)
                manager = None
        deps = Deps(
            store=store,
            dh=facade,
            mcp_manager=manager,
            settings=settings,
            scenario=scenario,
        )
        failed = False
        async for event in run_triage(trigger, deps):
            render_event(event)
            if event.kind == "run_completed" and event.status != "succeeded":
                failed = True
        return 1 if failed else 0
    finally:
        if manager is not None and entered:
            await manager.__aexit__(None, None, None)
        await store.close()


async def _runs(settings: Settings) -> int:
    store = await Store.open(settings.db_path)
    try:
        rows = await store.list_runs()
    finally:
        await store.close()
    print(f"runs={len(rows)}")
    for row in rows:
        print(
            f"{row['id']} {row['status']:9} {row['trigger_name']:22} "
            f"root={row.get('root_cause_name') or '-'} "
            f"tool_calls={row.get('tool_calls') or 0} "
            f"time_to_root_cause_s={row.get('time_to_root_cause_s')} "
            f"recall_used={row.get('recall_used') or 0}"
        )
    return 0


async def _replay(run_id: str, settings: Settings) -> int:
    store = await Store.open(settings.db_path)
    try:
        events = await store.get_events(run_id)
    finally:
        await store.close()
    if not events:
        raise RuntimeError(f"Run not found or has no events: {run_id}")
    for event in events:
        render_event(event)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("signals", help="print the health-derived alert inbox")
    triage = commands.add_parser("triage", help="run a live agent triage")
    target = triage.add_mutually_exclusive_group(required=True)
    target.add_argument("--urn", help="explicit failing dataset URN")
    target.add_argument(
        "--auto", action="store_true", help="select the demo's highest-priority signal"
    )
    triage.add_argument("--signal", choices=("assertion", "freshness"), default="assertion")
    commands.add_parser("runs", help="list stored runs and metrics")
    replay = commands.add_parser("replay", help="re-render a run without network or OpenAI")
    replay.add_argument("run_id")
    return parser


async def _main_async(args: argparse.Namespace) -> int:
    settings = get_settings()
    if args.command == "signals":
        return await _signals()
    if args.command == "triage":
        return await _triage(args, settings)
    if args.command == "runs":
        return await _runs(settings)
    return await _replay(args.run_id, settings)


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and execute one CLI command."""

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    try:
        return asyncio.run(_main_async(_parser().parse_args(argv)))
    except KeyboardInterrupt:
        print("cancelled", file=sys.stderr)
        return 130
    except Exception as exc:
        log.error("CLI command failed: %s: %s", type(exc).__name__, exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
