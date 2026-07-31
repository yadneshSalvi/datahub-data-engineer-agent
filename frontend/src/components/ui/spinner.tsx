import { LoaderCircle } from "lucide-react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/utils";

const spinnerStyles = cva("animate-spin text-brand", { variants: { size: { sm: "size-3.5", md: "size-5", lg: "size-7" } }, defaultVariants: { size: "md" } });
export function Spinner({ className, size, label = "Loading" }: { className?: string; size?: VariantProps<typeof spinnerStyles>["size"]; label?: string }) {
  return <span role="status" className="inline-flex items-center gap-2 text-xs text-fg-muted"><LoaderCircle className={cn(spinnerStyles({ size }), className)} aria-hidden="true" /><span>{label}</span></span>;
}
