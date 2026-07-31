import { forwardRef } from "react";
import { LoaderCircle } from "lucide-react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/utils";

const buttonStyles = cva(
  "inline-flex shrink-0 items-center justify-center gap-2 rounded-lg border font-semibold transition-[color,background-color,border-color,box-shadow,transform] duration-200 ease-out focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-bg disabled:pointer-events-none disabled:opacity-45 active:translate-y-px",
  {
    variants: {
      variant: {
        primary: "border-brand/80 bg-brand text-white shadow-[0_8px_28px_-12px_color-mix(in_oklch,var(--color-brand)_75%,transparent)] hover:bg-brand/90",
        secondary: "border-border-strong bg-surface-2 text-fg hover:border-brand/50 hover:bg-surface",
        ghost: "border-transparent bg-transparent text-fg-muted hover:bg-surface-2 hover:text-fg",
        danger: "border-critical/60 bg-critical/12 text-critical hover:bg-critical/20",
      },
      size: { sm: "h-8 px-3 text-xs", md: "h-10 px-4 text-sm" },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonStyles> {
  loading?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant, size, loading = false, disabled, children, ...props }, ref,
) {
  return (
    <button ref={ref} className={cn(buttonStyles({ variant, size }), className)} disabled={disabled || loading} {...props}>
      {loading && <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />}
      {children}
    </button>
  );
});
