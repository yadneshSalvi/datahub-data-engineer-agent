import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Bot, CheckCircle2, ExternalLink, FileCheck2, MessageSquare, Search, Send, Sparkles } from "lucide-react";
import { api } from "../lib/api";
import { dataHubEntityUrl } from "../lib/postmortem";
import type { ActionData, BlastRadiusItem, FindingData, PostmortemEvent } from "../lib/types";
import { cn } from "../lib/utils";
import { BlastRadiusTable } from "./blast-radius-table";
import { Markdown } from "./markdown";
import { Badge } from "./ui/badge";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "./ui/collapsible";
import { EmptyState } from "./ui/empty-state";
import { Skeleton } from "./ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./ui/tabs";

function findingVariant(verdict: string): "ok" | "warn" | "critical" | "neutral" {
  if (verdict === "healthy" || verdict === "passed") return "ok";
  if (verdict === "broken" || verdict === "failed" || verdict === "root_cause") return "critical";
  if (verdict === "degraded") return "warn";
  return "neutral";
}

function Evidence({ findings }: { findings: FindingData[] }) {
  const groups = useMemo(() => {
    const map = new Map<string, FindingData[]>();
    [...findings].reverse().forEach((finding) => map.set(finding.urn, [...(map.get(finding.urn) ?? []), finding]));
    return [...map.entries()];
  }, [findings]);
  if (!groups.length) return <EmptyState icon={Search} title="Evidence is still arriving" description="Dataset checks and raw measurements appear here as the agent inspects the lineage." className="min-h-48" />;
  return <div className="space-y-3">{groups.map(([urn, items]) => <section key={urn} className="overflow-hidden rounded-xl border border-border bg-bg/25"><div className="flex min-w-0 items-center gap-2 border-b border-border bg-bg/35 px-3.5 py-2.5"><span className={cn("size-2 rounded-full", items.some((item) => findingVariant(item.verdict) === "critical") ? "bg-critical" : items.some((item) => findingVariant(item.verdict) === "warn") ? "bg-warn" : "bg-ok")} /><code className="min-w-0 flex-1 truncate font-mono text-[10px] font-semibold text-fg">{items[0]?.name}</code><span className="font-mono text-[8px] text-fg-subtle">{items.length} checks</span></div><div className="divide-y divide-border">{items.map((finding, index) => <div key={`${finding.check}-${index}`} className="grid grid-cols-[94px_1fr] gap-3 px-3.5 py-2.5"><div><Badge variant={findingVariant(finding.verdict)} className="px-1.5 py-0.5 text-[8px]">{finding.verdict.replaceAll("_", " ")}</Badge><code className="mt-1.5 block truncate font-mono text-[8px] text-fg-subtle">{finding.check}</code></div><p className="text-[10px] leading-relaxed text-fg-muted">{finding.detail}</p></div>)}</div></section>)}</div>;
}

function Actions({ actions, dataHubBase }: { actions: ActionData[]; dataHubBase: string }) {
  if (!actions.length) return <EmptyState icon={Sparkles} title="No write-backs yet" description="Incidents, tags, notifications, and memory artifacts will be listed here in execution order." className="min-h-48" />;
  return <div className="space-y-3">{actions.map((action, index) => {
    const link = action.datahub_url ?? (action.urns[0] ? dataHubEntityUrl(dataHubBase, action.urns[0]) : dataHubBase);
    if (action.action === "notify") return <div key={`${action.action}-${index}`} className="rounded-xl border border-info/30 bg-info/7 p-4"><div className="flex items-center gap-2"><span className="grid size-8 place-items-center rounded-lg bg-[#4a154b] text-white"><MessageSquare className="size-4" aria-hidden="true" /></span><div><p className="text-[10px] font-bold text-fg">on-call-agent <span className="font-normal text-fg-subtle">APP · now</span></p><p className="text-[8px] font-bold uppercase tracking-[.12em] text-info">Owner notification</p></div><Badge variant={action.ok ? "ok" : "critical"} className="ml-auto">{action.ok ? "Delivered" : "Failed"}</Badge></div><div className="mt-3 rounded-lg border-l-2 border-info bg-bg/35 px-3 py-2.5"><p className="text-[11px] font-semibold text-fg">{action.summary}</p><p className="mt-2 whitespace-pre-wrap text-[9px] leading-relaxed text-fg-muted">{action.detail}</p></div><Collapsible><div className="mt-3 flex items-center justify-between"><CollapsibleTrigger>Exact payload</CollapsibleTrigger><a href={link} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[9px] font-semibold text-info hover:underline">Open owner in DataHub<ExternalLink className="size-3" aria-hidden="true" /></a></div><CollapsibleContent className="mt-2"><pre className="max-h-52 overflow-auto whitespace-pre-wrap break-all rounded-lg border border-border bg-bg/60 p-3 font-mono text-[9px] leading-relaxed text-fg-muted">{JSON.stringify(action, null, 2)}</pre></CollapsibleContent></Collapsible></div>;
    return <div key={`${action.action}-${index}`} className={cn("rounded-xl border p-4", action.ok ? "border-ok/25 bg-ok/6" : "border-critical/30 bg-critical/8")}><div className="flex items-start gap-3"><span className={cn("grid size-8 shrink-0 place-items-center rounded-lg border", action.ok ? "border-ok/30 bg-ok/10 text-ok" : "border-critical/30 bg-critical/10 text-critical")}>{action.ok ? <CheckCircle2 className="size-4" aria-hidden="true" /> : <AlertTriangle className="size-4" aria-hidden="true" />}</span><div className="min-w-0 flex-1"><div className="flex items-center gap-2"><p className="text-[9px] font-bold uppercase tracking-[.13em] text-ok">{String(index + 1).padStart(2, "0")} · {action.action}</p><Badge variant={action.ok ? "ok" : "critical"} className="ml-auto py-0.5">{action.ok ? "Written" : "Failed"}</Badge></div><p className="mt-1 text-[11px] font-semibold text-fg">{action.summary}</p><p className="mt-1.5 text-[9px] leading-relaxed text-fg-muted">{action.detail}</p></div></div><Collapsible><div className="mt-3 flex items-center justify-between border-t border-border/70 pt-3"><CollapsibleTrigger>Exact payload</CollapsibleTrigger><a href={link} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[9px] font-semibold text-ok hover:underline">View in DataHub<ExternalLink className="size-3" aria-hidden="true" /></a></div><CollapsibleContent className="mt-2"><pre className="max-h-52 overflow-auto whitespace-pre-wrap break-all rounded-lg border border-border bg-bg/60 p-3 font-mono text-[9px] leading-relaxed text-fg-muted">{JSON.stringify(action, null, 2)}</pre></CollapsibleContent></Collapsible></div>;
  })}</div>;
}

