import { useId } from "react";
import { cva } from "class-variance-authority";
import { cn } from "../lib/utils";

const chartStyles = cva("h-10 w-24 overflow-visible");
const left = 2;
const right = 94;
const top = 5;
const bottom = 35;
const baseline = 38;

interface Point { x: number; y: number }

function chartPoints(values: number[]): Point[] {
  if (values.length === 0) return [];
  if (values.length === 1) return [{ x: (left + right) / 2, y: (top + bottom) / 2 }];
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min;
  return values.map((value, index) => ({ x: left + (index / (values.length - 1)) * (right - left), y: range === 0 ? (top + bottom) / 2 : bottom - ((value - min) / range) * (bottom - top) }));
}

function monotonePath(points: Point[]): string {
  if (points.length === 0) return "";
  if (points.length === 1) return `M ${points[0].x} ${points[0].y}`;
  const slopes = points.slice(0, -1).map((point, index) => (points[index + 1].y - point.y) / (points[index + 1].x - point.x));
  const tangents = points.map((_, index) => index === 0 ? slopes[0] : index === points.length - 1 ? slopes.at(-1)! : slopes[index - 1] * slopes[index] <= 0 ? 0 : (slopes[index - 1] + slopes[index]) / 2);
  slopes.forEach((slope, index) => {
    if (slope === 0) { tangents[index] = 0; tangents[index + 1] = 0; return; }
    const a = tangents[index] / slope;
    const b = tangents[index + 1] / slope;
    const magnitude = a * a + b * b;
    if (magnitude <= 9) return;
    const scale = 3 / Math.sqrt(magnitude);
    tangents[index] = scale * a * slope;
    tangents[index + 1] = scale * b * slope;
  });
  return points.slice(0, -1).reduce((path, point, index) => {
    const next = points[index + 1];
    const width = next.x - point.x;
    return `${path} C ${point.x + width / 3} ${point.y + tangents[index] * width / 3}, ${next.x - width / 3} ${next.y - tangents[index + 1] * width / 3}, ${next.x} ${next.y}`;
  }, `M ${points[0].x} ${points[0].y}`);
}

export function Sparkline({ values, className, label }: { values: number[]; className?: string; label?: string }) {
  const id = useId().replaceAll(":", "");
  const points = chartPoints(values);
  const path = monotonePath(points);
  const sparse = values.length < 3;
  const ariaLabel = label ?? (values.length === 0 ? "No measurements available" : `${values.length} real measurement${values.length === 1 ? "" : "s"}; latest value ${values.at(-1)}`);
  return (
    <svg viewBox="0 0 96 40" className={cn(chartStyles(), className)} role="img" aria-label={ariaLabel}>
      {values.length === 0 ? <line x1={left} y1="20" x2={right} y2="20" stroke="var(--color-fg-subtle)" strokeOpacity=".55" strokeWidth="1" strokeDasharray="3 3" /> : <>
        {!sparse && <><defs><linearGradient id={id} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="var(--color-brand)" stopOpacity=".28" /><stop offset="1" stopColor="var(--color-brand)" stopOpacity="0" /></linearGradient></defs><path d={`${path} L ${points.at(-1)!.x} ${baseline} L ${points[0].x} ${baseline} Z`} fill={`url(#${id})`} /></>}
        {points.length > 1 && <path d={sparse ? `M ${points.map((point) => `${point.x} ${point.y}`).join(" L ")}` : path} fill="none" stroke="var(--color-brand)" strokeOpacity={sparse ? ".35" : "1"} strokeWidth={sparse ? "1" : "2"} strokeLinecap="round" strokeLinejoin="round" />}
        {points.slice(0, -1).map((point, index) => <circle key={index} cx={point.x} cy={point.y} r="1.6" fill="var(--color-brand)" />)}
        <circle cx={points.at(-1)!.x} cy={points.at(-1)!.y} r="2.5" fill="var(--color-bg)" stroke="var(--color-brand)" strokeWidth="2" />
      </>}
    </svg>
  );
}
