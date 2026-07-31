import { Inbox } from "lucide-react";
import { cva } from "class-variance-authority";
import { cn } from "../../lib/utils";

const emptyStyles = cva("flex min-h-40 flex-col items-center justify-center rounded-xl border border-dashed border-border bg-bg/25 px-6 py-8 text-center");
export function EmptyState({ icon: Icon = Inbox, title, description, action, className }: { icon?: React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>; title: string; description: string; action?: React.ReactNode; className?: string }) {
  return <div className={cn(emptyStyles(), className)}><div className="mb-3 grid size-10 place-items-center rounded-xl border border-brand/25 bg-brand/10 text-brand"><Icon className="size-5" aria-hidden={true} /></div><p className="font-semibold text-fg">{title}</p><p className="mt-1 max-w-md text-xs leading-relaxed text-fg-muted">{description}</p>{action && <div className="mt-4">{action}</div>}</div>;
}
