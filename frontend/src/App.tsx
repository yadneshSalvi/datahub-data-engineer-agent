import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router-dom";
import { AppShell } from "./components/app-shell";
import { Skeleton } from "./components/ui/skeleton";

const CommandDeck = lazy(() => import("./pages/command-deck"));
const LiveTriage = lazy(() => import("./pages/live-triage"));
const Lineage = lazy(() => import("./pages/lineage"));
const Memory = lazy(() => import("./pages/memory"));
const MemoryDetail = lazy(() => import("./pages/memory-detail"));
const Compare = lazy(() => import("./pages/compare"));
const NotFound = lazy(() => import("./pages/not-found"));

function RouteFallback() {
  return <div className="p-6"><Skeleton className="h-32 rounded-card" /><div className="mt-4 grid grid-cols-3 gap-4"><Skeleton className="col-span-2 h-[520px] rounded-card" /><Skeleton className="h-[520px] rounded-card" /></div></div>;
}

export function App() {
  return <Suspense fallback={<RouteFallback />}><Routes><Route element={<AppShell />}><Route index element={<CommandDeck />} /><Route path="runs/:id" element={<LiveTriage />} /><Route path="lineage" element={<Lineage />} /><Route path="memory" element={<Memory />} /><Route path="memory/:id" element={<MemoryDetail />} /><Route path="compare" element={<Compare />} /><Route path="*" element={<NotFound />} /></Route></Routes></Suspense>;
}
