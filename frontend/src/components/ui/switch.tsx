import * as SwitchPrimitive from "@radix-ui/react-switch";
import { cva } from "class-variance-authority";
import { cn } from "../../lib/utils";

const switchStyles = cva("relative h-6 w-11 shrink-0 rounded-full border border-border-strong bg-surface-2 transition-colors data-[state=checked]:border-brand data-[state=checked]:bg-brand");

export function Switch({ className, ...props }: React.ComponentPropsWithoutRef<typeof SwitchPrimitive.Root>) {
  return (
    <SwitchPrimitive.Root className={cn(switchStyles(), className)} {...props}>
      <SwitchPrimitive.Thumb className="block size-4 translate-x-1 rounded-full bg-fg shadow transition-transform data-[state=checked]:translate-x-6" />
    </SwitchPrimitive.Root>
  );
}
