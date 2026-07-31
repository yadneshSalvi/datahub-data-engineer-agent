import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/app-shell";
import { Skeleton } from "./components/ui/skeleton";

const CommandDeck = lazy(() => import("./pages/command-deck"));
const ComingSoon = lazy(() => import("./pages/coming-soon"));
const LiveTriage = lazy(() => import("./pages/live-triage"));

function RouteFallback() {
  return <div className="p-6"><Skeleton className="h-32 rounded-card" /><div className="mt-4 grid grid-cols-3 gap-4"><Skeleton className="col-span-2 h-[520px] rounded-card" /><Skeleton className="h-[520px] rounded-card" /></div></div>;
}

export function App() {
  return <Suspense fallback={<RouteFallback />}><Routes><Route element={<AppShell />}><Route index element={<CommandDeck />} /><Route path="runs/:id" element={<LiveTriage />} /><Route path="lineage" element={<ComingSoon />} /><Route path="memory" element={<ComingSoon />} /><Route path="memory/:id" element={<ComingSoon />} /><Route path="compare" element={<ComingSoon />} /><Route path="*" element={<Navigate to="/" replace />} /></Route></Routes></Suspense>;
}
