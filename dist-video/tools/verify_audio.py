#!/usr/bin/env python3
"""Fail the build if the TTS mangled the script.

v1 shipped a caption reading "a six hour fresh and it" where the script said "six-hour freshness
target". Transcribing the rendered audio and diffing it against the script catches that class of
defect before it reaches a viewer.

    DEEPGRAM_API_KEY=... python3 tools/verify_audio.py [audio.wav]

Exit 0 = clean. Exit 1 = something was mangled; the differing spans are printed.
"""

from __future__ import annotations

import difflib
import sys
from pathlib import Path

from dg import normalize, script_tokens, transcribe

TOOLS = Path(__file__).resolve().parent
DEFAULT_AUDIO = TOOLS / "build" / "audio.wav"
SCRIPT = TOOLS / "narration.txt"
MIN_RATIO = 0.93


def main() -> int:
    audio = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_AUDIO
    spoken = [normalize(word.get("punctuated_word") or word["word"]) for word in transcribe(audio)]
    written = [normalize(token) for token in script_tokens(SCRIPT)]

    matcher = difflib.SequenceMatcher(a=written, b=spoken, autojunk=False)
    ratio = matcher.ratio()
    problems = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        problems.append((tag, " ".join(written[i1:i2]) or "-", " ".join(spoken[j1:j2]) or "-"))

    print(f"script tokens: {len(written)}   transcribed: {len(spoken)}   similarity: {ratio:.3f}")
    if problems:
        print(f"\n{len(problems)} differing span(s) — script -> heard:")
        for tag, want, got in problems:
            print(f"  [{tag:7}] {want!r} -> {got!r}")

    if ratio < MIN_RATIO:
        print(f"\nFAIL: similarity {ratio:.3f} is below {MIN_RATIO}. Do not ship this audio.")
        return 1
    print("\nPASS: transcript matches the script closely enough to ship.")
    print("Read the differing spans above anyway — a low count can still hide one bad word.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
