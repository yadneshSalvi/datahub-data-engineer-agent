import { cva } from "class-variance-authority";
import { cn, formatCompact } from "../../lib/utils";

const usageStyles = cva("inline-flex min-w-28 items-center gap-2 font-mono text-[11px] text-fg-muted tabular-nums");
export function UsageBar({ value, max, className }: { value: number; max: number; className?: string }) {
  const width = Math.max(2, Math.min(100, max > 0 ? (value / max) * 100 : 0));
  return <span className={cn(usageStyles(), className)}><svg width="74" height="8" viewBox="0 0 74 8" role="img" aria-label={`${value} usage`}><rect width="74" height="8" rx="4" fill="var(--color-surface-2)" /><rect width={74 * width / 100} height="8" rx="4" fill="var(--color-brand)" /></svg><span>{formatCompact(value)}</span></span>;
}
