import * as CollapsiblePrimitive from "@radix-ui/react-collapsible";
import { ChevronDown } from "lucide-react";
import { cva } from "class-variance-authority";
import { cn } from "../../lib/utils";

const triggerStyles = cva("group inline-flex items-center gap-1.5 rounded-md text-xs font-semibold text-fg-muted transition-colors hover:text-fg");

export const Collapsible = CollapsiblePrimitive.Root;
export function CollapsibleTrigger({ className, children, ...props }: React.ComponentPropsWithoutRef<typeof CollapsiblePrimitive.Trigger>) {
  return <CollapsiblePrimitive.Trigger className={cn(triggerStyles(), className)} {...props}>{children}<ChevronDown className="size-3.5 transition-transform group-data-[state=open]:rotate-180" aria-hidden="true" /></CollapsiblePrimitive.Trigger>;
}
export function CollapsibleContent({ className, ...props }: React.ComponentPropsWithoutRef<typeof CollapsiblePrimitive.Content>) {
  return <CollapsiblePrimitive.Content className={cn("overflow-hidden data-[state=open]:animate-in data-[state=closed]:animate-out", className)} {...props} />;
}
