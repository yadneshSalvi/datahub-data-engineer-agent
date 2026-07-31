import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowDownRight, ArrowRight, BrainCircuit, CheckCircle2, Clock3, GitCompareArrows, Route, Sparkles, Wrench } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import type { RunEvent, RunRecord } from "../lib/types";
import { cn, formatDuration, middleTruncate } from "../lib/utils";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { EmptyState } from "../components/ui/empty-state";
import { Skeleton } from "../components/ui/skeleton";

interface PhaseGroup { name: string; note: string; tools: string[] }

function condensed(events: RunEvent[]): PhaseGroup[] {
  const groups: PhaseGroup[] = [];
  let current: PhaseGroup = { name: "Recall", note: "Search prior incidents", tools: [] };
  groups.push(current);
  events.forEach((event) => {
    if (event.kind === "phase") {
      current = { name: event.phase.replaceAll("_", " "), note: event.note, tools: [] };
      groups.push(current);
    } else if (event.kind === "tool_call") current.tools.push(event.tool);
  });
  return groups.filter((group, index) => group.tools.length || index === 0 || group.name.toLowerCase() === "done");
}

function metricValue(run: RunRecord, key: "time" | "tools" | "hops"): number {
  return key === "time" ? run.time_to_root_cause_s ?? 0 : key === "tools" ? run.tool_calls : run.hops_walked;
}

function DeltaBar({ label, icon: Icon, a, b, unit = "" }: { label: string; icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>; a: number; b: number; unit?: string }) {
  const reduced = useReducedMotion();
  const max = Math.max(a, b, 1);
  const delta = a - b;
  const pct = a ? (delta / a) * 100 : 0;
  const format = (value: number) => keyValue(label, value, unit);
  return <Card className="p-5"><div className="flex items-start justify-between"><div><div className="flex items-center gap-2"><Icon className="size-4 text-brand" aria-hidden={true} /><p className="text-[10px] font-bold uppercase tracking-[.13em] text-fg-subtle">{label}</p></div><div className="mt-3 flex items-baseline gap-2"><span className="font-mono text-2xl font-semibold tracking-[-.04em] text-ok tabular-nums">{format(b)}</span><span className="text-[9px] text-fg-subtle">with memory</span></div></div><Badge variant={delta >= 0 ? "ok" : "critical"} className="py-1.5"><ArrowDownRight className="size-3" aria-hidden="true" />{Math.abs(pct).toFixed(0)}% {delta >= 0 ? "less" : "more"}</Badge></div><svg viewBox="0 0 420 70" className="mt-4 h-[70px] w-full overflow-visible" role="img" aria-label={`${label}: cold ${format(a)}, with memory ${format(b)}`}><text x="0" y="16" fill="var(--color-fg-subtle)" fontSize="9" fontFamily="var(--font-mono)">COLD</text><rect x="54" y="6" width="350" height="13" rx="6.5" fill="var(--color-bg)" /><motion.rect x="54" y="6" height="13" rx="6.5" fill="var(--color-fg-subtle)" initial={{ width: reduced ? 350 * a / max : 0 }} animate={{ width: 350 * a / max }} transition={{ duration: reduced ? 0 : .55, ease: "easeOut" }} /><text x="0" y="52" fill="var(--color-info)" fontSize="9" fontFamily="var(--font-mono)">RECALL</text><rect x="54" y="42" width="350" height="13" rx="6.5" fill="var(--color-bg)" /><motion.rect x="54" y="42" height="13" rx="6.5" fill="var(--color-info)" initial={{ width: reduced ? 350 * b / max : 0 }} animate={{ width: 350 * b / max }} transition={{ duration: reduced ? 0 : .55, delay: reduced ? 0 : .08, ease: "easeOut" }} /></svg><div className="mt-1 flex items-center justify-between border-t border-border pt-3"><span className="text-[9px] text-fg-subtle">Cold <strong className="font-mono font-semibold text-fg tabular-nums">{format(a)}</strong> → recall <strong className="font-mono font-semibold text-info tabular-nums">{format(b)}</strong></span><span className="font-mono text-[10px] font-semibold text-ok tabular-nums">saved {format(Math.abs(delta))}</span></div></Card>;
}

function keyValue(label: string, value: number, unit: string): string {
  return label.toLowerCase().includes("time") ? formatDuration(value) : `${Number.isInteger(value) ? value : value.toFixed(1)}${unit}`;
}

