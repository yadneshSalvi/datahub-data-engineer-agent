import { BrainCircuit, GitCompareArrows, GitFork, Layers3, Sparkles } from "lucide-react";
import { useLocation } from "react-router-dom";
import { Badge } from "../components/ui/badge";
import { Card } from "../components/ui/card";

const content = {
  lineage: { icon: GitFork, eyebrow: "Namespace intelligence", title: "Lineage Explorer", description: "Whole-namespace topology, health overlays, asset search, and deep catalog inspection arrive in Slice 5.", bullets: ["23-node directed graph", "Health and layer filters", "Schema, freshness, usage drawer"] },
  memory: { icon: BrainCircuit, eyebrow: "Compounding intelligence", title: "The agent’s memory", description: "Browse every DataHub-backed post-mortem and see exactly where later triages reused it in Slice 5.", bullets: ["Structured memory cards", "Causal-path recall", "Reuse attribution"] },
  compare: { icon: GitCompareArrows, eyebrow: "Proof of learning", title: "Cold vs memory", description: "The side-by-side run comparison and animated time, tool-call, and hop reductions arrive in Slice 5.", bullets: ["Matched incident pairs", "Reduction delta bars", "Condensed timelines"] },
} as const;

export default function ComingSoon() {
  const location = useLocation();
  const key = location.pathname.startsWith("/lineage") ? "lineage" : location.pathname.startsWith("/memory") ? "memory" : "compare";
  const item = content[key];
  const Icon = item.icon;
  return <div className="mx-auto flex min-h-[calc(100vh-72px)] max-w-5xl items-center justify-center p-8"><Card className="relative w-full overflow-hidden p-10"><div className="absolute -right-16 -top-20 size-72 rounded-full bg-brand/10 blur-3xl" /><div className="relative grid grid-cols-[1fr_320px] items-center gap-16"><div><div className="flex items-center gap-3"><span className="grid size-11 place-items-center rounded-xl border border-brand/35 bg-brand/10 text-brand"><Icon className="size-5" aria-hidden="true" /></span><Badge variant="brand">Coming in Slice 5</Badge></div><p className="section-label mt-8">{item.eyebrow}</p><h1 className="mt-2 text-3xl font-semibold tracking-[-.035em]">{item.title}</h1><p className="mt-4 max-w-xl text-sm leading-relaxed text-fg-muted">{item.description}</p></div><div className="rounded-2xl border border-border bg-bg/35 p-5"><div className="mb-5 flex items-center gap-2 text-xs font-semibold text-fg"><Sparkles className="size-4 text-brand" aria-hidden="true" />Next-stage capabilities</div><div className="space-y-3">{item.bullets.map((bullet, index) => <div key={bullet} className="flex items-center gap-3 rounded-lg border border-border bg-surface px-3 py-2.5"><span className="grid size-6 place-items-center rounded-md bg-brand/10 font-mono text-[9px] font-bold text-brand">0{index + 1}</span><span className="text-xs text-fg-muted">{bullet}</span></div>)}</div><div className="mt-5 flex items-center gap-2 border-t border-border pt-4 text-[10px] text-fg-subtle"><Layers3 className="size-3.5" aria-hidden="true" />Foundation route is active and camera-ready</div></div></div></Card></div>;
}
