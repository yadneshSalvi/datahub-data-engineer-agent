import * as SeparatorPrimitive from "@radix-ui/react-separator";
import { cva } from "class-variance-authority";
import { cn } from "../../lib/utils";

const separatorStyles = cva("shrink-0 bg-border", { variants: { orientation: { horizontal: "h-px w-full", vertical: "h-full w-px" } }, defaultVariants: { orientation: "horizontal" } });

export function Separator({ className, orientation = "horizontal", decorative = true, ...props }: React.ComponentPropsWithoutRef<typeof SeparatorPrimitive.Root>) {
  return <SeparatorPrimitive.Root decorative={decorative} orientation={orientation} className={cn(separatorStyles({ orientation }), className)} {...props} />;
}
