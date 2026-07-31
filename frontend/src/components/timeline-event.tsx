import { Bot, CheckCircle2, CircleDotDashed, Cog, ExternalLink, GitFork, Hexagon, Lightbulb, Link2, MessageSquare, PencilLine, Play, Radius, ShieldCheck, Siren, Sparkles, Tag, Users, XCircle } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import { Link } from "react-router-dom";
import type { RunEvent, ToolResultEvent } from "../lib/types";
import { cn, middleTruncate } from "../lib/utils";
import { JsonBlock } from "./json-block";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "./ui/collapsible";
import { Spinner } from "./ui/spinner";
import { Tooltip } from "./ui/tooltip";
import { Urn } from "./ui/urn";

function verdictVariant(value: string): "ok" | "warn" | "critical" | "info" {
  if (["healthy", "ok", "passed", "succeeded"].includes(value.toLowerCase())) return "ok";
  if (["degraded", "warning", "unknown"].includes(value.toLowerCase())) return "warn";
  if (["broken", "failed", "root_cause"].includes(value.toLowerCase())) return "critical";
  return "info";
}

function ToolCard({ event, result }: { event: Extract<RunEvent, { kind: "tool_call" }>; result?: ToolResultEvent }) {
  const OriginIcon = event.origin === "mcp" ? Hexagon : event.origin === "subagent" ? PencilLine : Cog;
  const args = Object.entries(event.args).slice(0, 2).map(([key, value]) => `${key}=${typeof value === "string" ? middleTruncate(value, 25) : JSON.stringify(value)}`).join(" · ") || "no arguments";
  return <div className="rounded-xl border border-border bg-surface p-3.5 transition-colors hover:border-border-strong"><div className="flex items-start gap-3"><span className="grid size-8 shrink-0 place-items-center rounded-lg border border-brand/25 bg-brand/8 text-brand"><OriginIcon className="size-4" aria-hidden="true" /></span><div className="min-w-0 flex-1"><div className="flex items-center gap-2"><code className="truncate font-mono text-xs font-semibold text-fg">{event.tool}</code><Badge className="py-0.5">{event.origin}</Badge><span className="ml-auto">{result ? <Badge variant={result.ok ? "ok" : "critical"} className="py-0.5">{result.ok ? "Complete" : "Failed"}</Badge> : <Spinner size="sm" label="Running" />}</span></div><p className="mt-1.5 truncate font-mono text-[9px] text-fg-subtle">{args}</p>{result && <div className="mt-2 flex items-center gap-2"><span className="rounded-md bg-bg/50 px-1.5 py-0.5 font-mono text-[9px] text-fg-muted tabular-nums">{result.duration_ms}ms</span><p className="min-w-0 truncate text-[10px] text-fg-muted">{result.summary}</p></div>}<Collapsible><CollapsibleTrigger className="mt-2.5">Inspect JSON</CollapsibleTrigger><CollapsibleContent className="mt-2 space-y-2"><div><p className="mb-1.5 text-[9px] font-bold uppercase tracking-wider text-fg-subtle">Arguments</p><JsonBlock value={event.args} /></div>{result && <div><p className="mb-1.5 text-[9px] font-bold uppercase tracking-wider text-fg-subtle">Result payload</p><JsonBlock value={result.payload} /></div>}</CollapsibleContent></Collapsible></div></div></div>;
}

function ActionIcon({ action }: { action: string }) {
  const Icon = action === "incident" ? Siren : action === "tag" ? Tag : action === "notify" ? Users : ShieldCheck;
  return <Icon className="size-4" aria-hidden="true" />;
}

