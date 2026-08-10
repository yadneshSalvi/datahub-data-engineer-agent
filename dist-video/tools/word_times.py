#!/usr/bin/env python3
"""Give every script word a time, so the panels can be cut to the narration instead of guessed at.

The split-screen panels reveal one API call at the moment the narration names it. Eyeballing those
offsets drifts as soon as the TTS is regenerated, so they are derived the same way the subtitles
are: Deepgram supplies timings, `narration.txt` supplies the words, and unmatched tokens borrow
their timing from their neighbours.

Deepgram's answer is cached in `build/dg_words.json` — panels get re-rendered far more often than
the audio changes, and re-transcribing 3 minutes on every render wastes time and quota. Delete the
cache (or pass --refresh) after regenerating any wav.

    DEEPGRAM_API_KEY=... python3 tools/word_times.py [--refresh]

Writes `build/word_times.json`: per segment, the segment's own start/end in the concatenated
narration plus every word with times RELATIVE to that segment's start.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from dg import transcribe
from subtitles import align

TOOLS = Path(__file__).resolve().parent
RAW = TOOLS / "raw"
BUILD = TOOLS / "build"
SCRIPT = TOOLS / "narration.txt"
CACHE = BUILD / "dg_words.json"
OUT = BUILD / "word_times.json"


def duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def segments() -> list[list[str]]:
    blocks = [b for b in SCRIPT.read_text(encoding="utf-8").split("\n\n") if b.strip()]
    return [block.split() for block in blocks]


def main() -> int:
    BUILD.mkdir(parents=True, exist_ok=True)
    refresh = "--refresh" in sys.argv

    audio = BUILD / "audio.wav"
    if not audio.is_file():
        sys.exit(f"missing {audio} — concatenate the segment wavs first")

    if CACHE.is_file() and not refresh:
        heard = json.loads(CACHE.read_text())
        print(f"using cached Deepgram words ({len(heard)}) — pass --refresh after re-running tts.py")
    else:
        heard = transcribe(audio)
        CACHE.write_text(json.dumps(heard))
        print(f"transcribed {len(heard)} words")

    per_segment = segments()
    flat = [token for seg in per_segment for token in seg]
    timed = align(flat, heard)

    # Segment boundaries come from the wav durations, not from the transcript: the concatenated
    # audio is exactly those files end to end, and a silent tail would otherwise drag a boundary.
    starts, offset = [], 0.0
    for index in range(1, len(per_segment) + 1):
        starts.append(offset)
        offset += duration(RAW / f"seg_{index:02d}.wav")

    out, cursor = [], 0
    for index, tokens in enumerate(per_segment):
        base = starts[index]
        end = starts[index + 1] if index + 1 < len(starts) else offset
        words = []
        for token in tokens:
            text, start, stop = timed[cursor]
            cursor += 1
            words.append({"w": text, "s": round(start - base, 3), "e": round(stop - base, 3)})
        out.append({"seg": f"seg{index + 1:02d}", "start": round(base, 3),
                    "duration": round(end - base, 3), "words": words})

    OUT.write_text(json.dumps(out, indent=1))
    print(f"wrote {OUT.name}: {len(out)} segments, {cursor} words, {offset:.2f}s total")
    for row in out:
        print(f"  {row['seg']}  {row['duration']:6.2f}s  {len(row['words']):3d} words")
    return 0


if __name__ == "__main__":
    sys.exit(main())