function RunHeading({ run, memory }: { run: RunRecord; memory: boolean }) {
  return <div className="flex items-start justify-between gap-3"><div className="min-w-0"><div className="flex items-center gap-2"><Badge variant={memory ? "info" : "neutral"}>{memory ? "Run B · with memory" : "Run A · cold"}</Badge>{memory && <Sparkles className="size-3.5 text-info" aria-hidden="true" />}</div><p className="mt-2 truncate font-mono text-xs font-semibold text-fg">{run.trigger_name} → {run.root_cause_name ?? "unknown"}</p><p className="mt-1 font-mono text-[8px] text-fg-subtle">{run.id}</p></div><Link to={`/runs/${run.id}`} className="inline-flex items-center gap-1 rounded-md border border-border bg-bg/35 px-2 py-1 text-[8px] font-semibold text-fg-muted hover:text-brand">Open run<ArrowRight className="size-3" aria-hidden="true" /></Link></div>;
}

function TimelineColumn({ run, events, loading, memory }: { run: RunRecord; events: RunEvent[]; loading: boolean; memory: boolean }) {
  const groups = useMemo(() => condensed(events), [events]);
  if (loading) return <div className="space-y-2">{Array.from({ length: 6 }, (_, index) => <Skeleton key={index} className="h-16" />)}</div>;
  return <div><RunHeading run={run} memory={memory} /><div className="relative mt-5 pl-5"><span className={cn("absolute bottom-2 left-[6px] top-2 w-px", memory ? "bg-gradient-to-b from-info via-info/40 to-transparent" : "bg-gradient-to-b from-fg-subtle via-border to-transparent")} />{groups.map((group, index) => { const counts = new Map<string, number>(); group.tools.forEach((tool) => counts.set(tool, (counts.get(tool) ?? 0) + 1)); const tools = [...counts.entries()]; const proportionalHeight = Math.min(150, 48 + group.tools.length * 1.65); return <div key={`${group.name}-${index}`} className="relative pb-2"><span className={cn("absolute -left-[18px] top-3 z-10 size-2.5 rounded-full border-2 border-surface", memory ? "bg-info" : "bg-fg-subtle")} /><div className={cn("overflow-hidden rounded-lg border bg-bg/28 px-3 py-2.5", memory ? "border-info/22" : "border-border")} style={{ minHeight: `${proportionalHeight}px` }}><div className="flex items-center gap-2"><span className={cn("text-[9px] font-bold uppercase tracking-[.12em]", memory ? "text-info" : "text-fg-muted")}>{group.name}</span><span className="ml-auto font-mono text-[8px] text-fg-subtle tabular-nums">{group.tools.length} calls</span></div><p className="mt-1 truncate text-[8px] text-fg-subtle">{group.note}</p>{tools.length > 0 && <div className="mt-2 space-y-1">{tools.slice(0, 4).map(([tool, count]) => <div key={tool} className="flex min-w-0 items-center gap-1.5"><Wrench className="size-2.5 shrink-0 text-brand" aria-hidden="true" /><code className="min-w-0 flex-1 truncate font-mono text-[8px] text-fg-muted">{middleTruncate(tool, 34)}</code><span className="font-mono text-[7px] text-fg-subtle">×{count}</span></div>)}{tools.length > 4 && <p className="pl-4 text-[7px] text-fg-subtle">+{tools.length - 4} more tool types</p>}</div>}</div></div>; })}<div className="mt-1 flex items-center gap-2 rounded-lg border border-ok/25 bg-ok/7 px-3 py-2"><CheckCircle2 className="size-3.5 text-ok" aria-hidden="true" /><span className="text-[9px] font-semibold text-ok">Root cause confirmed</span><span className="ml-auto font-mono text-[8px] text-fg-muted">{run.tool_calls} total calls</span></div></div></div>;
}

