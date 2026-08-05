#!/usr/bin/env python3
"""Render a burn-in label to a transparent PNG.

ffmpeg's drawtext filter needs libfreetype, which this build was compiled without, so the label is
rasterised here and composited with the overlay filter instead.

    python3 make_chip.py "2x speed" build/chip_06.png
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONTS = (
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
)
SIZE = 30
PAD_X, PAD_Y = 20, 12


def font() -> ImageFont.FreeTypeFont:
    for path in FONTS:
        if Path(path).is_file():
            try:
                return ImageFont.truetype(path, SIZE)
            except OSError:
                continue
    return ImageFont.load_default()


def main() -> int:
    text, out = sys.argv[1], Path(sys.argv[2])
    face = font()
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    left, top, right, bottom = probe.textbbox((0, 0), text, font=face)
    width = right - left + PAD_X * 2
    height = bottom - top + PAD_Y * 2

    chip = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(chip)
    draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=height // 2, fill=(8, 9, 11, 208))
    draw.text((PAD_X - left, PAD_Y - top), text, font=face, fill=(255, 255, 255, 236))

    out.parent.mkdir(parents=True, exist_ok=True)
    chip.save(out)
    print(f"{out} {width}x{height}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
