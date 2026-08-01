import { useEffect, useRef } from "react";

/**
 * Hold the last value that satisfied `isGood`, so a transient empty response does not blank the UI.
 *
 * Several backend reads are search-index backed and briefly report an empty or unseeded catalog
 * right after a reset — a window measured at ~24s under load. Rendering that literally makes the
 * Command Deck flash "No catalog yet" in the middle of a demo, which reads as a broken app rather
 * than a settling index. Showing the previous good value is both calmer and more accurate: the
 * catalog did not actually go away.
 *
 * Returns the current value when it is good, otherwise the most recent good one (or the current
 * value if nothing good has been seen yet, so genuine empty states still surface on first load).
 */
export function useLastKnownGood<T>(value: T, isGood: (candidate: T) => boolean): T {
  const lastGood = useRef<T | null>(null);
  useEffect(() => {
    if (isGood(value)) lastGood.current = value;
  }, [value, isGood]);

  if (isGood(value)) return value;
  return lastGood.current ?? value;
}
