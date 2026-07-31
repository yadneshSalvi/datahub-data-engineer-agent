import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { cva } from "class-variance-authority";
import { cn } from "../../lib/utils";

const contentStyles = cva("z-[100] max-w-xs rounded-lg border border-border-strong bg-surface-2 px-3 py-2 text-xs leading-relaxed text-fg shadow-2xl data-[state=delayed-open]:animate-in data-[state=closed]:animate-out");

export function Tooltip({ children, content, side = "top" }: { children: React.ReactNode; content: React.ReactNode; side?: "top" | "right" | "bottom" | "left" }) {
  return (
    <TooltipPrimitive.Provider delayDuration={250}>
      <TooltipPrimitive.Root>
        <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
        <TooltipPrimitive.Portal>
          <TooltipPrimitive.Content side={side} sideOffset={8} className={cn(contentStyles())}>
            {content}
            <TooltipPrimitive.Arrow className="fill-border-strong" />
          </TooltipPrimitive.Content>
        </TooltipPrimitive.Portal>
      </TooltipPrimitive.Root>
    </TooltipPrimitive.Provider>
  );
}
