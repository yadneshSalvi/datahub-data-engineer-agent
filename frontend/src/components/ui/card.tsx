import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/utils";

const cardStyles = cva("card-highlight rounded-card border border-border bg-surface", {
  variants: {
    interactive: { true: "transition-all duration-200 hover:-translate-y-0.5 hover:border-border-strong hover:shadow-[0_18px_50px_-28px_rgba(0,0,0,.65)]", false: "" },
  },
  defaultVariants: { interactive: false },
});

export interface CardProps extends React.HTMLAttributes<HTMLDivElement>, VariantProps<typeof cardStyles> {}

export function Card({ className, interactive, ...props }: CardProps) {
  return <div className={cn(cardStyles({ interactive }), className)} {...props} />;
}

export function CardHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex items-center justify-between gap-4 border-b border-border px-5 py-4", className)} {...props} />;
}

export function CardBody({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("p-5", className)} {...props} />;
}
