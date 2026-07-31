import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { cva } from "class-variance-authority";
import { cn, middleTruncate } from "../../lib/utils";
import { Tooltip } from "./tooltip";

const urnStyles = cva("inline-flex min-w-0 max-w-full items-center gap-1.5 rounded-md font-mono text-xs text-fg-muted transition-colors hover:text-fg");
export function Urn({ value, max = 58, className }: { value: string; max?: number; className?: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    } catch {
      setCopied(false);
    }
  };
  return <Tooltip content={value}><button type="button" onClick={() => void copy()} className={cn(urnStyles(), className)} aria-label={`Copy ${value}`}><span className="truncate">{middleTruncate(value, max)}</span>{copied ? <Check className="size-3.5 shrink-0 text-ok" aria-hidden="true" /> : <Copy className="size-3.5 shrink-0" aria-hidden="true" />}<span className="sr-only" aria-live="polite">{copied ? "Copied" : ""}</span></button></Tooltip>;
}
