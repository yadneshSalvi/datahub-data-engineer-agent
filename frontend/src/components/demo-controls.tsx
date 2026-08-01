import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Database, Flame, History, RotateCcw, ShieldAlert, Sparkles, Trash2 } from "lucide-react";
import { API_URL, ApiError, api } from "../lib/api";
import type { DemoJobAccepted, DemoJobEvent, Scenario } from "../lib/types";
import { cn } from "../lib/utils";
import { useToast } from "../contexts/toast-context";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Dialog, DialogContent, DialogTrigger } from "./ui/dialog";
import { ScrollArea } from "./ui/scroll-area";
import { Separator } from "./ui/separator";
import { Skeleton } from "./ui/skeleton";
import { Spinner } from "./ui/spinner";
import { Switch } from "./ui/switch";
import { useLastKnownGood } from "../hooks/use-last-known-good";

const scenarios: Array<{ id: Scenario; title: string; description: string; icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean }> }> = [
  { id: "stale_upstream", title: "Stale upstream", description: "Stops the raw trips feed and creates a cascading freshness incident.", icon: Flame },
  { id: "recall_hit", title: "Recall hit", description: "Repeats the causal pattern on a new symptom to prove memory compounds.", icon: History },
  { id: "schema_drift", title: "Schema drift", description: "Introduces a distinct source break to demonstrate a fresh diagnosis.", icon: ShieldAlert },
];

function isJobEvent(value: unknown): value is DemoJobEvent {
  return typeof value === "object" && value !== null && "kind" in value && "line" in value && "seq" in value;
}

