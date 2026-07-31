import { cva } from "class-variance-authority";
import { cn } from "../lib/utils";

const donutStyles = cva("size-28 -rotate-90");
export function HealthDonut({ healthy, degraded, broken, className }: { healthy: number; degraded: number; broken: number; className?: string }) {
  const total = Math.max(1, healthy + degraded + broken);
  const circumference = 2 * Math.PI * 36;
  const values = [
    { value: healthy, color: "var(--color-ok)" },
    { value: degraded, color: "var(--color-warn)" },
    { value: broken, color: "var(--color-critical)" },
  ];
  let offset = 0;
  return <svg viewBox="0 0 88 88" className={cn(donutStyles(), className)} role="img" aria-label={`${healthy} healthy, ${degraded} degraded, ${broken} broken assets`}><circle cx="44" cy="44" r="36" fill="none" stroke="var(--color-surface-2)" strokeWidth="9" />{values.map((segment) => { const length = (segment.value / total) * circumference; const circle = <circle key={segment.color} cx="44" cy="44" r="36" fill="none" stroke={segment.color} strokeWidth="9" strokeLinecap="butt" strokeDasharray={`${length} ${circumference - length}`} strokeDashoffset={-offset} />; offset += length; return circle; })}</svg>;
}
