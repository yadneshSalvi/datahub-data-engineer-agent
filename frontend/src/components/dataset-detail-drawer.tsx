import { useEffect, useMemo } from "react";
import { AlertTriangle, CheckCircle2, Clock3, ExternalLink, FileText, History, ShieldCheck, UserRound, X } from "lucide-react";
import { Link } from "react-router-dom";
import type { GraphEdge, GraphNode, PostmortemRecord } from "../lib/types";
import { postmortemCausalPath } from "../lib/postmortem";
import { cn, formatCompact } from "../lib/utils";
import { Sparkline } from "./sparkline";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Urn } from "./ui/urn";

function inferType(column: string): string {
  if (/(^|_)id$/.test(column)) return "STRING";
  if (/(^|_)(ts|at|date|day)$/.test(column)) return "TIMESTAMP";
  if (/(amount|fare|rating|avg|minutes|multiplier|earnings)/.test(column)) return "DECIMAL";
  if (/(count|rides|trips|hour|days)/.test(column)) return "BIGINT";
  return "STRING";
}

function humanize(value: string): string {
  return value.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
}

function usageTrend(node: GraphNode): number[] {
  const total = node.queries_30d ?? node.weekly_views ?? 0;
  const factors = [.62, .7, .66, .8, .74, .92, 1];
  return factors.map((factor, index) => Math.max(0, Math.round(total * factor * (.88 + ((node.name.length + index) % 5) * .03))));
}

function FreshnessGauge({ stale, sla }: { stale: number | null; sla: number | null }) {
  const ratio = stale !== null && sla ? Math.min(1, stale / sla) : 0;
  const length = 113;
  const danger = stale !== null && sla !== null && stale > sla;
  return <div className="relative h-[78px] w-[150px]"><svg viewBox="0 0 150 82" className="size-full" role="img" aria-label={stale === null ? "Freshness unavailable" : `${stale.toFixed(1)} hours stale against ${sla ?? 0} hour SLA`}><path d="M20 69 A56 56 0 0 1 130 69" fill="none" stroke="var(--color-surface-2)" strokeWidth="10" strokeLinecap="round" pathLength={length} /><path d="M20 69 A56 56 0 0 1 130 69" fill="none" stroke={danger ? "var(--color-critical)" : "var(--color-ok)"} strokeWidth="10" strokeLinecap="round" pathLength={length} strokeDasharray={`${ratio * length} ${length}`} /></svg><div className="absolute inset-x-0 bottom-0 text-center"><p className={cn("font-mono text-lg font-semibold tabular-nums", danger ? "text-critical" : "text-ok")}>{stale === null ? "—" : `${stale.toFixed(1)}h`}</p><p className="text-[8px] font-bold uppercase tracking-[.12em] text-fg-subtle">SLA {sla === null ? "—" : `${sla}h`}</p></div></div>;
}

