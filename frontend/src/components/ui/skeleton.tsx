import { cva } from "class-variance-authority";
import { cn } from "../../lib/utils";

const skeletonStyles = cva("animate-pulse rounded-md bg-surface-2", { variants: { tone: { default: "border border-border/50", brand: "bg-brand/10" } }, defaultVariants: { tone: "default" } });
export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div aria-hidden="true" className={cn(skeletonStyles(), className)} {...props} />;
}
