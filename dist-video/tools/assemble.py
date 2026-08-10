#!/usr/bin/env python3
"""Assemble the demo cut: fit each clip to its narration, then apply the camera treatment.

The camera grammar is deliberate rather than continuous. Each shot establishes on a locked full
frame, draws an accent border around the region the narration is about to name, eases into that
region over about a second, then holds perfectly still while the narration explains it. A previous
cut drifted slowly through every shot to avoid dead air and read as a constant shake with text
sliding out of frame; stillness is the correct default. What keeps a held shot alive is the UI's own
motion — rows landing, the event stream advancing, the replay walking its cards.

Consequence worth knowing: freezedetect now reports long "frozen" spans wherever the camera holds
over a settled screen. Those are intended. The gate it still catches is a stuck capture, which is a
different thing and shows up as a hold nothing was ever meant to be on.

    python3 assemble.py
"""

from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
RAW = TOOLS / "raw"
OUT = TOOLS / "build"
FINAL = TOOLS.parent / "oncall-demo.mp4"

MASTER_W, MASTER_H = 3200, 1800
W, H, FPS = 1920, 1080, 30
BG = "0x08090b"
ACCENT = "0x9184FF"          # the app's own brand violet; reads on the dark UI and on DataHub white
BORDER = 7                   # in master pixels, so it lands at ~4px once scaled to 1080p
CAP_SECONDS = 180


