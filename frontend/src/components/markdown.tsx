import { Fragment, type ReactNode } from "react";
import { cn } from "../lib/utils";

function inline(text: string): ReactNode[] {
  const parts = text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g);
  return parts.map((part, index) => {
    if (part.startsWith("`") && part.endsWith("`")) return <code key={index} className="rounded bg-bg/55 px-1.5 py-0.5 font-mono text-[.92em] text-info">{part.slice(1, -1)}</code>;
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={index} className="font-semibold text-fg">{part.slice(2, -2)}</strong>;
    return <Fragment key={index}>{part}</Fragment>;
  });
}

export function Markdown({ children, className }: { children: string; className?: string }) {
  const lines = children.replace(/\r/g, "").split("\n");
  const blocks: ReactNode[] = [];
  let paragraph: string[] = [];
  let bullets: string[] = [];

  const flushParagraph = () => {
    if (!paragraph.length) return;
    const value = paragraph.join(" ");
    blocks.push(<p key={`p-${blocks.length}`} className="text-[13px] leading-7 text-fg-muted">{inline(value)}</p>);
    paragraph = [];
  };
  const flushBullets = () => {
    if (!bullets.length) return;
    blocks.push(<ul key={`ul-${blocks.length}`} className="space-y-2 pl-1">{bullets.map((value, index) => <li key={index} className="flex gap-2 text-[13px] leading-6 text-fg-muted"><span className="mt-[9px] size-1.5 shrink-0 rounded-full bg-brand" /> <span>{inline(value)}</span></li>)}</ul>);
    bullets = [];
  };

  lines.forEach((line) => {
    const trimmed = line.trim();
    if (!trimmed) { flushParagraph(); flushBullets(); return; }
    if (trimmed.startsWith("# ")) { flushParagraph(); flushBullets(); blocks.push(<h1 key={`h1-${blocks.length}`} className="text-xl font-semibold tracking-[-.025em] text-fg">{inline(trimmed.slice(2))}</h1>); return; }
    if (trimmed.startsWith("## ")) { flushParagraph(); flushBullets(); blocks.push(<h2 key={`h2-${blocks.length}`} className="border-b border-border pb-2 pt-2 text-xs font-bold uppercase tracking-[.14em] text-fg-subtle">{inline(trimmed.slice(3))}</h2>); return; }
    if (trimmed.startsWith("- ")) { flushParagraph(); bullets.push(trimmed.slice(2)); return; }
    flushBullets();
    paragraph.push(trimmed);
  });
  flushParagraph();
  flushBullets();
  return <article className={cn("space-y-4", className)}>{blocks}</article>;
}
