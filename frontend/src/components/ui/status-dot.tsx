import { AlertTriangle, CheckCircle2, CircleHelp, LoaderCircle, XCircle } from "lucide-react";
import { cva } from "class-variance-authority";
import { cn } from "../../lib/utils";

export type StatusTone = "ok" | "warn" | "critical" | "info" | "unknown" | "running";
const statusStyles = cva("inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-[11px] font-semibold", { variants: { tone: { ok: "border-ok/25 bg-ok/8 text-ok", warn: "border-warn/25 bg-warn/8 text-warn", critical: "border-critical/25 bg-critical/8 text-critical", info: "border-info/25 bg-info/8 text-info", unknown: "border-border bg-surface-2 text-fg-subtle", running: "border-brand/30 bg-brand/10 text-brand" } }, defaultVariants: { tone: "unknown" } });
const statusIcons: Record<StatusTone, React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>> = { ok: CheckCircle2, warn: AlertTriangle, critical: XCircle, info: CircleHelp, unknown: CircleHelp, running: LoaderCircle };
export function StatusDot({ tone, label, className }: { tone: StatusTone; label: string; className?: string }) {
  const Icon = statusIcons[tone];
  return <span className={cn(statusStyles({ tone }), className)}><Icon className={cn("size-3.5", tone === "running" && "animate-spin")} aria-hidden={true} />{label}</span>;
}
