import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { cva } from "class-variance-authority";
import { cn } from "../../lib/utils";

const overlayStyles = cva("fixed inset-0 z-50 bg-bg/72 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out data-[state=open]:fade-in");
const panelStyles = cva("fixed z-50 border-border bg-surface shadow-[-28px_0_80px_-40px_rgba(0,0,0,.9)] outline-none data-[state=open]:animate-in data-[state=closed]:animate-out", {
  variants: { side: { right: "inset-y-0 right-0 w-[min(480px,94vw)] border-l data-[state=closed]:slide-out-to-right data-[state=open]:slide-in-from-right", center: "left-1/2 top-1/2 w-[min(560px,92vw)] -translate-x-1/2 -translate-y-1/2 rounded-card border" } },
  defaultVariants: { side: "center" },
});

export const Dialog = DialogPrimitive.Root;
export const DialogTrigger = DialogPrimitive.Trigger;
export const DialogClose = DialogPrimitive.Close;

export function DialogContent({ className, children, side = "center", title }: { className?: string; children: React.ReactNode; side?: "right" | "center"; title: string }) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className={overlayStyles()} />
      <DialogPrimitive.Content className={cn(panelStyles({ side }), className)}>
        <DialogPrimitive.Title className="sr-only">{title}</DialogPrimitive.Title>
        {children}
        <DialogPrimitive.Close aria-label="Close panel" className="absolute right-4 top-4 grid size-9 place-items-center rounded-lg border border-border bg-surface-2 text-fg-muted transition-colors hover:text-fg">
          <X className="size-4" aria-hidden="true" />
        </DialogPrimitive.Close>
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}
