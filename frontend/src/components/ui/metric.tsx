import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import { cva } from "class-variance-authority";
import { cn } from "../../lib/utils";

const metricStyles = cva(
  "card-highlight flex flex-col rounded-card border border-border bg-surface p-5",
  {
    variants: {
      emphasis: {
        default: "",
        good: "border-ok/25",
        alert: "border-critical/25",
      },
    },
    defaultVariants: { emphasis: "default" },
  },
);

export function Metric({
  label,
  value,
  delta,
  deltaGood = true,
  children,
  className,
}: {
  label: string;
  value: string;
  delta?: string;
  deltaGood?: boolean;
  children?: React.ReactNode;
  className?: string;
}) {
  const DeltaIcon = deltaGood ? ArrowDownRight : ArrowUpRight;
  return (
    <div
      className={cn(
        metricStyles({ emphasis: delta ? (deltaGood ? "good" : "alert") : "default" }),
        className,
      )}
    >
      {/* The label owns its own full-width line. Sharing a row with the sparkline clipped
          every tile heading to "INCIDENTS ..." at the recording width. */}
      <p className="section-label leading-tight text-balance">{label}</p>
      <div className="mt-3 flex items-end justify-between gap-4">
        <div className="min-w-0">
          <p className="font-mono text-[28px] font-semibold leading-none tracking-[-.04em] text-fg tabular-nums">
            {value}
          </p>
          {delta && (
            <p
              className={cn(
                "mt-2 inline-flex items-center gap-1 text-[11px] font-semibold",
                deltaGood ? "text-ok" : "text-critical",
              )}
            >
              <DeltaIcon className="size-3" aria-hidden="true" />
              {delta}
            </p>
          )}
        </div>
        {children && <div className="shrink-0">{children}</div>}
      </div>
    </div>
  );
}
