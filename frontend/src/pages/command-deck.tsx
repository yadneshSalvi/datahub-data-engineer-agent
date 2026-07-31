import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, CheckCircle2, CircleDot, ExternalLink, Inbox, Radar, ShieldCheck, Siren } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import type { GraphNode, Signal } from "../lib/types";
import { cn, formatCompact, formatDuration, middleTruncate, relativeTime } from "../lib/utils";
import { useToast } from "../contexts/toast-context";
import { HealthDonut } from "../components/health-donut";
import { Sparkline } from "../components/sparkline";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card, CardBody, CardHeader } from "../components/ui/card";
import { EmptyState } from "../components/ui/empty-state";
import { Metric } from "../components/ui/metric";
import { Skeleton } from "../components/ui/skeleton";
import { StatusDot } from "../components/ui/status-dot";
import { Tooltip } from "../components/ui/tooltip";
import { Urn } from "../components/ui/urn";

function metricSkeletons() {
  return Array.from({ length: 4 }, (_, index) => <Skeleton key={index} className="h-[132px] rounded-card" />);
}

function OwnerStack({ signal }: { signal: Signal }) {
  if (signal.owners.length === 0) return <span className="text-[10px] text-fg-subtle">Unowned</span>;
  return <div className="flex -space-x-1.5" aria-label={`Owners: ${signal.owners.map((owner) => owner.name).join(", ")}`}>{signal.owners.slice(0, 3).map((owner) => { const initials = owner.name.split(/\s+/).map((part) => part[0]).join("").slice(0, 2).toUpperCase(); return <Tooltip key={owner.urn} content={owner.name}><span className="grid size-7 place-items-center rounded-full border-2 border-surface bg-surface-2 text-[9px] font-bold text-fg-muted">{initials}</span></Tooltip>; })}</div>;
}

