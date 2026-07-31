import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return "—";
  const whole = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(whole / 60);
  const remainder = whole % 60;
  return `${minutes.toString().padStart(2, "0")}:${remainder.toString().padStart(2, "0")}`;
}

export function formatCompact(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

export function relativeTime(iso: string): string {
  const deltaSeconds = Math.round((new Date(iso).getTime() - Date.now()) / 1000);
  const formatter = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  const ranges: ReadonlyArray<[Intl.RelativeTimeFormatUnit, number]> = [
    ["year", 31_536_000],
    ["month", 2_592_000],
    ["day", 86_400],
    ["hour", 3_600],
    ["minute", 60],
  ];
  for (const [unit, seconds] of ranges) {
    if (Math.abs(deltaSeconds) >= seconds) return formatter.format(Math.round(deltaSeconds / seconds), unit);
  }
  return formatter.format(deltaSeconds, "second");
}

export function middleTruncate(value: string, max = 54): string {
  if (value.length <= max) return value;
  const available = max - 1;
  const start = Math.ceil(available * 0.58);
  return `${value.slice(0, start)}…${value.slice(-(available - start))}`;
}
