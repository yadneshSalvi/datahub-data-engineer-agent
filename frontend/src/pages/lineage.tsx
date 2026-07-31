import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Database, GitFork, Layers3, Search, X } from "lucide-react";
import { api } from "../lib/api";
import type { GraphNode } from "../lib/types";
import { cn } from "../lib/utils";
import { DatasetDetailDrawer } from "../components/dataset-detail-drawer";
import { LineageCanvas } from "../components/lineage-canvas";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { EmptyState } from "../components/ui/empty-state";
import { Skeleton } from "../components/ui/skeleton";

const layers: GraphNode["layer"][] = ["raw", "staging", "marts", "ml", "bi"];
const healths: GraphNode["health"][] = ["healthy", "degraded", "broken"];

export default function LineagePage() {
  const graph = useQuery({ queryKey: ["lineage", "whole"], queryFn: () => api.lineage(true), staleTime: 30_000 });
  const memories = useQuery({ queryKey: ["postmortems"], queryFn: api.postmortems, staleTime: 30_000 });
  const [search, setSearch] = useState("");
  const [activeLayers, setActiveLayers] = useState<Set<GraphNode["layer"]>>(new Set(layers));
  const [activeHealth, setActiveHealth] = useState<Set<GraphNode["health"]>>(new Set(healths));
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [focusRequest, setFocusRequest] = useState<string | null>(null);

  const visible = useMemo(() => {
    if (!graph.data) return { nodes: [], edges: [] };
    const nodes = graph.data.nodes.filter((node) => activeLayers.has(node.layer) && (node.health === "unknown" || activeHealth.has(node.health)));
    const ids = new Set(nodes.map((node) => node.id));
    return { nodes, edges: graph.data.edges.filter((edge) => ids.has(edge.source) && ids.has(edge.target)) };
  }, [activeHealth, activeLayers, graph.data]);

  const focusSearch = () => {
    const needle = search.trim().toLowerCase();
    if (!needle || !graph.data) return;
    const match = graph.data.nodes.find((node) => node.name.toLowerCase() === needle) ?? graph.data.nodes.find((node) => `${node.name} ${node.qualified_name} ${node.id}`.toLowerCase().includes(needle));
    if (!match) return;
    if (!activeLayers.has(match.layer)) setActiveLayers((current) => new Set([...current, match.layer]));
    if (match.health !== "unknown" && !activeHealth.has(match.health)) setActiveHealth((current) => new Set([...current, match.health]));
    setFocusRequest(match.id);
    setSelected(match);
  };
  const toggleLayer = (layer: GraphNode["layer"]) => setActiveLayers((current) => { const next = new Set(current); if (next.has(layer)) next.delete(layer); else next.add(layer); return next; });
  const toggleHealth = (health: GraphNode["health"]) => setActiveHealth((current) => { const next = new Set(current); if (next.has(health)) next.delete(health); else next.add(health); return next; });

  return <div className="p-6"><div className="flex flex-wrap items-start justify-between gap-4"><div><div className="flex items-center gap-2"><span className="section-label">Catalog intelligence</span><Badge variant="brand">Whole namespace</Badge></div><h1 className="mt-2 text-2xl font-semibold tracking-[-.03em] text-fg">Lineage Explorer</h1><p className="mt-2 text-xs text-fg-muted">Operational health, column mappings, and institutional memory across the entire on-call namespace.</p></div><div className="grid grid-cols-3 gap-2">{[[graph.data?.nodes.length ?? 0, "entities"], [graph.data?.edges.length ?? 0, "edges"], [graph.data?.nodes.filter((node) => node.health !== "healthy").length ?? 0, "at risk"]].map(([value, label]) => <div key={String(label)} className="min-w-20 rounded-xl border border-border bg-surface px-3 py-2.5 text-right"><p className="font-mono text-sm font-semibold text-fg tabular-nums">{value}</p><p className="mt-0.5 text-[7px] font-bold uppercase tracking-[.12em] text-fg-subtle">{label}</p></div>)}</div></div>
    <Card className="mt-5 flex flex-wrap items-center gap-3 p-3"><form onSubmit={(event) => { event.preventDefault(); focusSearch(); }} className="relative min-w-[260px] flex-1"><Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-fg-subtle" aria-hidden="true" /><label htmlFor="lineage-search" className="sr-only">Search lineage nodes</label><input id="lineage-search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Find a dataset, dashboard, or URN…" className="h-10 w-full rounded-lg border border-border bg-bg/45 pl-10 pr-10 text-xs text-fg placeholder:text-fg-subtle focus:border-brand" />{search && <button type="button" onClick={() => setSearch("")} aria-label="Clear lineage search" className="absolute right-2 top-1/2 grid size-7 -translate-y-1/2 place-items-center rounded-md text-fg-subtle hover:bg-surface-2 hover:text-fg"><X className="size-3.5" aria-hidden="true" /></button>}</form><Button size="sm" onClick={focusSearch}><Search className="size-3.5" aria-hidden="true" />Focus</Button><div className="h-7 w-px bg-border" /><div className="flex items-center gap-1.5"><Layers3 className="mr-1 size-3.5 text-fg-subtle" aria-hidden="true" />{layers.map((layer) => <button key={layer} type="button" aria-pressed={activeLayers.has(layer)} onClick={() => toggleLayer(layer)} className={cn("rounded-md border px-2 py-1.5 text-[9px] font-bold uppercase tracking-[.09em] transition-colors", activeLayers.has(layer) ? "border-brand/35 bg-brand/10 text-brand" : "border-border bg-bg/25 text-fg-subtle hover:text-fg")}>{layer}</button>)}</div><div className="h-7 w-px bg-border" /><div className="flex items-center gap-1.5">{healths.map((health) => <button key={health} type="button" aria-pressed={activeHealth.has(health)} onClick={() => toggleHealth(health)} className={cn("inline-flex items-center gap-1.5 rounded-md border px-2 py-1.5 text-[9px] font-semibold capitalize transition-colors", activeHealth.has(health) ? health === "healthy" ? "border-ok/30 bg-ok/8 text-ok" : health === "degraded" ? "border-warn/30 bg-warn/8 text-warn" : "border-critical/30 bg-critical/8 text-critical" : "border-border bg-bg/25 text-fg-subtle")}><span className={cn("size-1.5 rounded-full", health === "healthy" ? "bg-ok" : health === "degraded" ? "bg-warn" : "bg-critical")} />{health}</button>)}</div></Card>
    <Card className="relative mt-4 h-[calc(100vh-246px)] min-h-[610px] overflow-hidden">{graph.isLoading ? <div className="size-full p-5"><Skeleton className="size-full rounded-xl" /></div> : graph.isError || !graph.data ? <div className="grid size-full place-items-center p-8"><EmptyState icon={AlertTriangle} title="Namespace graph unavailable" description="DataHub could not assemble the lineage graph. The rest of the console remains usable while the catalog reconnects." action={<Button variant="secondary" size="sm" onClick={() => void graph.refetch()}>Retry graph</Button>} /></div> : <><div className="absolute left-4 top-4 z-10 flex items-center gap-2 rounded-lg border border-border bg-surface/85 px-3 py-2 text-[9px] text-fg-muted shadow-lg backdrop-blur"><GitFork className="size-3.5 text-brand" aria-hidden="true" /><span><strong className="font-mono text-fg tabular-nums">{visible.nodes.length}</strong> visible nodes</span><span className="h-3 w-px bg-border" /><span><strong className="font-mono text-fg tabular-nums">{visible.edges.length}</strong> relationships</span></div><LineageCanvas className="size-full" nodes={visible.nodes} edges={visible.edges} focusRequest={focusRequest} onNodeClick={setSelected} emptyLabel="Enable a layer or health filter to bring nodes back into view." />{selected && <DatasetDetailDrawer node={selected} edges={graph.data.edges} postmortems={memories.data ?? []} onClose={() => setSelected(null)} />}</>}</Card>
    <div className="mt-3 flex items-center justify-between text-[9px] text-fg-subtle"><span className="inline-flex items-center gap-1.5"><Database className="size-3" aria-hidden="true" />Click any node for schema, freshness, workload, assertions, and memory.</span><span>Drag to pan · scroll to zoom · hover an edge for column lineage</span></div>
  </div>;
}