export function DemoControls() {
  const [open, setOpen] = useState(false);
  const [keepMemory, setKeepMemory] = useState(true);
  const [events, setEvents] = useState<DemoJobEvent[]>([]);
  const [jobLabel, setJobLabel] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const streamRef = useRef<EventSource | null>(null);
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const state = useQuery({ queryKey: ["demo-state"], queryFn: api.demoState, staleTime: 3000, refetchInterval: open ? 5000 : false });
  // Same transient-unseeded window as the Command Deck: never show 0 entities mid-demo.
  const entityCount = useLastKnownGood<number>(state.data?.entity_count ?? 0, (n) => n > 0);

  useEffect(() => () => streamRef.current?.close(), []);
  useEffect(() => {
    const show = () => setOpen(true);
    window.addEventListener("open-demo-controls", show);
    return () => window.removeEventListener("open-demo-controls", show);
  }, []);

  const startStream = (accepted: DemoJobAccepted, label: string) => {
    streamRef.current?.close();
    setEvents([]);
    setJobLabel(label);
    setRunning(true);
    const source = new EventSource(`${API_URL}/api/demo/jobs/${encodeURIComponent(accepted.job_id)}/stream`);
    streamRef.current = source;
    const receive = (event: MessageEvent<string>) => {
      let parsed: unknown;
      try { parsed = JSON.parse(event.data); } catch { return; }
      if (!isJobEvent(parsed)) return;
      setEvents((current) => current.some((item) => item.seq === parsed.seq) ? current : [...current, parsed]);
      if (parsed.kind === "completed" || parsed.kind === "error") {
        source.close();
        setRunning(false);
        void queryClient.invalidateQueries();
        toast({ tone: parsed.kind === "completed" ? "success" : "error", title: parsed.kind === "completed" ? `${label} complete` : `${label} failed`, message: parsed.line });
      }
    };
    source.addEventListener("progress", receive as EventListener);
    source.addEventListener("completed", receive as EventListener);
    source.addEventListener("error", receive as EventListener);
    source.onerror = () => {
      if (source.readyState === EventSource.CLOSED && running) setRunning(false);
    };
  };

  const run = async (label: string, action: () => Promise<DemoJobAccepted>) => {
    try { startStream(await action(), label); }
    catch (error) {
      const message = error instanceof ApiError ? `${error.message}${error.hint ? ` · ${error.hint}` : ""}` : "The backend could not start this demo job.";
      toast({ tone: "error", title: `${label} could not start`, message });
    }
  };

  const progress = [...events].reverse().find((event) => event.step != null && event.total != null);
  const last = events.at(-1);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button variant="secondary" size="sm"><Sparkles className="size-3.5 text-brand" aria-hidden="true" />Demo Controls</Button></DialogTrigger>
      <DialogContent side="right" title="Demo Controls" className="flex h-full flex-col">
        <header className="border-b border-border px-6 pb-5 pt-6">
          <p className="section-label">Operator console</p>
          <div className="mt-2 flex items-end justify-between gap-4"><div><h2 className="text-xl font-semibold tracking-[-.02em]">Demo Controls</h2><p className="mt-1 text-xs text-fg-muted">Shape the catalog state for the live story.</p></div>{state.isLoading ? <Skeleton className="h-7 w-24" /> : state.data && <Badge variant={state.data.healthy ? "ok" : "warn"}>{state.data.healthy ? "Healthy" : "Armed"}</Badge>}</div>
        </header>
        <ScrollArea className="min-h-0 flex-1">
          <div className="space-y-6 px-6 py-6">
            <section><div className="mb-3 flex items-center justify-between"><div><p className="section-label">01 · Foundation</p><h3 className="mt-1 font-semibold">Seed catalog</h3></div><Database className="size-4 text-fg-subtle" aria-hidden="true" /></div><div className="flex items-center justify-between rounded-xl border border-border bg-bg/35 p-4"><div><p className="text-xs font-medium text-fg">Verified demo namespace</p><p className="mt-1 text-[11px] text-fg-subtle">{entityCount} entities currently visible</p></div><Button size="sm" variant="secondary" disabled={running} onClick={() => void run("Catalog seed", api.seed)}>Seed</Button></div></section>
            <Separator />
            <section><p className="section-label">02 · Arm scenario</p><h3 className="mt-1 font-semibold">Choose the incident beat</h3><div className="mt-3 space-y-2">{scenarios.map((scenario) => { const Icon = scenario.icon; const armed = state.data?.armed_scenario === scenario.id; return <button type="button" key={scenario.id} disabled={running} onClick={() => void run(`Arm ${scenario.title}`, () => api.breakScenario(scenario.id))} className={cn("group flex w-full items-center gap-3 rounded-xl border p-3 text-left transition-all duration-200", armed ? "border-brand/50 bg-brand/10" : "border-border bg-bg/25 hover:border-border-strong hover:bg-surface-2", running && "cursor-not-allowed opacity-55")}><span className={cn("grid size-9 shrink-0 place-items-center rounded-lg border", armed ? "border-brand/35 bg-brand/15 text-brand" : "border-border bg-surface text-fg-muted")}><Icon className="size-4" aria-hidden={true} /></span><span className="min-w-0 flex-1"><span className="flex items-center gap-2 text-xs font-semibold text-fg">{scenario.title}{armed && <Badge variant="brand" className="py-0.5">Armed</Badge>}</span><span className="mt-1 block text-[11px] leading-relaxed text-fg-muted">{scenario.description}</span></span></button>; })}</div></section>
            <Separator />
            <section><p className="section-label">03 · Recovery</p><div className="mt-3 rounded-xl border border-border bg-bg/25 p-4"><div className="flex items-center justify-between gap-4"><div><p className="text-xs font-semibold text-fg">Keep agent memory</p><p className="mt-1 text-[11px] text-fg-muted">Heal signals but preserve learned post-mortems.</p></div><Switch checked={keepMemory} onCheckedChange={setKeepMemory} aria-label="Keep agent memory on reset" /></div><div className="mt-4 grid grid-cols-2 gap-2"><Button variant="secondary" size="sm" disabled={running} onClick={() => void run("Demo reset", () => api.reset(keepMemory))}><RotateCcw className="size-3.5" aria-hidden="true" />Reset</Button><Button variant="danger" size="sm" disabled={running} onClick={() => void run("Namespace purge", () => api.reset(false, true))}><Trash2 className="size-3.5" aria-hidden="true" />Purge</Button></div></div></section>
            {(jobLabel || running) && <section className="rounded-xl border border-brand/30 bg-brand/8 p-4" aria-live="polite"><div className="flex items-center justify-between gap-3"><div className="flex items-center gap-2">{running ? <Spinner size="sm" label="" /> : last?.kind === "completed" ? <CheckCircle2 className="size-4 text-ok" aria-hidden="true" /> : <AlertTriangle className="size-4 text-critical" aria-hidden="true" />}<p className="text-xs font-semibold text-fg">{jobLabel}</p></div><span className="font-mono text-[11px] text-fg-muted tabular-nums">{progress ? `${progress.step}/${progress.total}` : running ? "starting" : "done"}</span></div><div className="mt-3 h-1.5 overflow-hidden rounded-full bg-surface-2"><div className="h-full rounded-full bg-brand transition-all duration-300" style={{ width: progress ? `${Math.max(4, (progress.step! / progress.total!) * 100)}%` : running ? "8%" : "100%" }} /></div><div className="mt-3 h-28 overflow-y-auto rounded-lg border border-border bg-bg/60 p-3 font-mono text-[10px] leading-relaxed text-fg-muted">{events.length === 0 ? <span className="text-fg-subtle">Waiting for the first progress event…</span> : events.slice(-12).map((event) => <div key={event.seq} className="flex gap-2"><span className="text-fg-subtle">{event.seq.toString().padStart(2, "0")}</span><span className={event.kind === "error" ? "text-critical" : event.kind === "completed" ? "text-ok" : ""}>{event.line}</span></div>)}</div></section>}
          </div>
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}
