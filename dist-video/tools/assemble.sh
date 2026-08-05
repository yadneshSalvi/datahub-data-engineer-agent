#!/usr/bin/env bash
# Assemble the demo cut: fit each clip to its narration segment, then mux.
#
# Clips are recorded at 3200x1800 (1600x900 CSS viewport at deviceScaleFactor 2). A "wide" shot is
# that master downscaled to 1080p; a close-up is a CROP of the master, so narrated text stays at or
# near native resolution instead of being upscaled from a 1080p frame. That is the fix for v1's
# unreadably tiny text.
#
# Segments marked with a speed > 1 in shots.tsv time-compress a real wait (the triage run takes
# ~3.5 min of wall clock against ~46 s of narration). Those get an "Nx speed" chip burned in so the
# fast-moving elapsed counter on screen is never mistaken for real time.
set -euo pipefail
cd "$(dirname "$0")"

RAW=raw
OUT=build
SHOTS=shots.tsv
FINAL=../oncall-demo.mp4
FONT=/System/Library/Fonts/Supplemental/Arial.ttf
W=1920
H=1080
FPS=30
BG=0x08090b

mkdir -p "$OUT"
: > "$OUT/video_list.txt"
: > "$OUT/audio_list.txt"

command -v ffmpeg >/dev/null || { echo "ffmpeg not found" >&2; exit 1; }
[[ -f "$SHOTS" ]] || { echo "$SHOTS missing" >&2; exit 1; }

duration() { ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$1"; }

index=0
total=0
while IFS=$'\t' read -r seg clip in speed crop chip; do
  chip=${chip:--}
  [[ -z "${seg// }" || "${seg:0:1}" == "#" ]] && continue
  index=$((index + 1))
  n=$(printf "%02d" "$index")
  wav="$RAW/seg_$n.wav"
  src="$RAW/$clip.webm"

  [[ -f "$wav" ]] || { echo "missing $wav — run tts.py first" >&2; exit 1; }
  [[ -f "$src" ]] || { echo "missing $src — capture $clip first" >&2; exit 1; }

  want=$(duration "$wav")

  # Build the video filter chain: speed -> panning crop -> fit to 1080p -> pad -> chip.
  #
  # The crop drifts slowly instead of sitting still. Screen recordings of these pages are static
  # for long stretches — several UI panels scroll an inner container, so a window scroll during
  # capture moved nothing at all, and a frame-difference check found 15+ second stretches of
  # pixel-identical video. That is precisely the "nothing happens on screen" problem this recut
  # exists to fix. A slow pan across the 2x master guarantees continuous motion in every shot
  # while still showing real, unaltered UI.
  #
  # The crop size stays constant (the encoder needs a fixed output size); only its origin moves.
  # Full-frame shots are inset slightly so they have margin to travel within.
  if [[ "$crop" == "-" ]]; then
    cw=$((3040)); ch=$((1710)); cx=80; cy=45
  else
    IFS=':' read -r cw ch cx cy <<< "$crop"
  fi
  # Travel ~5px/s horizontally on the master, a little less vertically, clamped inside the frame.
  px="min(${cx}+5*t\\,in_w-${cw})"
  py="min(${cy}+2*t\\,in_h-${ch})"

  chain="setpts=PTS/${speed}"
  chain="$chain,crop=${cw}:${ch}:${px}:${py}"
  chain="$chain,scale=${W}:${H}:force_original_aspect_ratio=decrease"
  chain="$chain,pad=${W}:${H}:(ow-iw)/2:(oh-ih)/2:color=${BG},fps=${FPS}"
  # Hold the final frame if the clip runs short, so a segment never ends on black.
  chain="$chain,tpad=stop_mode=clone:stop_duration=8"

  # The chip is declared per shot rather than derived from `speed`. Screen capture already drops
  # idle frames, so a clip can run faster than wall time at speed=1, and a slow-motion shot
  # (speed<1) must NOT be labelled as sped up. Only the shots.tsv chip column says what is claimed.
  # It is rasterised by make_chip.py and overlaid: this ffmpeg lacks drawtext (no libfreetype).
  if [[ "$chip" != "-" && -n "$chip" ]]; then
    python3 make_chip.py "$chip" "$OUT/chip_$n.png" >/dev/null
    ffmpeg -nostdin -y -v error -ss "$in" -i "$src" -i "$OUT/chip_$n.png" \
      -filter_complex "[0:v]${chain}[base];[base][1:v]overlay=W-w-36:36[v]" -map "[v]" \
      -t "$want" -an -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p "$OUT/v_$n.mp4"
  else
    ffmpeg -nostdin -y -v error -ss "$in" -i "$src" -filter_complex "[0:v]${chain}[v]" -map "[v]" \
      -t "$want" -an -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p "$OUT/v_$n.mp4"
  fi

  echo "file 'v_$n.mp4'" >> "$OUT/video_list.txt"
  echo "file '../$RAW/seg_$n.wav'" >> "$OUT/audio_list.txt"
  total=$(python3 -c "print(round($total + $want, 2))")
  printf "  seg %s  %-22s %6.2fs  speed=%s crop=%-22s chip=%s\n" "$n" "$clip" "$want" "$speed" "$crop" "$chip"
done < "$SHOTS"

echo "  ---- narration total: ${total}s"

echo "== concatenating =="
ffmpeg -nostdin -y -v error -f concat -safe 0 -i "$OUT/video_list.txt" -c copy "$OUT/video.mp4"
ffmpeg -nostdin -y -v error -f concat -safe 0 -i "$OUT/audio_list.txt" -c:a pcm_s16le "$OUT/audio.wav"

echo "== muxing =="
ffmpeg -nostdin -y -v error -i "$OUT/video.mp4" -i "$OUT/audio.wav" \
  -c:v copy -c:a aac -b:a 192k -shortest "$FINAL"

secs=$(duration "$FINAL")
printf "\nDONE: %s  (%.1fs)\n" "$FINAL" "$secs"
python3 -c "
import sys
d = $secs
print(f'  duration {int(d//60)}:{d%60:04.1f}')
sys.exit(1 if d > 180 else 0)
" || { echo "FAIL: over the 3:00 hackathon cap." >&2; exit 1; }
