import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowDown, Clipboard, Layers3, Radio, Search, Sparkles, Wrench } from "lucide-react";
import { useReducedMotion } from "motion/react";
import { useParams } from "react-router-dom";
import { api } from "../lib/api";
import type { GraphNode, RunEvent, ToolCallEvent, ToolResultEvent } from "../lib/types";
import { useRunStream } from "../lib/useRunStream";
import { cn, formatDuration, middleTruncate } from "../lib/utils";
import { useLiveRun } from "../contexts/live-run-context";
import { useToast } from "../contexts/toast-context";
import { useElapsed } from "../hooks/use-elapsed";
import { TimelineEvent } from "../components/timeline-event";
import { DatasetDetailDrawer } from "../components/dataset-detail-drawer";
import { LineageCanvas } from "../components/lineage-canvas";
import { LiveRunTabs } from "../components/live-run-tabs";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { EmptyState } from "../components/ui/empty-state";
import { Skeleton } from "../components/ui/skeleton";
import { StatusDot } from "../components/ui/status-dot";
import { Tabs, TabsList, TabsTrigger } from "../components/ui/tabs";
import { Tooltip } from "../components/ui/tooltip";
import { Urn } from "../components/ui/urn";

const phases = ["Recall", "Triage", "Root Cause", "Blast Radius", "Act", "Learn", "Done"] as const;
type TimelineFilter = "all" | "tools" | "findings" | "actions";

function visibleFor(event: RunEvent, filter: TimelineFilter): boolean {
  if (filter === "all") return true;
  if (filter === "tools") return event.kind === "tool_call" || event.kind === "tool_result";
  if (filter === "findings") return event.kind === "finding" || event.kind === "causal_path" || event.kind === "blast_radius";
  return event.kind === "action" || event.kind === "postmortem";
}

function transcriptLine(event: RunEvent): string {
  switch (event.kind) {
    case "phase": return `[${event.seq}] PHASE ${event.phase}: ${event.note}`;
    case "agent_message": return `[${event.seq}] ${event.agent}: ${event.text}`;
    case "reasoning": return `[${event.seq}] THINKING: ${event.summary}`;
    case "tool_call": return `[${event.seq}] TOOL ${event.tool} ${JSON.stringify(event.args)}`;
    case "tool_result": return `[${event.seq}] RESULT ${event.tool} (${event.duration_ms}ms): ${event.summary}`;
    case "finding": return `[${event.seq}] FINDING ${event.name}/${event.check}: ${event.detail}`;
    case "action": return `[${event.seq}] ACTION ${event.action}: ${event.summary}`;
    case "error": return `[${event.seq}] ERROR ${event.where}: ${event.message}`;
    default: return `[${event.seq}] ${event.kind.toUpperCase()}`;
  }
}