function SignalRow({ signal, triaging, onTriage }: { signal: Signal; triaging: boolean; onTriage: (signal: Signal) => void }) {
  const reduceMotion = useReducedMotion();
  const severe = signal.severity === "critical";
  return (
    <motion.article initial={{ opacity: 0, x: reduceMotion ? 0 : -8 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: .18 }} className="group relative grid min-h-[104px] grid-cols-[minmax(0,1fr)_132px] gap-4 overflow-hidden border-b border-border bg-surface px-5 py-4 last:border-b-0 hover:bg-surface-2/45">
      <span className={cn("absolute inset-y-3 left-0 w-[3px] rounded-r-full", severe ? "bg-critical" : "bg-warn")} />
      <div className="min-w-0"><div className="flex min-w-0 items-center gap-2"><Tooltip content={signal.name}><span className="max-w-[230px] truncate font-mono text-[13px] font-semibold text-fg">{middleTruncate(signal.name, 38)}</span></Tooltip><Badge className="py-0.5">{signal.layer}</Badge><Badge variant={severe ? "critical" : "warn"} className="py-0.5">{signal.severity}</Badge></div><p className="mt-2 truncate text-xs font-medium text-fg">{signal.title}</p><div className="mt-1.5 flex min-w-0 items-center gap-2"><span className={cn("size-1.5 shrink-0 rounded-full", severe ? "bg-critical" : "bg-warn")} /><code className="min-w-0 truncate font-mono text-[10px] text-fg-muted">{signal.detail}</code></div><div className="mt-2"><Urn value={signal.dataset_urn} max={62} className="text-[9px] text-fg-subtle" /></div></div>
      <div className="flex flex-col items-end justify-between"><div className="flex items-center gap-2"><OwnerStack signal={signal} /><span className="whitespace-nowrap text-[10px] text-fg-subtle">{relativeTime(signal.detected_at)}</span></div>{signal.triaged_by_run_id ? <Link to={`/runs/${signal.triaged_by_run_id}`} className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-bg/35 px-3 py-2 text-[11px] font-semibold text-fg-muted transition-colors hover:border-brand/35 hover:text-brand"><CheckCircle2 className="size-3 text-ok" aria-hidden="true" />Triaged · view</Link> : <Button size="sm" loading={triaging} onClick={() => onTriage(signal)}>Triage this<ArrowRight className="size-3.5" aria-hidden="true" /></Button>}</div>
    </motion.article>
  );
}

function CatalogSnapshot({ nodes, loading, error }: { nodes: GraphNode[]; loading: boolean; error: boolean }) {
  const health = nodes.reduce((counts, node) => ({ ...counts, [node.health]: counts[node.health] + 1 }), { healthy: 0, degraded: 0, broken: 0, unknown: 0 });
  if (loading) return <Card><CardHeader><Skeleton className="h-4 w-32" /></CardHeader><CardBody><Skeleton className="mx-auto size-28 rounded-full" /><Skeleton className="mt-5 h-20" /></CardBody></Card>;
  if (error) return <Card><CardBody><EmptyState icon={AlertTriangle} title="Catalog unavailable" description="The namespace graph could not be read. Check the DataHub connection." /></CardBody></Card>;
  if (nodes.length === 0) return <Card><CardBody><EmptyState icon={Radar} title="No catalog yet" description="Seed the demo namespace to see its health snapshot." action={<Button size="sm" variant="secondary" onClick={() => window.dispatchEvent(new Event("open-demo-controls"))}>Seed catalog</Button>} /></CardBody></Card>;
  return <Card><CardHeader><div><p className="section-label">Catalog snapshot</p><p className="mt-1 text-xs text-fg-muted">Live namespace health</p></div><Badge variant={health.broken > 0 ? "critical" : health.degraded > 0 ? "warn" : "ok"}>{nodes.length} assets</Badge></CardHeader><CardBody><div className="relative mx-auto w-fit"><HealthDonut healthy={health.healthy} degraded={health.degraded} broken={health.broken} /><div className="absolute inset-0 grid place-items-center text-center"><span><strong className="block font-mono text-xl tabular-nums">{nodes.length}</strong><span className="text-[9px] uppercase tracking-wider text-fg-subtle">entities</span></span></div></div><div className="mt-5 space-y-2">{[["Healthy", health.healthy, "bg-ok"], ["Degraded", health.degraded, "bg-warn"], ["Broken", health.broken, "bg-critical"]].map(([label, value, color]) => <div key={String(label)} className="flex items-center justify-between text-xs"><span className="flex items-center gap-2 text-fg-muted"><span className={cn("size-2 rounded-full", color)} />{label}</span><span className="font-mono text-fg tabular-nums">{value}</span></div>)}</div><a href={nodes[0]?.datahub_url} target="_blank" rel="noreferrer" className="mt-5 flex items-center justify-center gap-1.5 rounded-lg border border-border bg-bg/30 py-2.5 text-xs font-semibold text-fg-muted transition-colors hover:border-brand/35 hover:text-brand">Open in DataHub<ExternalLink className="size-3" aria-hidden="true" /></a></CardBody></Card>;
}

export default function CommandDeck() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [triaging, setTriaging] = useState<string | null>(null);
  const metrics = useQuery({ queryKey: ["metrics"], queryFn: api.metrics, staleTime: 30_000 });
  const signals = useQuery({ queryKey: ["signals"], queryFn: api.signals, staleTime: 5000, refetchInterval: 10_000 });
  const runs = useQuery({ queryKey: ["runs", 50], queryFn: () => api.runs(50), staleTime: 5000, refetchInterval: 10_000 });
  const graph = useQuery({ queryKey: ["lineage", "whole"], queryFn: () => api.lineage(true), staleTime: 30_000 });
  const triage = useMutation({ mutationFn: (signal: Signal) => api.createRun({ dataset_urn: signal.dataset_urn, signal_kind: signal.kind, signal_detail: signal.detail, assertion_urn: signal.assertion_urns[0] }), onMutate: (signal) => setTriaging(signal.id), onSuccess: ({ run_id }) => { void queryClient.invalidateQueries({ queryKey: ["runs"] }); navigate(`/runs/${run_id}`); }, onError: (error) => { const message = error instanceof ApiError ? `${error.message}${error.hint ? ` · ${error.hint}` : ""}` : "The triage run could not be started."; toast({ tone: "error", title: "Triage failed to start", message }); }, onSettled: () => setTriaging(null) });
  const trend = metrics.data?.trend ?? [];
  const firstTime = trend[0]?.time_to_root_cause_s;
  const lastTime = trend.at(-1)?.time_to_root_cause_s;
  const reduction = firstTime && lastTime != null ? Math.round(((firstTime - lastTime) / firstTime) * 100) : null;

  return (
    <div className="mx-auto max-w-[1540px] p-6"><header className="mb-5 flex items-end justify-between"><div><p className="section-label">Live operations</p><h1 className="mt-1 text-2xl font-semibold tracking-[-.02em]">Command Deck</h1><p className="mt-1.5 text-xs text-fg-muted">Signals, active investigations, and the memory loop at a glance.</p></div><div className="flex items-center gap-2"><StatusDot tone={signals.isLoading ? "unknown" : signals.data?.signals.length ? "critical" : "ok"} label={signals.isLoading ? "Checking signals" : signals.data?.signals.length ? `${signals.data.signals.length} signals` : "All clear"} /><span className="rounded-md border border-border bg-surface px-2 py-1 font-mono text-[10px] text-fg-subtle tabular-nums">AUTO · 10s</span></div></header>
      <section aria-label="Key metrics" className="grid grid-cols-4 gap-3">{metrics.isLoading ? metricSkeletons() : metrics.isError || !metrics.data ? <div className="col-span-4"><EmptyState icon={AlertTriangle} title="Metrics are unavailable" description="The command deck could not load run metrics from the backend." action={<Button size="sm" variant="secondary" onClick={() => void metrics.refetch()}>Retry</Button>} /></div> : <><Metric label="Incidents triaged" value={String(metrics.data.runs_succeeded)}><Sparkline values={trend.map((_, index) => index + 1)} /></Metric><Metric label="Avg time to root cause" value={metrics.data.avg_time_to_root_cause_s == null ? "—" : `${metrics.data.avg_time_to_root_cause_s.toFixed(1)}s`} delta={reduction == null ? undefined : `${Math.abs(reduction)}% faster vs first`} deltaGood={(reduction ?? 0) >= 0}><Sparkline values={trend.map((item) => item.time_to_root_cause_s ?? 0)} /></Metric><Metric label="Recall hit rate" value={`${Math.round(metrics.data.recall_hit_rate * 100)}%`}><Sparkline values={trend.map((_, index) => { const seen = trend.slice(0, index + 1); return seen.reduce((sum, item) => sum + item.recall_used, 0) / seen.length; })} /></Metric><Metric label="Downstream assets protected" value={formatCompact(metrics.data.assets_protected)}><Sparkline values={trend.map((_, index) => metrics.data!.assets_protected * ((index + 1) / Math.max(1, trend.length)))} /></Metric></>}
      </section>
      <div className="mt-4 grid grid-cols-[minmax(0,1fr)_300px] gap-4">
        <Card className="min-w-0">
          <CardHeader>
            <div><p className="section-label">Signal inbox</p><h2 className="mt-1 text-sm font-semibold">Needs an engineer’s attention</h2></div>
            {signals.data && <Badge variant={signals.data.signals.length > 0 ? "critical" : "ok"}>{signals.data.signals.length} active</Badge>}
          </CardHeader>
          <div>
            {signals.isLoading ? (
              <div className="space-y-px">{Array.from({ length: 3 }, (_, index) => <div key={index} className="grid h-[104px] grid-cols-[1fr_132px] gap-4 border-b border-border p-5"><div><Skeleton className="h-4 w-52" /><Skeleton className="mt-3 h-3 w-4/5" /><Skeleton className="mt-3 h-3 w-2/3" /></div><Skeleton className="h-8 self-end" /></div>)}</div>
            ) : signals.isError ? (
              <div className="p-5"><EmptyState icon={AlertTriangle} title="Signal feed disconnected" description="The backend could not inspect DataHub health. No signal state is being inferred." action={<Button size="sm" variant="secondary" onClick={() => void signals.refetch()}>Retry feed</Button>} /></div>
            ) : signals.data?.signals.length === 0 ? (
              <div className="p-5"><EmptyState icon={ShieldCheck} title="All clear" description="Every monitored dataset is within its assertions and freshness SLA." action={<Button size="sm" onClick={() => window.dispatchEvent(new Event("open-demo-controls"))}><Siren className="size-3.5" aria-hidden="true" />Arm a scenario</Button>} /></div>
            ) : (
              signals.data?.signals.map((signal) => <SignalRow key={signal.id} signal={signal} triaging={triaging === signal.id} onTriage={(item) => triage.mutate(item)} />)
            )}
          </div>
        </Card>
        <CatalogSnapshot nodes={graph.data?.nodes ?? []} loading={graph.isLoading} error={graph.isError} />
      </div>
      <section className="mt-4"><div className="mb-2.5 flex items-center justify-between"><div><p className="section-label">Recent runs</p><p className="mt-1 text-xs text-fg-muted">Permanent, replayable investigation records</p></div><span className="flex items-center gap-1.5 text-[10px] text-fg-subtle"><CircleDot className="size-3 text-info" aria-hidden="true" />Cyan marks memory-assisted runs</span></div>{runs.isLoading ? <div className="grid grid-cols-3 gap-3">{Array.from({ length: 3 }, (_, index) => <Skeleton key={index} className="h-[132px] rounded-card" />)}</div> : runs.isError ? <EmptyState icon={AlertTriangle} title="Run history unavailable" description="Stored investigations could not be loaded." action={<Button size="sm" variant="secondary" onClick={() => void runs.refetch()}>Retry</Button>} /> : runs.data?.length === 0 ? <EmptyState icon={Inbox} title="No investigations yet" description="Triage an active signal and the run will appear here as a replayable record." /> : <div className="flex snap-x gap-3 overflow-x-auto pb-2">{runs.data?.map((run) => <Link key={run.id} to={`/runs/${run.id}`} className="card-highlight min-w-[310px] snap-start rounded-card border border-border bg-surface p-4 transition-all hover:-translate-y-0.5 hover:border-border-strong"><div className="flex items-center justify-between gap-3"><StatusDot tone={run.status === "succeeded" ? "ok" : run.status === "running" ? "running" : "critical"} label={run.status} />{run.recall_used > 0 && <Badge variant="info">Recall</Badge>}</div><div className="mt-3 flex min-w-0 items-center gap-2 text-xs"><Tooltip content={run.trigger_name}><code className="max-w-[112px] truncate font-mono font-semibold text-fg">{middleTruncate(run.trigger_name, 21)}</code></Tooltip><ArrowRight className="size-3 shrink-0 text-fg-subtle" aria-hidden="true" /><Tooltip content={run.root_cause_name ?? "Investigating"}><code className="min-w-0 truncate font-mono text-fg-muted">{run.root_cause_name ?? "investigating…"}</code></Tooltip></div><div className="mt-4 flex items-center gap-4 border-t border-border pt-3 text-[10px] text-fg-subtle"><span className="font-mono tabular-nums">{formatDuration(run.duration_s)}</span><span>{run.tool_calls} tool calls</span><span className="ml-auto">{relativeTime(run.created_at)}</span></div></Link>)}</div>}</section>
    </div>
  );
}