export function TimelineEvent({ event, toolResult }: { event: RunEvent; toolResult?: ToolResultEvent }) {
  const reduced = useReducedMotion();
  const animation = { initial: { opacity: 0, x: reduced ? 0 : -8 }, animate: { opacity: 1, x: 0 }, transition: { duration: .18 } };
  let content: React.ReactNode;
  switch (event.kind) {
    case "run_started":
      content = <div className="flex items-center gap-3 rounded-xl border border-brand/25 bg-brand/8 px-4 py-3"><Play className="size-4 text-brand" aria-hidden="true" /><div className="min-w-0"><p className="text-xs font-semibold text-fg">Investigation started</p><p className="mt-1 truncate text-[10px] text-fg-muted">{event.model} · {event.trigger.signal_kind}</p></div></div>;
      break;
    case "phase":
      content = <div className="-ml-2 flex items-center gap-2 rounded-lg border border-brand/30 bg-brand/10 px-3 py-2"><Sparkles className="size-3.5 shrink-0 text-brand" aria-hidden="true" /><span className="text-[10px] font-bold uppercase tracking-[.12em] text-brand">{event.phase.replaceAll("_", " ")}</span><span className="h-3 w-px bg-brand/25" /><span className="min-w-0 truncate text-[10px] text-fg-muted">{event.note}</span></div>;
      break;
    case "agent_message":
      content = <div className="rounded-xl border border-border bg-surface p-4"><div className="mb-2 flex items-center gap-2 text-[10px] font-semibold text-fg-subtle"><Bot className="size-3.5 text-brand" aria-hidden="true" />{event.agent}{event.delta && <span className="size-1.5 animate-pulse rounded-full bg-brand" />}</div><p className="whitespace-pre-wrap text-[12px] leading-relaxed text-fg-muted">{event.text}</p></div>;
      break;
    case "reasoning":
      content = <div className="flex gap-2.5 px-2 py-1 text-[11px] italic leading-relaxed text-fg-subtle"><CircleDotDashed className="mt-0.5 size-3.5 shrink-0 animate-pulse text-brand" aria-hidden="true" /><span>{event.summary}</span></div>;
      break;
    case "tool_call":
      content = <ToolCard event={event} result={toolResult} />;
      break;
    case "tool_result":
      content = <div className={cn("rounded-xl border p-3", event.ok ? "border-ok/25 bg-ok/8" : "border-critical/25 bg-critical/8")}><div className="flex items-center gap-2">{event.ok ? <CheckCircle2 className="size-4 text-ok" aria-hidden="true" /> : <XCircle className="size-4 text-critical" aria-hidden="true" />}<code className="font-mono text-xs text-fg">{event.tool}</code><span className="ml-auto font-mono text-[9px] text-fg-subtle">{event.duration_ms}ms</span></div><p className="mt-2 text-[10px] text-fg-muted">{event.summary}</p></div>;
      break;
    case "recall":
      content = <div className="relative overflow-hidden rounded-xl border border-info/55 bg-info/10 p-4 shadow-[0_0_34px_-20px_var(--color-info)]"><span className="absolute inset-y-0 left-0 w-1 bg-info" /><div className="flex items-center gap-2"><span className="grid size-8 place-items-center rounded-lg border border-info/35 bg-info/15 text-info"><Lightbulb className="size-4" aria-hidden="true" /></span><div><p className="text-xs font-bold text-info">Recalled {event.found} prior post-mortem{event.found === 1 ? "" : "s"}</p><p className="mt-0.5 text-[9px] font-bold uppercase tracking-[.14em] text-info/75">Institutional memory hit</p></div></div>{event.top ? <div className="mt-3 rounded-lg border border-info/20 bg-bg/35 p-3"><p className="font-mono text-[11px] font-semibold text-fg">{event.top.root_cause_name}</p><div className="mt-2 flex items-center gap-2"><Badge variant="info" className="py-0.5">{event.top.relevance.toFixed(1)}% relevant</Badge><span className="text-[10px] text-fg-muted">{event.top.hops_away} hops away</span><Link to={`/memory/${event.top.incident_id}`} className="ml-auto inline-flex items-center gap-1 text-[10px] font-semibold text-info hover:underline">Open memory<Link2 className="size-3" aria-hidden="true" /></Link></div></div> : <p className="mt-3 text-[11px] text-fg-muted">Cold start: no related post-mortem was found. The agent will build new memory.</p>}</div>;
      break;
    case "finding":
      content = <div onMouseEnter={() => window.dispatchEvent(new CustomEvent("lineage-highlight", { detail: event.urn }))} onMouseLeave={() => window.dispatchEvent(new CustomEvent("lineage-highlight", { detail: null }))} className="rounded-xl border border-border bg-surface px-3.5 py-3 transition-colors hover:border-brand/35"><div className="flex min-w-0 items-center gap-2"><Badge variant={verdictVariant(event.verdict)} className="py-0.5">{event.verdict.replaceAll("_", " ")}</Badge><Tooltip content={event.name}><code className="min-w-0 truncate font-mono text-[11px] font-semibold text-fg">{event.name}</code></Tooltip><span className="ml-auto shrink-0 rounded-md bg-bg/45 px-1.5 py-0.5 font-mono text-[9px] text-fg-subtle">{event.check}</span></div><p className="mt-2 text-[10px] leading-relaxed text-fg-muted">{event.detail}</p></div>;
      break;
    case "causal_path":
      content = <div className="rounded-xl border border-critical/30 bg-critical/8 p-4"><div className="flex items-center gap-2 text-xs font-semibold text-critical"><GitFork className="size-4" aria-hidden="true" />Causal path confirmed</div><div className="mt-3 flex flex-wrap items-center gap-1.5">{event.nodes.map((node, index) => <span key={node.urn} className="contents"><Tooltip content={node.urn}><code className={cn("rounded-md border px-2 py-1 font-mono text-[9px]", node.verdict === "root_cause" ? "border-critical/40 bg-critical/15 text-critical" : "border-border bg-bg/35 text-fg-muted")}>{middleTruncate(node.name, 22)}</code></Tooltip>{index < event.nodes.length - 1 && <span className="text-critical/50">→</span>}</span>)}</div></div>;
      break;
    case "blast_radius":
      content = <div className="rounded-xl border border-warn/30 bg-warn/8 p-4"><div className="flex items-center gap-2"><Radius className="size-4 text-warn" aria-hidden="true" /><p className="text-xs font-semibold text-warn">Blast radius mapped</p><Badge variant="warn" className="ml-auto py-0.5">{event.items.length} impacted</Badge></div><p className="mt-2 text-[10px] text-fg-muted">{event.totals.datasets} datasets · {event.totals.charts} charts · {event.totals.dashboards} dashboards · {event.totals.models} models</p></div>;
      break;
    case "action":
      content = <div className={cn("rounded-xl border p-4", event.ok ? "border-ok/35 bg-ok/8" : "border-critical/35 bg-critical/8")}><div className="flex items-center gap-2"><span className={cn("grid size-8 place-items-center rounded-lg border", event.ok ? "border-ok/30 bg-ok/10 text-ok" : "border-critical/30 bg-critical/10 text-critical")}><ActionIcon action={event.action} /></span><div className="min-w-0"><p className="text-[10px] font-bold uppercase tracking-[.12em] text-ok">Write-back · {event.action}</p><p className="mt-0.5 truncate text-xs font-semibold text-fg">{event.summary}</p></div></div>{event.detail && <p className="mt-3 line-clamp-3 text-[10px] leading-relaxed text-fg-muted">{event.detail}</p>}<div className="mt-3 flex items-center gap-2"><Urn value={event.urns[0] ?? "No URN"} max={38} className="text-[9px]" />{event.datahub_url && <a href={event.datahub_url} target="_blank" rel="noreferrer" className="ml-auto inline-flex items-center gap-1 text-[10px] font-semibold text-ok hover:underline">View in DataHub<ExternalLink className="size-3" aria-hidden="true" /></a>}</div></div>;
      break;
    case "postmortem":
      content = <div className="rounded-xl border border-info/30 bg-surface p-4"><div className="flex items-center gap-2"><MessageSquare className="size-4 text-info" aria-hidden="true" /><p className="min-w-0 truncate text-xs font-semibold text-fg">{event.title}</p></div><p className="mt-1.5 text-[10px] text-fg-muted">Post-mortem persisted across three DataHub memory surfaces.</p><div className="mt-3 flex flex-wrap gap-2"><a href={event.datahub_urls.structured_property} target="_blank" rel="noreferrer" className="rounded-md border border-border bg-bg/35 px-2 py-1 text-[9px] font-semibold text-fg-muted hover:text-info">Structured property ↗</a><a href={event.datahub_urls.document} target="_blank" rel="noreferrer" className="rounded-md border border-border bg-bg/35 px-2 py-1 text-[9px] font-semibold text-fg-muted hover:text-info">Document ↗</a><a href={event.datahub_urls.link} className="rounded-md border border-info/25 bg-info/8 px-2 py-1 text-[9px] font-semibold text-info">Open post-mortem</a></div></div>;
      break;
    case "metric":
      content = <div className="flex items-center gap-2 px-2 py-1 text-[10px] text-fg-subtle"><span className="size-1.5 rounded-full bg-brand" /><span>{event.name.replaceAll("_", " ")}</span><span className="ml-auto font-mono text-fg-muted tabular-nums">{event.value}</span></div>;
      break;
    case "run_completed":
      content = <div className={cn("rounded-xl border p-4", event.status === "succeeded" ? "border-ok/35 bg-ok/8" : "border-critical/35 bg-critical/8")}><div className="flex items-center gap-2">{event.status === "succeeded" ? <CheckCircle2 className="size-4 text-ok" aria-hidden="true" /> : <XCircle className="size-4 text-critical" aria-hidden="true" />}<p className="text-xs font-semibold text-fg">Run {event.status}</p><Badge variant={event.status === "succeeded" ? "ok" : "critical"} className="ml-auto py-0.5">{event.duration_s.toFixed(1)}s</Badge></div><p className="mt-3 text-[10px] leading-relaxed text-fg-muted">{event.summary}</p></div>;
      break;
    case "error":
      content = <div className="rounded-xl border border-critical/45 bg-critical/10 p-4"><div className="flex items-center gap-2"><XCircle className="size-4 text-critical" aria-hidden="true" /><p className="text-xs font-semibold text-critical">Agent error · {event.where}</p></div><p className="mt-2 text-[11px] leading-relaxed text-fg-muted">{event.message}</p><Button className="mt-3" size="sm" variant="danger" onClick={() => window.location.reload()}>Retry stream</Button></div>;
      break;
  }
  return <motion.div {...animation} className="relative pl-7"><span className="absolute left-[7px] top-4 z-10 size-2.5 rounded-full border-2 border-bg bg-border-strong" />{content}</motion.div>;
}
