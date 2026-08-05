#!/usr/bin/env python3
"""Cut an SRT whose text comes from the script and whose timing comes from the audio.

v1 wrote captions straight from Deepgram's transcript, so every ASR error shipped as a caption —
one cue read "a six hour fresh and it" where the script said "six-hour freshness target". Here
Deepgram supplies only the per-word timings; the words themselves always come from narration.txt.
Script tokens that the recognizer misheard get their timing interpolated from their neighbours, so
a mis-recognition costs a little timing precision instead of putting a wrong word on screen.

    DEEPGRAM_API_KEY=... python3 tools/subtitles.py [audio.wav] [out.srt]
"""

from __future__ import annotations

import difflib
import sys
from pathlib import Path

from dg import normalize, script_tokens, transcribe

TOOLS = Path(__file__).resolve().parent
DEFAULT_AUDIO = TOOLS / "build" / "audio.wav"
DEFAULT_SRT = TOOLS.parent / "oncall-demo.srt"
SCRIPT = TOOLS / "narration.txt"

MAX_CHARS = 74  # two comfortable caption lines at 1920px
MAX_SECONDS = 5.5
MIN_CUE_SECONDS = 0.6


def stamp(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def align(written: list[str], heard: list[dict]) -> list[tuple[str, float, float]]:
    """Give every script token a start/end, borrowing timings from the matched spoken tokens."""

    spoken_norm = [normalize(word.get("punctuated_word") or word["word"]) for word in heard]
    times: list[tuple[float, float] | None] = [None] * len(written)
    matcher = difflib.SequenceMatcher(a=[normalize(t) for t in written], b=spoken_norm, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "equal":
            continue
        for offset in range(i2 - i1):
            word = heard[j1 + offset]
            times[i1 + offset] = (float(word["start"]), float(word["end"]))

    # Unmatched runs sit between two anchors; spread them evenly across the gap.
    total = float(heard[-1]["end"])
    for index, value in enumerate(times):
        if value is not None:
            continue
        before = next((times[i] for i in range(index - 1, -1, -1) if times[i]), None)
        after = next((times[i] for i in range(index + 1, len(times)) if times[i]), None)
        start = before[1] if before else 0.0
        end = after[0] if after else total
        if end < start:
            end = start
        span = max(end - start, 0.0)
        run = [i for i in range(index, len(times)) if times[i] is None]
        run = run[: len(run)] if run else [index]
        share = span / max(len(run), 1)
        position = run.index(index) if index in run else 0
        times[index] = (start + share * position, start + share * (position + 1))

    return [(written[i], times[i][0], times[i][1]) for i in range(len(written))]


def group(tokens: list[tuple[str, float, float]]) -> list[tuple[float, float, str]]:
    """Pack tokens into cues, breaking on sentence ends, line length, or duration."""

    cues: list[tuple[float, float, str]] = []
    buf: list[str] = []
    start = end = 0.0
    for text, token_start, token_end in tokens:
        if not buf:
            start = token_start
        buf.append(text)
        end = token_end
        line = " ".join(buf)
        if len(line) >= MAX_CHARS or (end - start) >= MAX_SECONDS or text.endswith((".", "?", "!", ":")):
            cues.append((start, end, line))
            buf = []
    if buf:
        cues.append((start, end, " ".join(buf)))
    return cues


def wrap(text: str) -> str:
    if len(text) <= 42:
        return text
    words = text.split()
    mid = len(text) // 2
    best, line = None, ""
    for index, word in enumerate(words):
        line = line + (" " if line else "") + word
        if best is None or abs(len(line) - mid) < abs(best[1] - mid):
            best = (index, len(line))
    cut = (best or (0, 0))[0] + 1
    return " ".join(words[:cut]) + "\n" + " ".join(words[cut:])


def main() -> int:
    audio = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_AUDIO
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_SRT
    tokens = align(script_tokens(SCRIPT), transcribe(audio))
    cues = group(tokens)

    lines = []
    for index, (start, end, text) in enumerate(cues, start=1):
        lines.append(f"{index}\n{stamp(start)} --> {stamp(max(end, start + MIN_CUE_SECONDS))}\n{wrap(text)}\n")
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out.name}: {len(cues)} cues from script text, last ends {stamp(cues[-1][1])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
