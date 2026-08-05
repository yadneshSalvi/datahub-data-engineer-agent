"""Shared Deepgram helpers.

smart_format is deliberately OFF. It rewrites spoken numbers into numerals ("twenty three" ->
"23"), which fights the script alignment in subtitles.py — we want tokens as close to the spoken
form as possible so they line up with narration.txt.
"""

from __future__ import annotations

import json
import os
import re
import ssl
from pathlib import Path
from urllib.request import Request, urlopen

try:
    import certifi

    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:  # pragma: no cover
    SSL_CONTEXT = ssl.create_default_context()

ENDPOINT = "https://api.deepgram.com/v1/listen?model=nova-2&punctuate=true&smart_format=false"


def transcribe(audio: Path) -> list[dict]:
    """Return Deepgram's word list with per-word start/end times."""

    key = os.environ.get("DEEPGRAM_API_KEY", "").strip()
    if not key:
        raise SystemExit("DEEPGRAM_API_KEY is not set; source the repo .env first.")
    if not audio.is_file():
        raise SystemExit(f"{audio} is missing; run assemble.sh first.")
    request = Request(
        ENDPOINT,
        data=audio.read_bytes(),
        headers={"Authorization": f"Token {key}", "Content-Type": "audio/wav"},
    )
    with urlopen(request, timeout=600, context=SSL_CONTEXT) as response:
        body = json.load(response)
    words = body["results"]["channels"][0]["alternatives"][0].get("words", [])
    if not words:
        raise SystemExit("Deepgram returned no words; inspect the response before shipping.")
    return words


def normalize(word: str) -> str:
    """Fold a token to its comparable core: lowercase, letters and digits only."""

    return re.sub(r"[^a-z0-9]", "", word.lower())


def script_tokens(script: Path) -> list[str]:
    return [token for token in script.read_text(encoding="utf-8").split() if normalize(token)]
