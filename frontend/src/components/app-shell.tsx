import { useQuery } from "@tanstack/react-query";
import { Activity, BrainCircuit, ChevronRight, Command, GitCompareArrows, GitFork, Moon, Radar, Sun } from "lucide-react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { cn, formatDuration } from "../lib/utils";
import { useTheme } from "../contexts/theme-context";
import { useLiveRun } from "../contexts/live-run-context";
import { useElapsed } from "../hooks/use-elapsed";
import { DemoControls } from "./demo-controls";
import { Skeleton } from "./ui/skeleton";
import { StatusDot } from "./ui/status-dot";
import { Tooltip } from "./ui/tooltip";

const baseNavigation = [
  { to: "/", label: "Command Deck", icon: Command },
] as const;

const crumbs: Record<string, string> = { "/": "Command Deck", "/lineage": "Lineage Explorer", "/memory": "Agent Memory", "/compare": "Run Compare" };

function ConnectionPill({ label, up, hint }: { label: string; up: boolean; hint: string }) {
  const pill = <StatusDot tone={up ? "ok" : "critical"} label={label} className="w-full justify-start bg-transparent" />;
  return up ? pill : <Tooltip side="right" content={hint}><span className="block">{pill}</span></Tooltip>;
}

export function AppShell() {
  const location = useLocation();
  const navigate = useNavigate();
  const { theme, toggleTheme } = useTheme();
  const { run, phase } = useLiveRun();
  const elapsed = useElapsed(run?.created_at);
  const health = useQuery({ queryKey: ["health"], queryFn: api.health, refetchInterval: 15_000, staleTime: 10_000 });
  const recentRuns = useQuery({ queryKey: ["runs", 1], queryFn: () => api.runs(1), staleTime: 5_000 });
  const navigation = [
    ...baseNavigation,
    { to: recentRuns.data?.[0] ? `/runs/${recentRuns.data[0].id}` : "/", label: "Live Triage", icon: Activity },
    { to: "/lineage", label: "Lineage", icon: GitFork },
    { to: "/memory", label: "Memory", icon: BrainCircuit },
    { to: "/compare", label: "Compare", icon: GitCompareArrows },
  ];
  const runPath = location.pathname.startsWith("/runs/");
  const breadcrumb = runPath ? "Live Triage" : location.pathname.startsWith("/memory/") ? "Memory Detail" : crumbs[location.pathname] ?? "Command Deck";

  return (
    <div className="min-h-screen text-fg">
      <aside className="fixed inset-y-0 left-0 z-30 flex w-[216px] flex-col border-r border-border bg-bg/88 backdrop-blur-xl">
        <div className="flex h-[72px] items-center gap-3 border-b border-border px-5"><span className="relative grid size-9 place-items-center rounded-xl border border-brand/35 bg-brand/10 text-brand"><Radar className="size-[19px]" aria-hidden="true" /><span className="absolute right-1.5 top-1.5 size-1.5 animate-pulse rounded-full bg-info" /></span><div><p className="text-[13px] font-semibold tracking-[-.02em]">On-Call Agent</p><p className="mt-0.5 text-[9px] font-bold uppercase tracking-[.16em] text-fg-subtle">Data Command</p></div></div>
        <nav aria-label="Primary navigation" className="flex-1 px-3 py-5"><p className="mb-2 px-3 text-[9px] font-bold uppercase tracking-[.16em] text-fg-subtle">Workspace</p><div className="space-y-1">{navigation.map((item) => { const Icon = item.icon; return <NavLink key={item.label} to={item.to} end={item.to === "/"} className={({ isActive }) => cn("group flex h-10 items-center gap-3 rounded-lg border px-3 text-xs font-medium transition-all", isActive ? "border-brand/25 bg-brand/10 text-fg" : "border-transparent text-fg-muted hover:bg-surface-2 hover:text-fg")}><Icon className="size-4 text-fg-subtle transition-colors group-hover:text-brand" aria-hidden="true" />{item.label}</NavLink>; })}</div></nav>
        <div className="m-3 rounded-xl border border-border bg-surface/75 p-3"><div className="mb-2 flex items-center justify-between"><p className="text-[9px] font-bold uppercase tracking-[.14em] text-fg-subtle">Connections</p><span className={cn("size-1.5 rounded-full", health.isError ? "bg-critical" : "bg-ok animate-pulse")} /></div>{health.isLoading ? <div className="space-y-2"><Skeleton className="h-7" /><Skeleton className="h-7" /><Skeleton className="h-7" /></div> : <div className="space-y-1"><ConnectionPill label="DataHub" up={health.data?.datahub.status === "up"} hint="Start DataHub GMS on localhost:8081, then refresh this health probe." /><ConnectionPill label="MCP" up={health.data?.mcp.status === "connected"} hint="Restore DataHub first, then restart the backend so the MCP session reconnects." /><ConnectionPill label="Model" up={health.data?.openai.configured === true} hint="Set OPENAI_API_KEY in the repository .env and restart the backend." /></div>}</div>
      </aside>
      <header className="fixed left-[216px] right-0 top-0 z-20 flex h-[72px] items-center justify-between border-b border-border bg-bg/76 px-6 backdrop-blur-xl"><div className="flex items-center gap-2 text-xs"><span className="font-medium text-fg-subtle">On-Call Agent</span><ChevronRight className="size-3 text-border-strong" aria-hidden="true" /><span className="font-semibold text-fg">{breadcrumb}</span></div><div className="flex items-center gap-2">{run && <button type="button" onClick={() => navigate(`/runs/${run.id}`)} className="flex h-8 items-center gap-2 rounded-lg border border-brand/35 bg-brand/10 px-3 text-[11px] font-semibold text-brand transition-colors hover:bg-brand/15"><Activity className="size-3.5 animate-pulse" aria-hidden="true" /><span className="capitalize">{phase.replaceAll("_", " ")}</span><span className="font-mono tabular-nums">{formatDuration(elapsed)}</span></button>}<DemoControls /><Tooltip content={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}><button type="button" onClick={toggleTheme} aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`} className="grid size-8 place-items-center rounded-lg border border-border bg-surface text-fg-muted transition-colors hover:border-border-strong hover:text-fg">{theme === "dark" ? <Sun className="size-3.5" aria-hidden="true" /> : <Moon className="size-3.5" aria-hidden="true" />}</button></Tooltip></div></header>
      <main className="ml-[216px] min-h-screen pt-[72px]"><Outlet /></main>
    </div>
  );
}