function Postmortem({ id, event }: { id: string | null; event: PostmortemEvent | null }) {
  const query = useQuery({ queryKey: ["postmortem", id], queryFn: () => api.postmortem(id!), enabled: Boolean(id), staleTime: 30_000 });
  if (!id) return <EmptyState icon={FileCheck2} title="Post-mortem pending" description="The agent writes the narrative and DataHub memory artifacts during its Learn phase." className="min-h-48" />;
  if (query.isLoading) return <div className="space-y-3"><Skeleton className="h-16" /><Skeleton className="h-32" /><Skeleton className="h-24" /></div>;
  if (query.isError || !query.data) return <EmptyState icon={AlertTriangle} title="Post-mortem unavailable" description="The stored narrative could not be loaded from the backend mirror." className="min-h-48" />;
  const links = event ? [
    { label: "Structured property", url: event.datahub_urls.structured_property },
    { label: "Document entity", url: event.datahub_urls.document },
    { label: "Institutional link", url: event.datahub_urls.link.includes("localhost:3001") || event.datahub_urls.link.includes(window.location.host) ? event.datahub_urls.structured_property : event.datahub_urls.link },
  ] : [
    { label: "Root-cause property", url: query.data.datahub_links[0] },
    { label: "Document entity", url: query.data.datahub_links[1] },
    { label: "Institutional link", url: query.data.datahub_links[2]?.includes("localhost:3001") || query.data.datahub_links[2]?.includes(window.location.host) ? query.data.datahub_links[0] : query.data.datahub_links[2] },
  ];
  return <div><div className="mb-4 rounded-xl border border-ok/30 bg-ok/8 p-3"><div className="flex items-center gap-2"><FileCheck2 className="size-4 text-ok" aria-hidden="true" /><div><p className="text-[10px] font-bold uppercase tracking-[.12em] text-ok">Written back to DataHub</p><p className="mt-0.5 text-[9px] text-fg-muted">Narrative, structured memory, and entity link are durable catalog artifacts.</p></div></div><div className="mt-3 flex flex-wrap gap-2">{links.map((link) => link.url && <a key={link.label} href={link.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 rounded-md border border-ok/25 bg-bg/35 px-2 py-1 text-[8px] font-semibold text-ok transition-colors hover:bg-ok/10">{link.label}<ExternalLink className="size-2.5" aria-hidden="true" /></a>)}</div></div><Markdown>{query.data.doc_markdown}</Markdown></div>;
}

export function LiveRunTabs({ findings, blastRadius, actions, postmortemId, postmortemEvent }: { findings: FindingData[]; blastRadius: BlastRadiusItem[]; actions: ActionData[]; postmortemId: string | null; postmortemEvent: PostmortemEvent | null }) {
  const config = useQuery({ queryKey: ["config"], queryFn: api.config, staleTime: Infinity });
  const base = config.data?.datahub_ui_url ?? "http://localhost:9002";
  return <Tabs defaultValue="evidence" className="flex h-full min-h-0 flex-col"><div className="flex shrink-0 items-center justify-between border-b border-border px-3 py-2.5"><TabsList className="max-w-full overflow-x-auto">{[["evidence", Search], ["blast", Sparkles], ["actions", Send], ["postmortem", FileCheck2]].map(([value, Icon]) => <TabsTrigger key={String(value)} value={String(value)} className="gap-1.5 whitespace-nowrap px-2.5"><Icon className="size-3" aria-hidden="true" />{value === "blast" ? "Blast Radius" : String(value).replace(/^./, (letter) => letter.toUpperCase())}</TabsTrigger>)}</TabsList><span className="hidden items-center gap-1 text-[8px] font-semibold uppercase tracking-[.12em] text-fg-subtle min-[1450px]:flex"><Bot className="size-3 text-brand" aria-hidden="true" />Run artifacts</span></div><div className="min-h-0 flex-1 overflow-y-auto p-3.5"><TabsContent value="evidence" className="mt-0"><Evidence findings={findings} /></TabsContent><TabsContent value="blast" className="mt-0"><BlastRadiusTable items={blastRadius} dataHubBase={base} compact /></TabsContent><TabsContent value="actions" className="mt-0"><Actions actions={actions} dataHubBase={base} /></TabsContent><TabsContent value="postmortem" className="mt-0"><Postmortem id={postmortemId} event={postmortemEvent} /></TabsContent></div></Tabs>;
}