export default function LiveTriage() {
  const { id } = useParams<{ id: string }>();
  const run = useQuery({ queryKey: ["run", id], queryFn: () => api.run(id!), enabled: Boolean(id), refetchInterval: (query) => query.state.data?.status === "running" ? 5000 : false, staleTime: 2000 });
  const stream = useRunStream(id);
  const { setPhase } = useLiveRun();
  const { toast } = useToast();
  const reduced = useReducedMotion();
  const [filter, setFilter] = useState<TimelineFilter>("all");
  const [following, setFollowing] = useState(true);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const timelineRef = useRef<HTMLDivElement>(null);
  const elapsed = useElapsed(run.data?.created_at, run.data?.finished_at);
  const graph = useQuery({ queryKey: ["lineage", run.data?.trigger_urn], queryFn: () => api.lineageFocus(run.data!.trigger_urn), enabled: Boolean(run.data?.trigger_urn), staleTime: 30_000 });

  useEffect(() => setPhase(stream.phase), [setPhase, stream.phase]);
  useEffect(() => {
    if (!following || !timelineRef.current) return;
    timelineRef.current.scrollTo({ top: timelineRef.current.scrollHeight, behavior: reduced ? "auto" : "smooth" });
  }, [stream.events.length, following, reduced]);

  const toolResults = useMemo(() => new Map(stream.events.filter((event): event is ToolResultEvent => event.kind === "tool_result").map((event) => [event.call_id, event])), [stream.events]);
  const callIds = useMemo(() => new Set(stream.events.filter((event) => event.kind === "tool_call").map((event) => event.call_id)), [stream.events]);
  const visible = stream.events.filter((event) => visibleFor(event, filter) && (event.kind !== "tool_result" || !callIds.has(event.call_id)));
  const toolCalls = Number(stream.metrics.tool_calls ?? stream.events.filter((event) => event.kind === "tool_call").length);
  const hops = Number(stream.metrics.hops_walked ?? run.data?.hops_walked ?? 0);
  const status = stream.events.length > 0 ? stream.status : run.data?.status ?? "running";
  const inspectingUrn = useMemo(() => {
    if (!graph.data) return null;
    const completed = new Set(stream.events.filter((event): event is ToolResultEvent => event.kind === "tool_result").map((event) => event.call_id));
    const activeCall = [...stream.events].reverse().find((event): event is ToolCallEvent => event.kind === "tool_call" && !completed.has(event.call_id));
    if (!activeCall) return null;
    const args = JSON.stringify(activeCall.args);
    return graph.data.nodes.find((node) => args.includes(node.id))?.id ?? null;
  }, [graph.data, stream.events]);

  if (run.isLoading) return <div className="p-5"><Skeleton className="h-36 rounded-card" /><div className="mt-4 grid grid-cols-[44fr_56fr] gap-4"><Skeleton className="h-[590px] rounded-card" /><Skeleton className="h-[590px] rounded-card" /></div></div>;
  if (run.isError || !run.data) return <div className="p-6"><EmptyState icon={AlertTriangle} title="Run not found" description="This investigation could not be loaded. It may have been purged from local demo storage." action={<Button variant="secondary" onClick={() => window.history.back()}>Go back</Button>} /></div>;

  const copyTranscript = async () => {
    try {
      await navigator.clipboard.writeText(stream.events.map(transcriptLine).join("\n"));
      toast({ tone: "success", title: "Transcript copied", message: `${stream.events.length} timeline events are on your clipboard.` });
    } catch {
      toast({ tone: "error", title: "Copy unavailable", message: "Your browser denied clipboard access." });
    }
  };

  return (
    <div className="p-5"><Card className="p-4"><div className="flex items-start justify-between gap-4"><div className="min-w-0"><div className="flex items-center gap-2"><span className="section-label">Live triage</span>{stream.connection === "reconnecting" && <StatusDot tone="warn" label="Reconnecting" />}{stream.connection === "error" && <StatusDot tone="critical" label="Stream error" />}{stream.connection === "live" && <span className="inline-flex items-center gap-1 text-[9px] font-semibold uppercase tracking-wider text-ok"><Radio className="size-3 animate-pulse" aria-hidden="true" />Live</span>}</div><div className="mt-2 flex min-w-0 items-center gap-2"><Tooltip content={run.data.trigger_name}><h1 className="max-w-[300px] truncate font-mono text-lg font-semibold tracking-[-.03em]">{middleTruncate(run.data.trigger_name, 34)}</h1></Tooltip><Urn value={run.data.trigger_urn} max={42} className="text-[9px]" /></div><p className="mt-1 max-w-[560px] truncate text-[11px] text-fg-muted">{run.data.signal_detail || run.data.signal_kind}</p></div><div className="flex items-center gap-2"><StatusDot tone={status === "succeeded" ? "ok" : status === "running" ? "running" : "critical"} label={status} />{[[formatDuration(elapsed), "elapsed"], [String(toolCalls), "tool calls"], [String(hops), "hops walked"]].map(([value, label]) => <div key={label} className="min-w-[76px] rounded-lg border border-border bg-bg/35 px-3 py-2 text-right"><p className="font-mono text-xs font-semibold text-fg tabular-nums">{value}</p><p className="mt-0.5 text-[8px] font-bold uppercase tracking-wider text-fg-subtle">{label}</p></div>)}</div></div><div className="mt-4 grid grid-cols-7 gap-1.5">{phases.map((phase, index) => { const current = index === stream.phaseIndex && status === "running"; const complete = index < stream.phaseIndex || status === "succeeded"; return <div key={phase} className="min-w-0"><div className={cn("h-1.5 rounded-full transition-colors duration-300", complete ? "bg-brand" : current ? "animate-pulse bg-brand/70" : "bg-surface-2")} /><p className={cn("mt-1.5 truncate text-center text-[8px] font-bold uppercase tracking-[.08em]", complete || current ? "text-brand" : "text-fg-subtle")}>{phase}</p></div>; })}</div></Card>
      <div className="mt-4 grid grid-cols-[44fr_56fr] gap-4 max-[1100px]:grid-cols-1"><Card className="relative flex h-[calc(100vh-256px)] min-h-[620px] min-w-0 flex-col overflow-hidden"><div className="flex h-[52px] shrink-0 items-center justify-between border-b border-border px-3"><Tabs value={filter} onValueChange={(value) => setFilter(value as TimelineFilter)}><TabsList>{(["all", "tools", "findings", "actions"] as const).map((item) => <TabsTrigger key={item} value={item} className="capitalize">{item}</TabsTrigger>)}</TabsList></Tabs><Tooltip content="Copy a readable transcript"><Button variant="ghost" size="sm" onClick={() => void copyTranscript()}><Clipboard className="size-3.5" aria-hidden="true" />Copy</Button></Tooltip></div><div ref={timelineRef} tabIndex={0} onScroll={(event) => { const target = event.currentTarget; setFollowing(target.scrollHeight - target.scrollTop - target.clientHeight < 72); }} className="relative min-h-0 flex-1 overflow-y-auto px-4 py-4" aria-label="Agent reasoning timeline"><div className="pointer-events-none absolute bottom-0 left-[26px] top-0 w-px bg-gradient-to-b from-brand via-border-strong to-transparent" /><div className="space-y-3" role="status" aria-live="polite">{visible.length === 0 ? <EmptyState icon={stream.connection === "error" ? AlertTriangle : filter === "tools" ? Wrench : filter === "findings" ? Search : filter === "actions" ? Sparkles : Layers3} title={stream.connection === "error" ? "Event stream unavailable" : stream.connection === "connecting" ? "Opening event stream" : `No ${filter === "all" ? "timeline events" : filter} yet`} description={stream.connection === "error" ? "The stored replay could not be read. Check the backend and retry this screen." : stream.connection === "connecting" ? "Replaying the stored investigation and attaching to the live agent…" : "Events will appear here as the agent advances through its playbook."} action={stream.connection === "error" ? <Button size="sm" variant="secondary" onClick={() => window.location.reload()}>Retry stream</Button> : undefined} /> : visible.map((event) => <TimelineEvent key={event.seq} event={event} toolResult={event.kind === "tool_call" ? toolResults.get(event.call_id) : undefined} />)}</div></div>{!following && <button type="button" onClick={() => { setFollowing(true); timelineRef.current?.scrollTo({ top: timelineRef.current.scrollHeight, behavior: reduced ? "auto" : "smooth" }); }} className="absolute bottom-4 left-1/2 z-20 flex -translate-x-1/2 items-center gap-1.5 rounded-full border border-brand/35 bg-surface-2 px-3 py-2 text-[10px] font-semibold text-brand shadow-xl"><ArrowDown className="size-3" aria-hidden="true" />Jump to latest</button>}</Card><div className="grid h-[calc(100vh-256px)] min-h-[620px] min-w-0 grid-rows-[minmax(330px,55fr)_minmax(270px,45fr)] gap-4"><Card className="relative min-h-0 overflow-hidden">{graph.isLoading ? <Skeleton className="size-full rounded-none" /> : graph.isError || !graph.data ? <div className="grid size-full place-items-center p-6"><EmptyState icon={AlertTriangle} title="Lineage unavailable" description="The focused graph could not be assembled from DataHub." action={<Button size="sm" variant="secondary" onClick={() => void graph.refetch()}>Retry graph</Button>} /></div> : <><LineageCanvas className="size-full" nodes={graph.data.nodes} edges={graph.data.edges} findings={stream.findings.length ? stream.findings : run.data.findings} causalPath={stream.causalPath.length ? stream.causalPath : run.data.causal_path} blastRadius={stream.blastRadius.length ? stream.blastRadius : run.data.blast_radius} inspectingUrn={inspectingUrn} triggerUrn={run.data.trigger_urn} rootCauseUrn={run.data.root_cause_urn} onNodeClick={setSelectedNode} />{selectedNode && <DatasetDetailDrawer node={selectedNode} edges={graph.data.edges} postmortems={[]} onClose={() => setSelectedNode(null)} />}</>}</Card><Card className="min-h-0 overflow-hidden"><LiveRunTabs findings={stream.findings.length ? stream.findings : run.data.findings} blastRadius={stream.blastRadius.length ? stream.blastRadius : run.data.blast_radius} actions={stream.actions.length ? stream.actions : run.data.actions} postmortemId={stream.postmortem?.postmortem_id ?? run.data.postmortem_id} postmortemEvent={stream.postmortem} /></Card></div></div>
    </div>
  );
}