export default function ComparePage() {
  const [selectedA, setSelectedA] = useState("");
  const [selectedB, setSelectedB] = useState("");
  const compare = useQuery({ queryKey: ["compare", selectedA, selectedB], queryFn: () => api.compare(selectedA || undefined, selectedB || undefined), staleTime: 10_000 });
  const runs = useQuery({ queryKey: ["runs", 100], queryFn: () => api.runs(100), staleTime: 5_000 });
  const memories = useQuery({ queryKey: ["postmortems"], queryFn: api.postmortems, staleTime: 30_000 });
  const a = compare.data?.a;
  const b = compare.data?.b;
  const eventsA = useQuery({ queryKey: ["run-events", a?.id], queryFn: () => api.runEvents(a!.id), enabled: Boolean(a?.id), staleTime: Infinity });
  const eventsB = useQuery({ queryKey: ["run-events", b?.id], queryFn: () => api.runEvents(b!.id), enabled: Boolean(b?.id), staleTime: Infinity });
  const recalled = memories.data?.find((memory) => b?.recalled_ids.includes(memory.id));

  if (compare.isLoading) return <div className="p-6"><Skeleton className="h-28 rounded-card" /><div className="mt-4 grid grid-cols-3 gap-4"><Skeleton className="h-[250px] rounded-card" /><Skeleton className="h-[250px] rounded-card" /><Skeleton className="h-[250px] rounded-card" /></div><Skeleton className="mt-4 h-[520px] rounded-card" /></div>;
  if (compare.isError || !a || !b) return <div className="p-6"><EmptyState icon={GitCompareArrows} title="No comparable pair yet" description="Complete one cold triage and one memory-assisted triage sharing a root cause. The comparison will auto-select them." action={<Button variant="secondary" onClick={() => void compare.refetch()}>Retry comparison</Button>} /></div>;

  const currentA = selectedA || a.id;
  const currentB = selectedB || b.id;
  return <div className="p-6"><div className="flex flex-wrap items-start justify-between gap-4"><div><div className="flex items-center gap-2"><span className="section-label">Memory impact</span><Badge variant="info"><BrainCircuit className="size-3" aria-hidden="true" />Cold vs recall</Badge></div><h1 className="mt-2 text-2xl font-semibold tracking-[-.03em] text-fg">Run comparison</h1><p className="mt-2 text-xs text-fg-muted">Same root cause. Less searching. A visibly shorter path to the answer.</p></div><Card className="flex flex-wrap items-end gap-2 p-3"><label><span className="mb-1 block text-[8px] font-bold uppercase tracking-wider text-fg-subtle">Run A · baseline</span><select value={currentA} onChange={(event) => { setSelectedA(event.target.value); if (!selectedB) setSelectedB(currentB); }} className="h-9 w-56 appearance-none rounded-lg border border-border bg-bg/45 px-3 font-mono text-[9px] text-fg"><option value={currentA}>{a.trigger_name} · {a.id.slice(-6)}</option>{runs.data?.filter((run) => run.id !== currentA).map((run) => <option key={run.id} value={run.id}>{run.trigger_name} · {run.id.slice(-6)} · {run.recall_used ? "recall" : "cold"}</option>)}</select></label><span className="mb-2.5 text-fg-subtle">→</span><label><span className="mb-1 block text-[8px] font-bold uppercase tracking-wider text-fg-subtle">Run B · contender</span><select value={currentB} onChange={(event) => { setSelectedB(event.target.value); if (!selectedA) setSelectedA(currentA); }} className="h-9 w-56 appearance-none rounded-lg border border-info/30 bg-info/7 px-3 font-mono text-[9px] text-fg"><option value={currentB}>{b.trigger_name} · {b.id.slice(-6)}</option>{runs.data?.filter((run) => run.id !== currentB).map((run) => <option key={run.id} value={run.id}>{run.trigger_name} · {run.id.slice(-6)} · {run.recall_used ? "recall" : "cold"}</option>)}</select></label></Card></div>
    <div className="mt-5 grid grid-cols-3 gap-4 max-[1050px]:grid-cols-1"><DeltaBar label="Time to root cause" icon={Clock3} a={metricValue(a, "time")} b={metricValue(b, "time")} /><DeltaBar label="Tool calls" icon={Wrench} a={metricValue(a, "tools")} b={metricValue(b, "tools")} /><DeltaBar label="Hops walked" icon={Route} a={metricValue(a, "hops")} b={metricValue(b, "hops")} /></div>
    <Card className="mt-4 overflow-hidden border-info/25"><div className="flex items-center gap-3 bg-gradient-to-r from-info/12 via-info/5 to-transparent px-5 py-4"><span className="grid size-10 place-items-center rounded-xl border border-info/30 bg-info/10 text-info"><Sparkles className="size-5" aria-hidden="true" /></span><div className="min-w-0"><p className="text-[9px] font-bold uppercase tracking-[.14em] text-info">The memory advantage</p><p className="mt-1 text-sm font-semibold text-fg">Run B recalled post-mortem <span className="text-info">“{recalled?.title ?? b.recalled_ids[0] ?? "prior incident"}”</span> and went straight to <code className="font-mono text-critical">{b.root_cause_name ?? "the root cause"}</code>.</p></div><Badge variant="ok" className="ml-auto">{a.tool_calls - b.tool_calls} calls avoided</Badge></div></Card>
    <Card className="mt-4"><div className="grid grid-cols-2 border-b border-border max-[900px]:grid-cols-1"><div className="border-r border-border px-5 py-4 max-[900px]:border-b max-[900px]:border-r-0"><p className="section-label">Cold investigation path</p><p className="mt-1 text-[10px] text-fg-muted">Explores the graph and builds evidence from scratch.</p></div><div className="px-5 py-4"><p className="section-label text-info">Memory-assisted path</p><p className="mt-1 text-[10px] text-fg-muted">Recalls, verifies, and converges on the known source.</p></div></div><div className="grid grid-cols-2 max-[900px]:grid-cols-1"><div className="border-r border-border p-5 max-[900px]:border-b max-[900px]:border-r-0"><TimelineColumn run={a} events={eventsA.data ?? []} loading={eventsA.isLoading} memory={false} /></div><div className="bg-info/[.025] p-5"><TimelineColumn run={b} events={eventsB.data ?? []} loading={eventsB.isLoading} memory /></div></div></Card>
  </div>;
}
