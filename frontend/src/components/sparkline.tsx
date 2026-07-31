import { useId } from "react";
import { cva } from "class-variance-authority";
import { cn } from "../lib/utils";

const chartStyles = cva("h-10 w-24 overflow-visible");

export function Sparkline({ values, className }: { values: number[]; className?: string }) {
  const id = useId().replaceAll(":", "");
  const safe = values.length > 1 ? values : [values[0] ?? 0, values[0] ?? 0];
  const min = Math.min(...safe);
  const max = Math.max(...safe);
  const range = max - min || 1;
  const points = safe.map((value, index) => `${(index / (safe.length - 1)) * 92 + 2},${36 - ((value - min) / range) * 30}`).join(" ");
  const area = `2,38 ${points} 94,38`;
  return (
    <svg viewBox="0 0 96 40" className={cn(chartStyles(), className)} role="img" aria-label={`Trend from ${safe[0]} to ${safe.at(-1)}`}>
      <defs><linearGradient id={id} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="var(--color-brand)" stopOpacity=".28" /><stop offset="1" stopColor="var(--color-brand)" stopOpacity="0" /></linearGradient></defs>
      <polygon points={area} fill={`url(#${id})`} />
      <polyline points={points} fill="none" stroke="var(--color-brand)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="94" cy={points.split(" ").at(-1)?.split(",")[1]} r="2.5" fill="var(--color-bg)" stroke="var(--color-brand)" strokeWidth="2" />
    </svg>
  );
}
