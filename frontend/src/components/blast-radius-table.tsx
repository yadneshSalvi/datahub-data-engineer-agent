import { Box, Database, ExternalLink, LayoutDashboard, Sparkles, UserRound } from "lucide-react";
import type { BlastRadiusItem } from "../lib/types";
import { dataHubEntityUrl } from "../lib/postmortem";
import { formatCompact, middleTruncate } from "../lib/utils";
import { Badge } from "./ui/badge";
import { EmptyState } from "./ui/empty-state";
import { Tooltip } from "./ui/tooltip";
import { UsageBar } from "./ui/usage-bar";

function iconFor(type: BlastRadiusItem["entity_type"]) {
  if (type === "DATASET") return Database;
  if (type === "DASHBOARD") return LayoutDashboard;
  if (type === "MLMODEL") return Sparkles;
  return Box;
}

function severityVariant(value: BlastRadiusItem["severity"]): "critical" | "warn" | "neutral" {
  return value === "critical" ? "critical" : value === "high" || value === "medium" ? "warn" : "neutral";
}

export function BlastRadiusTable({ items, dataHubBase, compact = false }: { items: BlastRadiusItem[]; dataHubBase: string; compact?: boolean }) {
  if (!items.length) return <EmptyState icon={Sparkles} title="Blast radius not mapped" description="Ranked downstream impact will appear when the agent completes its lineage walk." className="min-h-48" />;
  const max = Math.max(...items.map((item) => item.usage_score), 1);
  const totals = items.reduce((counts, item) => ({ ...counts, [item.entity_type]: counts[item.entity_type] + 1 }), { DATASET: 0, CHART: 0, DASHBOARD: 0, MLMODEL: 0 });
  const modelCount = totals.MLMODEL || items.filter((item) => /(^|_)features($|_)/i.test(item.name)).length;
  const usage = items.reduce((sum, item) => sum + item.usage_score, 0);
  return <div className="min-w-0"><div className="mb-3 flex flex-wrap items-center justify-between gap-2"><p className="text-[11px] font-semibold text-fg"><span className="font-mono text-warn tabular-nums">{items.length}</span> assets · <span className="font-mono tabular-nums">{totals.DASHBOARD}</span> dashboards · <span className="font-mono tabular-nums">{modelCount}</span> ML model{modelCount === 1 ? "" : "s"} · <span className="font-mono tabular-nums">{formatCompact(usage)}</span> usage/30d</p><Badge variant="warn">Ranked by usage</Badge></div><div className="overflow-x-auto rounded-xl border border-border"><table className="w-full min-w-[760px] table-fixed border-collapse text-left"><thead className="bg-bg/55"><tr className="text-[8px] font-bold uppercase tracking-[.12em] text-fg-subtle"><th className="w-12 px-3 py-2.5">#</th><th className="w-[36%] px-3 py-2.5">Asset</th><th className="w-24 px-3 py-2.5">Severity</th><th className="w-16 px-3 py-2.5 text-center">Hops</th><th className="w-44 px-3 py-2.5">Usage</th><th className="px-3 py-2.5">Owners</th><th className="w-10 px-2 py-2.5"><span className="sr-only">DataHub</span></th></tr></thead><tbody>{items.map((item, index) => { const Icon = iconFor(item.entity_type); return <tr key={item.urn} className="border-t border-border bg-surface transition-colors hover:bg-surface-2/50"><td className="px-3 py-2.5 font-mono text-[9px] text-fg-subtle tabular-nums">{String(index + 1).padStart(2, "0")}</td><td className="px-3 py-2.5"><div className="flex min-w-0 items-center gap-2"><span className="grid size-7 shrink-0 place-items-center rounded-md border border-border bg-bg/40 text-fg-subtle"><Icon className="size-3.5" aria-hidden="true" /></span><div className="min-w-0"><Tooltip content={item.name}><code className="block truncate font-mono text-[10px] font-semibold text-fg">{middleTruncate(item.name, compact ? 24 : 34)}</code></Tooltip><span className="text-[7px] font-bold uppercase tracking-[.11em] text-fg-subtle">{item.entity_type}</span></div></div></td><td className="px-3 py-2.5"><Badge variant={severityVariant(item.severity)} className="px-1.5 py-0.5 text-[8px]">{item.severity}</Badge></td><td className="px-3 py-2.5 text-center font-mono text-[10px] text-fg-muted tabular-nums">{item.hops}</td><td className="px-3 py-2.5"><UsageBar value={item.usage_score} max={max} /></td><td className="px-3 py-2.5"><div className="flex min-w-0 items-center gap-1.5 text-[9px] text-fg-muted">{item.owners.length ? <><UserRound className="size-3 shrink-0 text-brand" aria-hidden="true" /><span className="truncate">{item.owners.join(" · ")}</span></> : <span className="text-fg-subtle">Unowned</span>}</div></td><td className="px-2 py-2.5"><a href={dataHubEntityUrl(dataHubBase, item.urn)} target="_blank" rel="noreferrer" aria-label={`Open ${item.name} in DataHub`} className="grid size-7 place-items-center rounded-md border border-border bg-bg/30 text-fg-subtle transition-colors hover:border-brand/35 hover:text-brand"><ExternalLink className="size-3.5" aria-hidden="true" /></a></td></tr>; })}</tbody></table></div></div>;
}
