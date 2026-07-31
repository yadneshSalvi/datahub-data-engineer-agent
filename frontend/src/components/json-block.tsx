import type { JsonValue } from "../lib/types";

const JSON_TOKEN_EXPRESSION = /"(?:\\.|[^"\\])*"(?=\s*:)|"(?:\\.|[^"\\])*"|\b(?:true|false|null)\b|-?\d+(?:\.\d+)?/g;

export function JsonBlock({ value }: { value: JsonValue | null }) {
  const source = JSON.stringify(value, null, 2) ?? "null";
  const parts: React.ReactNode[] = [];
  let cursor = 0;
  for (const match of source.matchAll(JSON_TOKEN_EXPRESSION)) {
    const index = match.index;
    if (index > cursor) parts.push(source.slice(cursor, index));
    const token = match[0];
    const after = source.slice(index + token.length).trimStart();
    const tone = token.startsWith("\"") ? (after.startsWith(":") ? "text-info" : "text-ok") : token === "true" || token === "false" || token === "null" ? "text-warn" : "text-brand";
    parts.push(<span key={`${index}-${token}`} className={tone}>{token}</span>);
    cursor = index + token.length;
  }
  if (cursor < source.length) parts.push(source.slice(cursor));
  return <pre className="overflow-x-auto whitespace-pre-wrap break-words rounded-lg border border-border bg-bg/70 p-3 font-mono text-[10px] leading-relaxed text-fg-muted">{parts}</pre>;
}