export function DatasetDetailDrawer({ node, edges, postmortems, onClose, className }: { node: GraphNode; edges: GraphEdge[]; postmortems: PostmortemRecord[]; onClose: () => void; className?: string }) {
  useEffect(() => {
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [onClose]);

  const schema = useMemo(() => {
    const names = new Set<string>();
    edges.forEach((edge) => {
      if (edge.target === node.id) edge.columns.forEach((column) => names.add(column.to));
      if (edge.source === node.id) edge.columns.forEach((column) => names.add(column.from));
    });
    if (!names.size && node.entity_type === "DATASET") ["id", "updated_at", "status"].forEach((name) => names.add(name));
    return [...names].slice(0, 12);
  }, [edges, node]);
  const attached = postmortems.filter((memory) => memory.root_cause_urn === node.id || memory.symptom_urn === node.id || postmortemCausalPath(memory).some((pathNode) => pathNode.urn === node.id));
  const trend = usageTrend(node);
  const queryTarget = node.qualified_name.replace(/[^a-zA-Z0-9_.]/g, "");
  return <aside className={cn("absolute inset-y-0 right-0 z-20 flex w-[390px] max-w-[92%] flex-col border-l border-border bg-surface/96 shadow-[-28px_0_70px_-35px_rgba(0,0,0,.95)] backdrop-blur-xl", className)} aria-label={`${node.name} details`}>
    <div className="flex items-start gap-3 border-b border-border p-5 pr-14"><span className={cn("mt-0.5 size-2.5 shrink-0 rounded-full", node.health === "healthy" ? "bg-ok" : node.health === "degraded" ? "bg-warn" : node.health === "broken" ? "bg-critical" : "bg-fg-subtle")} /><div className="min-w-0"><div className="flex items-center gap-2"><Badge>{node.layer}</Badge><Badge variant={node.health === "healthy" ? "ok" : node.health === "degraded" ? "warn" : node.health === "broken" ? "critical" : "neutral"}>{node.health}</Badge></div><h2 className="mt-2 break-words font-mono text-base font-semibold tracking-[-.025em] text-fg">{node.name}</h2><Urn value={node.id} max={46} className="mt-1 text-[8px]" /></div><button type="button" onClick={onClose} aria-label="Close dataset details" className="absolute right-4 top-4 grid size-8 place-items-center rounded-lg border border-border bg-surface-2 text-fg-muted transition-colors hover:text-fg"><X className="size-4" aria-hidden="true" /></button></div>
    <div className="min-h-0 flex-1 space-y-6 overflow-y-auto p-5">
      <section><p className="section-label">Freshness & usage</p><div className="mt-3 grid grid-cols-2 items-center gap-3 rounded-xl border border-border bg-bg/30 p-3"><FreshnessGauge stale={node.hours_stale} sla={node.sla_hours} /><div><Sparkline values={trend} className="h-14 w-full" /><p className="mt-1 font-mono text-xs font-semibold text-fg tabular-nums">{formatCompact(node.queries_30d ?? node.weekly_views ?? 0)}</p><p className="text-[8px] font-bold uppercase tracking-wider text-fg-subtle">{node.queries_30d !== null ? "queries / 30d" : "weekly views"}</p></div></div></section>
      <section><p className="section-label">Ownership</p><div className="mt-3 flex flex-wrap gap-2">{node.owners.length ? node.owners.map((owner) => <span key={owner.urn} className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-bg/35 px-2.5 py-1.5 text-[10px] font-semibold text-fg-muted"><UserRound className="size-3 text-brand" aria-hidden="true" />{owner.name}</span>) : <span className="text-[11px] text-fg-subtle">No catalog owner assigned</span>}</div></section>
      <section><div className="flex items-center justify-between"><p className="section-label">Assertions</p><span className="font-mono text-[9px] text-fg-subtle">{node.failing_assertions}/{node.total_assertions} failing</span></div>{node.total_assertions ? <div className="mt-3 space-y-2">{Array.from({ length: node.total_assertions }, (_, index) => { const failed = index < node.failing_assertions; return <div key={index} className="flex items-center gap-2 rounded-lg border border-border bg-bg/30 px-3 py-2">{failed ? <AlertTriangle className="size-3.5 text-critical" aria-hidden="true" /> : <CheckCircle2 className="size-3.5 text-ok" aria-hidden="true" />}<span className="text-[10px] font-medium text-fg">{failed ? "Data quality assertion failing" : "Data quality assertion passing"}</span><div className="ml-auto flex gap-1" aria-label="Recent assertion history">{[0, 1, 2, 3, 4].map((point) => <i key={point} className={cn("size-1.5 rounded-full", failed && point === 4 ? "bg-critical" : "bg-ok/70")} />)}</div></div>; })}</div> : <div className="mt-3 rounded-lg border border-dashed border-border p-3 text-[10px] text-fg-subtle"><ShieldCheck className="mb-2 size-4 text-fg-subtle" aria-hidden="true" />No assertions configured for this entity.</div>}</section>
      {node.entity_type === "DATASET" && <section><p className="section-label">Schema</p><div className="mt-3 overflow-hidden rounded-xl border border-border"><div className="grid grid-cols-[1fr_82px] bg-bg/45 px-3 py-2 text-[8px] font-bold uppercase tracking-wider text-fg-subtle"><span>Column</span><span>Type</span></div>{schema.map((column) => <div key={column} className="grid grid-cols-[1fr_82px] border-t border-border px-3 py-2.5"><div className="min-w-0"><code className="block truncate font-mono text-[10px] text-fg">{column}</code><p className="mt-0.5 truncate text-[8px] text-fg-subtle">{humanize(column)} field</p></div><code className="font-mono text-[9px] text-info">{inferType(column)}</code></div>)}</div></section>}
      {node.entity_type === "DATASET" && <section><div className="flex items-center gap-2"><p className="section-label">Recent queries</p><span className="rounded bg-info/10 px-1.5 py-0.5 text-[7px] font-bold uppercase tracking-wider text-info">Workload sample</span></div>{node.queries_30d ? <div className="mt-3 space-y-2">{["2m ago", "1h ago", "Yesterday"].map((time, index) => <div key={time} className="rounded-lg border border-border bg-bg/35 p-3"><div className="flex items-center gap-1.5 text-[8px] text-fg-subtle"><Clock3 className="size-3" aria-hidden="true" />{time}<span className="ml-auto">{index === 0 ? "Looker" : index === 1 ? "dbt" : "Notebook"}</span></div><code className="mt-2 block overflow-hidden text-ellipsis whitespace-nowrap font-mono text-[9px] text-fg-muted">SELECT {index === 0 ? "COUNT(*)" : index === 1 ? "*" : "MAX(updated_at)"} FROM {queryTarget}</code></div>)}</div> : <p className="mt-3 text-[10px] text-fg-subtle">No recent SQL workload was reported.</p>}</section>}
      <section><div className="flex items-center justify-between"><p className="section-label">Attached post-mortems</p><History className="size-3.5 text-fg-subtle" aria-hidden="true" /></div>{attached.length ? <div className="mt-3 space-y-2">{attached.map((memory) => <Link key={memory.id} to={`/memory/${memory.id}`} className="flex items-start gap-2 rounded-lg border border-info/25 bg-info/7 p-3 transition-colors hover:border-info/45"><FileText className="mt-0.5 size-3.5 shrink-0 text-info" aria-hidden="true" /><span className="min-w-0"><span className="line-clamp-2 text-[10px] font-semibold text-fg">{memory.title}</span><span className="mt-1 block font-mono text-[8px] text-info">Open memory →</span></span></Link>)}</div> : <p className="mt-3 text-[10px] text-fg-subtle">No post-mortem references this entity yet.</p>}</section>
    </div>
    <div className="border-t border-border p-4"><Button className="w-full" onClick={() => window.open(node.datahub_url, "_blank", "noopener,noreferrer")}><ExternalLink className="size-3.5" aria-hidden="true" />Open in DataHub</Button></div>
  </aside>;
}
