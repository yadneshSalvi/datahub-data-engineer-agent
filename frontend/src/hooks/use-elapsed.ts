import { useEffect, useState } from "react";

export function useElapsed(startedAt: string | undefined, finishedAt?: string | null): number {
  const calculate = () => {
    if (!startedAt) return 0;
    const end = finishedAt ? new Date(finishedAt).getTime() : Date.now();
    return Math.max(0, (end - new Date(startedAt).getTime()) / 1000);
  };
  const [elapsed, setElapsed] = useState(calculate);
  useEffect(() => {
    setElapsed(calculate());
    if (!startedAt || finishedAt) return;
    const timer = window.setInterval(() => setElapsed(calculate()), 1000);
    return () => window.clearInterval(timer);
  }, [startedAt, finishedAt]);
  return elapsed;
}
