import { AlertTriangle, CheckCircle2, Circle, Info, XCircle } from "lucide-react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/utils";

const badgeStyles = cva("inline-flex w-fit shrink-0 items-center gap-1.5 rounded-md border px-2 py-1 text-[10px] font-bold uppercase tracking-[.09em]", {
  variants: {
    variant: {
      neutral: "border-border bg-surface-2 text-fg-muted",
      brand: "border-brand/35 bg-brand/10 text-brand",
      critical: "border-critical/35 bg-critical/10 text-critical",
      warn: "border-warn/35 bg-warn/10 text-warn",
      ok: "border-ok/35 bg-ok/10 text-ok",
      info: "border-info/35 bg-info/10 text-info",
    },
  },
  defaultVariants: { variant: "neutral" },
});

type BadgeVariant = NonNullable<VariantProps<typeof badgeStyles>["variant"]>;
const icons: Partial<Record<BadgeVariant, React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>>> = {
  brand: Circle,
  critical: XCircle,
  warn: AlertTriangle,
  ok: CheckCircle2,
  info: Info,
};

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeStyles> {
  showIcon?: boolean;
}

export function Badge({ className, variant = "neutral", showIcon, children, ...props }: BadgeProps) {
  const Icon = icons[variant ?? "neutral"];
  const shouldShow = showIcon ?? variant !== "neutral";
  return (
    <span className={cn(badgeStyles({ variant }), className)} {...props}>
      {shouldShow && Icon && <Icon className="size-3" aria-hidden={true} />}
      {children}
    </span>
  );
}