def run(args: list[str]) -> None:
    proc = subprocess.run(args, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit(f"ffmpeg failed:\n  {shlex.join(args)}\n{proc.stderr[-1500:]}")


def duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def rows(path: Path) -> list[list[str]]:
    result = []
    for line in path.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        result.append(line.split("\t"))
    return result


def eased(expr_progress: str) -> str:
    """Smoothstep, so the move accelerates and settles instead of starting and stopping abruptly."""

    return f"(3*pow({expr_progress},2)-2*pow({expr_progress},3))"


def zoom_filter(rect: tuple[int, int, int, int], frames: int, *, out: bool) -> str:
    """Ease between the full master frame and `rect`, rendering straight to output size."""

    x, y, w, _h = rect
    progress = f"(on/{max(frames - 1, 1)})"
    e = eased(progress) if not out else f"(1-{eased(progress)})"
    width = f"({w}+({MASTER_W}-{w})*(1-{e}))"
    return (
        f"zoompan=z='{MASTER_W}/{width}':x='{x}*{e}':y='{y}*{e}'"
        f":d=1:s={W}x{H}:fps={FPS}"
    )


def phase_filter(kind: str, rect: tuple[int, int, int, int] | None, frames: int) -> str:
    if kind == "full":
        return f"scale={W}:{H}"
    if kind == "hl":
        assert rect
        x, y, w, h = rect
        return (f"drawbox=x={x}:y={y}:w={w}:h={h}:color={ACCENT}@0.95:t={BORDER},"
                f"scale={W}:{H}")
    if kind == "hold":
        assert rect
        x, y, w, h = rect
        return f"crop={w}:{h}:{x}:{y},scale={W}:{H}"
    if kind in ("zin", "zout"):
        assert rect
        return zoom_filter(rect, frames, out=(kind == "zout"))
    sys.exit(f"unknown phase kind: {kind}")



# The split-screen blocks. Inside a block the camera is pixel-locked and the panel does all the
# moving; the block enters and leaves with a single ~1s slide. They are deliberately few and long:
# five short blocks would have put two transitions a second apart at the seg08/09 and seg09/10
# boundaries, which is the constant motion the drift-pan cut was rejected for.
BLOCKS = {"A": ["seg02"], "B": ["seg06", "seg07", "seg08", "seg09", "seg10"]}
LEFT_W = 1120
PANEL_W = W - LEFT_W          # 800; panels.py renders at exactly this width
SLIDE = 0.9


def block_of(seg: str) -> tuple[str, int, int] | None:
    for name, members in BLOCKS.items():
        if seg in members:
            return name, members.index(seg), len(members)
    return None


def slide_x() -> tuple[str, str]:
    """Eased slide expressions for a panel entering and leaving frame."""

    p = f"min(t/{SLIDE},1)"
    q = f"max(min((t-(DUR-{SLIDE}))/{SLIDE},1),0)"
    enter = f"{LEFT_W}+{PANEL_W}*(1-(3*pow({p},2)-2*pow({p},3)))"
    leave = f"{LEFT_W}+{PANEL_W}*(3*pow({q},2)-2*pow({q},3))"
    return enter, leave


def panel_x(first: bool, last: bool, dur: float) -> str:
    enter, leave = slide_x()
    if first and last:
        expr = f"if(lt(t,{SLIDE}),{enter},{leave})"
    elif first:
        expr = enter
    elif last:
        expr = leave
    else:
        expr = str(LEFT_W)
    return expr.replace("DUR", f"{dur:.3f}")


def treat_rect(spec: str) -> str:
    """`sp:<secs>:<x,y,w,h>` -> an ffmpeg crop argument, checked against the left pane's shape."""

    x, y, w, h = (int(v) for v in spec.split(":")[2].split(","))
    if abs(w / h - LEFT_W / H) > 0.004:
        sys.exit(f"crop {w}x{h} is {w / h:.4f}, not the left pane's {LEFT_W / H:.4f} — it would stretch")
    return f"{w}:{h}:{x}:{y}"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    shots = {r[0]: r for r in rows(TOOLS / "shots.tsv")}
    treatments = {r[0]: r[1] for r in rows(TOOLS / "treatments.tsv")}

    video_list, audio_list = [], []
    total = 0.0

    for index, seg in enumerate(sorted(shots), start=1):
        _, clip, start, speed, _crop, chip = (shots[seg] + ["-"])[:6]
        n = f"{index:02d}"
        wav = RAW / f"seg_{n}.wav"
        src = RAW / f"{clip}.webm"
        if not wav.is_file():
            sys.exit(f"missing {wav} — run tts.py first")
        if not src.is_file():
            sys.exit(f"missing {src} — capture {clip} first")
        want = duration(wav)

        # A clip must genuinely cover its narration. tpad is left in only to absorb sub-frame
        # rounding; anything longer would clone a frozen frame into the cut, which is how a
        # "still" defect gets manufactured in the edit rather than found in the capture.
        available = (duration(src) - float(start)) / float(speed)
        if want > available:
            sys.exit(f"{seg}: narration is {want:.2f}s but {clip} only gives {available:.2f}s "
                     f"from in-point {start} at speed {speed} — retime, do not pad")

        pre = treatments[seg].endswith("pre")
        size = f"{LEFT_W}:{H}" if pre else f"{MASTER_W}:{MASTER_H}"
        norm = OUT / f"n_{n}.mp4"
        run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", start, "-i", str(src),
             "-vf", f"setpts=PTS/{speed},fps={FPS},scale={size},"
                    f"tpad=stop_mode=clone:stop_duration=1",
             "-t", f"{want}", "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
             "-pix_fmt", "yuv420p", str(norm)])

        block = block_of(seg)
        if block:
            name, position, count = block
            panel = OUT / f"panel_{name}.mp4"
            if not panel.is_file():
                sys.exit(f"missing {panel} — run panels.py first")
            offset = sum(duration(RAW / f"seg_{sorted(shots).index(m) + 1:02d}.wav")
                         for m in BLOCKS[name][:position])
            left = (f"scale={LEFT_W}:{H}" if pre
                    else f"crop={treat_rect(treatments[seg])},scale={LEFT_W}:{H}")
            seg_mp4 = OUT / f"v_{n}.mp4"
            run(["ffmpeg", "-nostdin", "-y", "-v", "error",
                 "-i", str(norm), "-ss", f"{offset}", "-t", f"{want}", "-i", str(panel),
                 "-filter_complex",
                 f"[0:v]{left},pad={W}:{H}:0:0:color={BG}[base];"
                 f"[base][1:v]overlay=x='{panel_x(position == 0, position == count - 1, want)}':y=0[v]",
                 "-map", "[v]", "-t", f"{want}", "-an", "-c:v", "libx264", "-preset", "medium",
                 "-crf", "19", "-pix_fmt", "yuv420p", "-r", str(FPS), str(seg_mp4)])
            video_list.append(f"file '{seg_mp4.name}'")
            audio_list.append(f"file '../raw/seg_{n}.wav'")
            total += want
            print(f"  seg {n}  {clip:<24} {want:6.2f}s  split-screen, panel {name}")
            continue

        # Split the segment into treatment phases; the last one absorbs the rounding remainder.
        specs = []
        for chunk in treatments[seg].split(";"):
            parts = chunk.split(":")
            kind, secs = parts[0], float(parts[1])
            rect = tuple(int(v) for v in parts[2].split(",")) if len(parts) > 2 else None
            specs.append([kind, secs, rect])
        fixed = sum(s[1] for s in specs[:-1])
        specs[-1][1] = round(want - fixed, 3)
        if specs[-1][1] < 0.4:
            sys.exit(f"{seg}: phases overrun the narration by {-specs[-1][1]:.2f}s")

        parts_list = OUT / f"p_{n}.txt"
        entries, offset = [], 0.0
        for pi, (kind, secs, rect) in enumerate(specs):
            piece = OUT / f"p_{n}_{pi}.mp4"
            frames = max(int(round(secs * FPS)), 1)
            run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", f"{offset}", "-t", f"{secs}",
                 "-i", str(norm), "-vf", phase_filter(kind, rect, frames),
                 "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "19",
                 "-pix_fmt", "yuv420p", "-r", str(FPS), str(piece)])
            entries.append(f"file '{piece.name}'")
            offset = round(offset + secs, 3)
        parts_list.write_text("\n".join(entries) + "\n")

        seg_mp4 = OUT / f"v_{n}.mp4"
        run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "concat", "-safe", "0",
             "-i", str(parts_list), "-c", "copy", str(seg_mp4)])

        if chip not in ("-", ""):
            png = OUT / f"chip_{n}.png"
            subprocess.run([sys.executable, "make_chip.py", chip, str(png)], cwd=TOOLS, check=True,
                           capture_output=True)
            chipped = OUT / f"c_{n}.mp4"
            run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(seg_mp4), "-i", str(png),
                 "-filter_complex", "[0:v][1:v]overlay=W-w-36:36[v]", "-map", "[v]",
                 "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "19",
                 "-pix_fmt", "yuv420p", str(chipped)])
            seg_mp4 = chipped

        video_list.append(f"file '{seg_mp4.name}'")
        audio_list.append(f"file '../raw/seg_{n}.wav'")
        total += want
        moves = sum(1 for s in specs if s[0] in ("zin", "zout"))
        print(f"  seg {n}  {clip:<24} {want:6.2f}s  {len(specs)} phases, {moves} camera moves")

    (OUT / "video_list.txt").write_text("\n".join(video_list) + "\n")
    (OUT / "audio_list.txt").write_text("\n".join(audio_list) + "\n")
    print(f"  ---- narration total: {total:.2f}s")

    run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", str(OUT / "video_list.txt"), "-c", "copy", str(OUT / "video.mp4")])
    run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", str(OUT / "audio_list.txt"), "-c:a", "pcm_s16le", str(OUT / "audio.wav")])
    run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(OUT / "video.mp4"),
         "-i", str(OUT / "audio.wav"), "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
         "-shortest", str(FINAL)])

    secs = duration(FINAL)
    print(f"\nDONE: {FINAL}  {secs:.3f}s = {int(secs // 60)}:{secs % 60:04.1f}")
    if secs > CAP_SECONDS:
        sys.exit(f"FAIL: {secs:.1f}s is over the {CAP_SECONDS}s cap.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
