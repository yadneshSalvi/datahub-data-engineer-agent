import { useEffect, useMemo, useState } from "react";
import dagre from "dagre";
import {
  Background,
  BackgroundVariant,
  EdgeLabelRenderer,
  Handle,
  MarkerType,
  Panel,
  Position,
  ReactFlow,
  getBezierPath,
  useReactFlow,
  type Edge,
  type EdgeProps,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import { Box, Crosshair, Database, LayoutDashboard, Maximize2, Minus, Plus, Search, Sparkles } from "lucide-react";
import type { BlastRadiusItem, CausalNode, FindingData, GraphEdge, GraphNode } from "../lib/types";
import { cn, formatCompact, middleTruncate } from "../lib/utils";
import { Tooltip } from "./ui/tooltip";
import "@xyflow/react/dist/style.css";

const NODE_WIDTH = 216;
const NODE_HEIGHT = 96;

export type LineageNodeState = "idle" | "inspecting" | "healthy" | "degraded" | "broken" | "root_cause" | "impacted";

interface LineageNodeData extends Record<string, unknown> {
  node: GraphNode;
  state: LineageNodeState;
  isSymptom: boolean;
  highlighted: boolean;
}

interface LineageEdgeData extends Record<string, unknown> {
  columns: GraphEdge["columns"];
  tone: "default" | "causal" | "blast";
}

type FlowNode = Node<LineageNodeData, "lineageNode">;
type FlowEdge = Edge<LineageEdgeData, "lineageEdge">;

function nodeIcon(type: GraphNode["entity_type"]) {
  if (type === "DATASET") return Database;
  if (type === "DASHBOARD") return LayoutDashboard;
  if (type === "MLMODEL") return Sparkles;
  return Box;
}

function statText(node: GraphNode): string {
  const count = node.row_count === null ? "— rows" : `${formatCompact(node.row_count)} rows`;
  const age = node.hours_stale === null ? "— stale" : `${node.hours_stale.toFixed(node.hours_stale >= 10 ? 0 : 1)}h stale`;
  const usageValue = node.queries_30d ?? node.weekly_views;
  const usage = usageValue === null ? "— usage" : `${formatCompact(usageValue)} ${node.queries_30d === null ? "views" : "queries"}`;
  return `${count} · ${age} · ${usage}`;
}

function stateLabel(state: LineageNodeState): string {
  return state === "root_cause" ? "root cause" : state.replaceAll("_", " ");
}

function LineageNodeCard({ data }: NodeProps<FlowNode>) {
  const Icon = nodeIcon(data.node.entity_type);
  return (
    <button
      type="button"
      onClick={() => window.dispatchEvent(new CustomEvent("lineage-select", { detail: data.node.id }))}
      className={cn(
        "lineage-node relative h-[96px] w-[216px] rounded-xl border bg-surface/96 px-3.5 py-3 shadow-[0_15px_35px_-25px_rgba(0,0,0,.9)] backdrop-blur transition-[border-color,background-color,box-shadow,transform] duration-[400ms] ease-out",
        data.state === "idle" && "border-border",
        data.state === "healthy" && "border-ok/45",
        data.state === "degraded" && "border-warn/60",
        data.state === "broken" && "border-critical/60",
        data.state === "impacted" && "border-warn ring-2 ring-warn/25",
        data.state === "inspecting" && "border-brand ring-2 ring-brand/35 shadow-[0_0_28px_-12px_var(--color-brand)]",
        data.state === "root_cause" && "border-critical bg-critical/16 ring-2 ring-critical/35 shadow-[0_0_34px_-10px_color-mix(in_oklch,var(--color-critical)_58%,transparent)]",
        data.highlighted && "-translate-y-0.5 ring-2 ring-brand shadow-[0_0_32px_-12px_var(--color-brand)]",
      )}
      aria-label={`${data.node.name}, ${stateLabel(data.state)}`}
    >
      <Handle type="target" position={Position.Left} className="!size-2 !border-bg !bg-border-strong" />
      {data.state === "root_cause" && <span className="absolute -right-1 -top-2 rounded-md border border-critical/50 bg-critical px-2 py-0.5 text-[7px] font-black uppercase tracking-[.14em] text-white shadow-lg">Root cause</span>}
      {data.state === "inspecting" && <span className="absolute -left-1 -top-1 size-3 animate-ping rounded-full bg-brand/70" />}
      <div className="flex items-center gap-2">
        <span className={cn("grid size-6 shrink-0 place-items-center rounded-md border", data.state === "root_cause" ? "border-critical/40 bg-critical/20 text-critical" : "border-border bg-bg/45 text-fg-subtle")}><Icon className="size-3" aria-hidden="true" /></span>
        <span className="rounded-md border border-border bg-bg/40 px-1.5 py-0.5 text-[7px] font-bold uppercase tracking-[.12em] text-fg-subtle">{data.node.layer}</span>
        {data.isSymptom && <span className="ml-auto text-[7px] font-black uppercase tracking-[.13em] text-warn">Symptom</span>}
        <span className={cn("ml-auto size-2 rounded-full ring-2 ring-bg", data.state === "healthy" ? "bg-ok" : data.state === "degraded" || data.state === "impacted" ? "bg-warn" : data.state === "broken" || data.state === "root_cause" ? "bg-critical" : data.state === "inspecting" ? "animate-pulse bg-brand" : "bg-fg-subtle")} />
      </div>
      <p className="mt-2 truncate font-mono text-[11px] font-semibold tracking-[-.02em] text-fg">{middleTruncate(data.node.name, 30)}</p>
      <p className="mt-1 truncate font-mono text-[7.5px] text-fg-subtle tabular-nums">{statText(data.node)}</p>
      <Handle type="source" position={Position.Right} className="!size-2 !border-bg !bg-border-strong" />
    </button>
  );
}

function LineageEdgePath({ id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, markerEnd, data }: EdgeProps<FlowEdge>) {
  const [hovered, setHovered] = useState(false);
  const [path, labelX, labelY] = getBezierPath({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, curvature: .3 });
  const tone = data?.tone ?? "default";
  const columns = data?.columns ?? [];
  return (
    <>
      <path id={id} d={path} fill="none" markerEnd={markerEnd} className={cn("lineage-edge", tone === "causal" ? "lineage-edge-causal" : tone === "blast" ? "lineage-edge-blast" : "lineage-edge-default")} />
      <path d={path} fill="none" stroke="transparent" strokeWidth="16" onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)} className="cursor-help" />
      {hovered && <EdgeLabelRenderer><div className="pointer-events-none absolute z-50 w-max max-w-64 -translate-x-1/2 -translate-y-1/2 rounded-lg border border-border-strong bg-surface-2 px-3 py-2 shadow-2xl" style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)` }}><p className="text-[8px] font-bold uppercase tracking-[.13em] text-fg-subtle">Column lineage</p>{columns.length ? <div className="mt-1.5 space-y-1">{columns.slice(0, 9).map((column, index) => <p key={`${column.from}-${column.to}-${index}`} className="font-mono text-[9px] text-fg-muted"><span className="text-info">{column.from}</span> → {column.to}</p>)}{columns.length > 9 && <p className="text-[9px] text-fg-subtle">+{columns.length - 9} more mappings</p>}</div> : <p className="mt-1 text-[9px] text-fg-muted">Entity-level lineage</p>}</div></EdgeLabelRenderer>}
    </>
  );
}

const nodeTypes = { lineageNode: LineageNodeCard };
const edgeTypes = { lineageEdge: LineageEdgePath };

function layout(nodes: FlowNode[], edges: FlowEdge[]): FlowNode[] {
  const graph = new dagre.graphlib.Graph();
  graph.setDefaultEdgeLabel(() => ({}));
  graph.setGraph({ rankdir: "LR", nodesep: 34, ranksep: 82, edgesep: 26, marginx: 34, marginy: 34, acyclicer: "greedy", ranker: "network-simplex" });
  nodes.forEach((node) => graph.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT }));
  edges.forEach((edge) => graph.setEdge(edge.source, edge.target));
  dagre.layout(graph);
  return nodes.map((node) => {
    const point = graph.node(node.id) as { x: number; y: number };
    return { ...node, position: { x: point.x - NODE_WIDTH / 2, y: point.y - NODE_HEIGHT / 2 } };
  });
}

function CanvasControls({ rootCauseUrn, focusRequest }: { rootCauseUrn?: string | null; focusRequest?: string | null }) {
  const flow = useReactFlow<FlowNode, FlowEdge>();
  useEffect(() => {
    if (!focusRequest) return;
    void flow.fitView({ nodes: [{ id: focusRequest }], duration: 220, padding: .9, maxZoom: 1.3 });
  }, [flow, focusRequest]);
  const focusRoot = () => {
    if (!rootCauseUrn) return;
    void flow.fitView({ nodes: [{ id: rootCauseUrn }], duration: 220, padding: 1.1, maxZoom: 1.25 });
  };
  return <Panel position="top-right" className="!m-3 flex items-center gap-1 rounded-lg border border-border bg-surface/90 p-1 shadow-xl backdrop-blur"><Tooltip content="Fit graph"><button type="button" aria-label="Fit lineage graph" onClick={() => void flow.fitView({ duration: 220, padding: .16 })} className="lineage-control"><Maximize2 className="size-3.5" aria-hidden="true" /></button></Tooltip><Tooltip content="Zoom in"><button type="button" aria-label="Zoom in" onClick={() => void flow.zoomIn({ duration: 180 })} className="lineage-control"><Plus className="size-3.5" aria-hidden="true" /></button></Tooltip><Tooltip content="Zoom out"><button type="button" aria-label="Zoom out" onClick={() => void flow.zoomOut({ duration: 180 })} className="lineage-control"><Minus className="size-3.5" aria-hidden="true" /></button></Tooltip>{rootCauseUrn && <Tooltip content="Focus root cause"><button type="button" aria-label="Focus root cause" onClick={focusRoot} className="lineage-control text-critical"><Crosshair className="size-3.5" aria-hidden="true" /></button></Tooltip>}</Panel>;
}

function Legend() {
  return <Panel position="bottom-left" className="!m-3 flex flex-wrap items-center gap-2 rounded-lg border border-border bg-surface/88 px-2.5 py-1.5 text-[8px] font-semibold uppercase tracking-[.09em] text-fg-subtle backdrop-blur"><span className="mr-1">Health</span><span className="inline-flex items-center gap-1"><i className="size-1.5 rounded-full bg-ok" />Healthy</span><span className="inline-flex items-center gap-1"><i className="size-1.5 rounded-full bg-warn" />Degraded</span><span className="inline-flex items-center gap-1"><i className="size-1.5 rounded-full bg-critical" />Broken</span><span className="inline-flex items-center gap-1 text-critical"><i className="h-px w-4 border-t border-dashed border-critical" />Causal path</span></Panel>;
}

function pairKey(a: string, b: string): string { return [a, b].sort().join("::"); }

export interface LineageCanvasProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  findings?: FindingData[];
  causalPath?: CausalNode[];
  blastRadius?: BlastRadiusItem[];
  inspectingUrn?: string | null;
  triggerUrn?: string | null;
  rootCauseUrn?: string | null;
  focusRequest?: string | null;
  onNodeClick?: (node: GraphNode) => void;
  className?: string;
  emptyLabel?: string;
}

export function LineageCanvas({ nodes, edges, findings = [], causalPath = [], blastRadius = [], inspectingUrn, triggerUrn, rootCauseUrn, focusRequest, onNodeClick, className, emptyLabel = "No lineage nodes match these filters." }: LineageCanvasProps) {
  const [highlightedUrn, setHighlightedUrn] = useState<string | null>(null);
  // Fitting the whole 23-node graph into the run panel drops the zoom to ~0.3, where node labels
  // are unreadable — fatal for a screen recording. When a causal path exists, frame that instead;
  // the "fit graph" control still shows everything.
  const initialFitView = useMemo(() => {
    const path = causalPath.map((node) => ({ id: node.urn }));
    return path.length >= 2
      ? { padding: 0.28, maxZoom: 1.05, minZoom: 0.55, nodes: path }
      : { padding: 0.14, maxZoom: 1.05, minZoom: 0.45 };
  }, [causalPath]);
  useEffect(() => {
    const listener = (raw: Event) => setHighlightedUrn((raw as CustomEvent<string | null>).detail);
    window.addEventListener("lineage-highlight", listener);
    return () => window.removeEventListener("lineage-highlight", listener);
  }, []);
  useEffect(() => {
    const listener = (raw: Event) => {
      const id = (raw as CustomEvent<string>).detail;
      const node = nodes.find((item) => item.id === id);
      if (node) onNodeClick?.(node);
    };
    window.addEventListener("lineage-select", listener);
    return () => window.removeEventListener("lineage-select", listener);
  }, [nodes, onNodeClick]);

  const findingStates = useMemo(() => new Map(findings.map((finding) => [finding.urn, finding.verdict])), [findings]);
  const pathPairs = useMemo(() => new Set(causalPath.slice(1).map((node, index) => pairKey(causalPath[index].urn, node.urn))), [causalPath]);
  const impacted = useMemo(() => new Set(blastRadius.map((item) => item.urn)), [blastRadius]);
  const causalUrns = useMemo(() => new Set(causalPath.map((node) => node.urn)), [causalPath]);

  const flowEdges = useMemo<FlowEdge[]>(() => edges.map((edge) => {
    const causal = pathPairs.has(pairKey(edge.source, edge.target));
    const blast = !causal && (impacted.has(edge.source) || impacted.has(edge.target)) && (causalUrns.has(edge.source) || impacted.has(edge.source));
    const tone: LineageEdgeData["tone"] = causal ? "causal" : blast ? "blast" : "default";
    return { id: edge.id, source: edge.source, target: edge.target, type: "lineageEdge", data: { columns: edge.columns, tone }, markerEnd: { type: MarkerType.ArrowClosed, width: 12, height: 12, color: tone === "causal" ? "var(--color-critical)" : tone === "blast" ? "var(--color-warn)" : "var(--color-border-strong)" } };
  }), [edges, pathPairs, impacted, causalUrns]);

  const flowNodes = useMemo<FlowNode[]>(() => layout(nodes.map((node) => {
    const pathNode = causalPath.find((item) => item.urn === node.id);
    const root = node.id === rootCauseUrn || pathNode?.verdict === "root_cause";
    const finding = findingStates.get(node.id);
    let state: LineageNodeState = node.health === "unknown" ? "idle" : node.health;
    if (impacted.has(node.id)) state = "impacted";
    if (finding === "healthy" || finding === "degraded" || finding === "broken") state = finding;
    if (node.id === inspectingUrn) state = "inspecting";
    if (root) state = "root_cause";
    return { id: node.id, type: "lineageNode", position: { x: 0, y: 0 }, data: { node, state, isSymptom: node.id === triggerUrn, highlighted: highlightedUrn === node.id } };
  }), flowEdges), [nodes, flowEdges, causalPath, rootCauseUrn, findingStates, impacted, inspectingUrn, triggerUrn, highlightedUrn]);

  if (!nodes.length) return <div className={cn("grid place-items-center bg-bg/20 text-center", className)}><div><Search className="mx-auto size-7 text-fg-subtle" aria-hidden="true" /><p className="mt-3 text-xs font-semibold text-fg">Nothing on this layer</p><p className="mt-1 text-[10px] text-fg-muted">{emptyLabel}</p></div></div>;

  return <div className={cn("lineage-canvas relative overflow-hidden bg-bg/25", className)}><ReactFlow<FlowNode, FlowEdge> nodes={flowNodes} edges={flowEdges} nodeTypes={nodeTypes} edgeTypes={edgeTypes} fitView fitViewOptions={initialFitView} minZoom={.22} maxZoom={1.8} nodesConnectable={false} nodesDraggable={false} elementsSelectable onNodeClick={(_event, node) => onNodeClick?.(node.data.node)} proOptions={{ hideAttribution: true }} aria-label="Interactive data lineage graph"><Background variant={BackgroundVariant.Dots} gap={24} size={1} color="var(--color-border)" /><CanvasControls rootCauseUrn={rootCauseUrn} focusRequest={focusRequest} /><Legend /></ReactFlow></div>;
}
