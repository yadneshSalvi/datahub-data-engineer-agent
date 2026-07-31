import { createContext, useContext, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { RunRecord } from "../lib/types";

interface LiveRunContextValue { run: RunRecord | null; phase: string; setPhase: (phase: string) => void }
const LiveRunContext = createContext<LiveRunContextValue | null>(null);

export function LiveRunProvider({ children }: { children: React.ReactNode }) {
  const [phase, setPhase] = useState("triage");
  const { data } = useQuery({ queryKey: ["runs", "live"], queryFn: () => api.runs(10), refetchInterval: 5000, staleTime: 2000 });
  const run = data?.find((item) => item.status === "running") ?? null;
  const value = useMemo(() => ({ run, phase, setPhase }), [run, phase]);
  return <LiveRunContext.Provider value={value}>{children}</LiveRunContext.Provider>;
}

export function useLiveRun(): LiveRunContextValue {
  const value = useContext(LiveRunContext);
  if (!value) throw new Error("useLiveRun must be used within LiveRunProvider");
  return value;
}
