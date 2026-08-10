#!/usr/bin/env python3
"""Measure the finished cut: caption sync, genuine freezes, and the motion profile.

Three gates, each pointed at a defect this project actually shipped once:

* **caption sync** — captions are worded from the script and timed from the audio, so the check is
  that each cue starts when its first word is spoken. Reported as the median offset over all cues.
* **genuine stillness** — since the camera now holds still on purpose, "nothing moved for 5
  seconds" is no longer a defect by itself. What is still a defect is a picture in which nothing
  moves at all: no cursor, no UI animation, no panel reveal. Measured by counting how many pixels
  changed, not by averaging the change away.
* **motion profile** — the camera grammar predicts a flat timeline with short bumps where the
  intended moves are. A sustained low-level ripple means the drift-pan is back.

    python3 tools/verify_cut.py [video.mp4]
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
DEFAULT = TOOLS.parent / "oncall-demo.mp4"
SRT = TOOLS.parent / "oncall-demo.srt"
SCRIPT = TOOLS / "narration.txt"

SAMPLE_FPS = 10
GRID_W, GRID_H = 480, 270
PIXEL_DELTA = 6      # per-pixel change that counts as a pixel having moved
STILL_PIXELS = 25    # fewer changed pixels than this, out of 129,600, is a still picture
MOVING = 3.0         # mean change above this and the camera or the page is actually travelling

# Measuring stillness as a MEAN luma change over a coarse grid does not work here: a caret
# blinking or a dot travelling an edge is real motion a viewer sees, but it moves so few pixels
# that the mean stays near zero and the gate reports a 14-second freeze over a panel that is
# visibly animating. Counting changed pixels answers the question actually being asked — did
# anything at all move — at the resolution the motion actually happens at.


def probe(path: Path, entries: str) -> str:
    return subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", entries,
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True).stdout.strip()


def sampled(path: Path) -> tuple[list[float], list[int]]:
    """Per frame pair: the mean luma change, and how many pixels moved at all."""

    raw = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", str(path),
         "-vf", f"fps={SAMPLE_FPS},scale={GRID_W}:{GRID_H},format=gray",
         "-f", "rawvideo", "-"],
        capture_output=True, check=True).stdout
    size = GRID_W * GRID_H
    frames = [raw[i:i + size] for i in range(0, len(raw) - size + 1, size)]
    means, counts = [], []
    for a, b in zip(frames, frames[1:]):
        deltas = [abs(x - y) for x, y in zip(a, b)]
        means.append(sum(deltas) / size)
        counts.append(sum(1 for d in deltas if d > PIXEL_DELTA))
    return means, counts


def runs(diffs: list[float], predicate) -> list[tuple[float, float]]:
    spans, start = [], None
    for index, value in enumerate(diffs):
        if predicate(value):
            start = index if start is None else start
        elif start is not None:
            spans.append((start / SAMPLE_FPS, index / SAMPLE_FPS))
            start = None
    if start is not None:
        spans.append((start / SAMPLE_FPS, len(diffs) / SAMPLE_FPS))
    return spans


def stamp_to_seconds(text: str) -> float:
    hours, minutes, rest = text.split(":")
    seconds, ms = rest.split(",")
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(ms) / 1000


def caption_sync() -> list[float]:
    sys.path.insert(0, str(TOOLS))
    from dg import script_tokens, normalize          # noqa: E402
    from subtitles import align                      # noqa: E402
    import json

    cache = TOOLS / "build" / "dg_words.json"
    if not cache.is_file():
        sys.exit("build/dg_words.json missing — run word_times.py first")
    timed = align(script_tokens(SCRIPT), json.loads(cache.read_text()))

    cues = []
    for block in SRT.read_text(encoding="utf-8").strip().split("\n\n"):
        lines = block.split("\n")
        start = stamp_to_seconds(lines[1].split("-->")[0].strip())
        cues.append((start, " ".join(lines[2:]).replace("\n", " ").split()))

    offsets, cursor = [], 0
    for start, words in cues:
        first = normalize(words[0])
        while cursor < len(timed) and normalize(timed[cursor][0]) != first:
            cursor += 1
        if cursor >= len(timed):
            break
        offsets.append(round(start - timed[cursor][1], 3))
        cursor += len(words)
    return offsets


def main() -> int:
    video = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    seconds = float(probe(video, "format=duration"))
    size = int(probe(video, "format=size"))
    stream = probe(video, "stream=width,height").split("\n")

    print(f"file      {video.name}")
    print(f"duration  {seconds:.3f}s = {int(seconds // 60)}:{seconds % 60:04.1f}"
          f"   {'PASS' if seconds < 180 else 'FAIL'} (hard cap 3:00)")
    print(f"size      {size:,} bytes")
    print(f"frame     {stream[0]}x{stream[1]}")

    diffs, counts = sampled(video)
    ordered = sorted(diffs)
    median = ordered[len(ordered) // 2]
    still = runs(counts, lambda v: v < STILL_PIXELS)
    moves = runs(diffs, lambda v: v > MOVING)

    print(f"\nmedian inter-frame change  {median:.3f}   (sampled at {SAMPLE_FPS} fps, "
          f"{GRID_W}x{GRID_H})")
    print(f"median pixels moved        {sorted(counts)[len(counts) // 2]}  of {GRID_W * GRID_H:,}")

    hard = [s for s in still if s[1] - s[0] >= 1.0]
    longest = max((b - a for a, b in still), default=0.0)
    print(f"\ngenuinely still spans >= 1.0s (fewer than {STILL_PIXELS} pixels moving):")
    if not hard:
        print("  none")
    for a, b in hard:
        print(f"  {a:6.1f}s -> {b:6.1f}s  ({b - a:.1f}s)")
    print(f"  longest still run: {longest:.1f}s "
          + ("(within the grammar's establish/dwell holds)" if longest <= 4.0
             else "— TOO LONG, this is dead air"))

    print(f"\nmovement runs (> {MOVING}): {len(moves)}")
    for a, b in moves:
        print(f"  {a:6.1f}s -> {b:6.1f}s  ({b - a:.1f}s)")
    sustained = [s for s in moves if s[1] - s[0] > 2.5]
    print("  sustained (>2.5s) runs: "
          + ("none — no drift, only cuts and the intended moves" if not sustained
             else f"{len(sustained)} — CHECK for drift"))

    offsets = caption_sync()
    ordered = sorted(offsets)
    med = ordered[len(ordered) // 2]
    worst = max(offsets, key=abs)
    print(f"\ncaption sync over {len(offsets)} cues: median {med:+.3f}s, "
          f"worst {worst:+.3f}s, "
          f"{sum(1 for o in offsets if abs(o) > 0.5)} cue(s) beyond 0.5s")
    return 0 if seconds < 180 else 1


if __name__ == "__main__":
    sys.exit(main())
