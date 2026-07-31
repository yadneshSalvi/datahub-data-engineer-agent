import * as TabsPrimitive from "@radix-ui/react-tabs";
import { cva } from "class-variance-authority";
import { cn } from "../../lib/utils";

const listStyles = cva("inline-flex items-center gap-1 rounded-lg border border-border bg-bg/60 p-1");
const triggerStyles = cva("rounded-md px-3 py-1.5 text-xs font-semibold text-fg-subtle transition-colors hover:text-fg data-[state=active]:bg-surface-2 data-[state=active]:text-fg data-[state=active]:shadow-sm");

export const Tabs = TabsPrimitive.Root;
export function TabsList({ className, ...props }: React.ComponentPropsWithoutRef<typeof TabsPrimitive.List>) {
  return <TabsPrimitive.List className={cn(listStyles(), className)} {...props} />;
}
export function TabsTrigger({ className, ...props }: React.ComponentPropsWithoutRef<typeof TabsPrimitive.Trigger>) {
  return <TabsPrimitive.Trigger className={cn(triggerStyles(), className)} {...props} />;
}
export function TabsContent({ className, ...props }: React.ComponentPropsWithoutRef<typeof TabsPrimitive.Content>) {
  return <TabsPrimitive.Content className={cn("outline-none", className)} {...props} />;
}
