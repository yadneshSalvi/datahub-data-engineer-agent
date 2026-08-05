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
while IFS=$'\t' read -r seg clip in speed crop; do
  [[ -z "${seg// }" || "${seg:0:1}" == "#" ]] && continue
  index=$((index + 1))
  n=$(printf "%02d" "$index")
  wav="$RAW/seg_$n.wav"
  src="$RAW/$clip.webm"

  [[ -f "$wav" ]] || { echo "missing $wav — run tts.py first" >&2; exit 1; }
  [[ -f "$src" ]] || { echo "missing $src — capture $clip first" >&2; exit 1; }

  want=$(duration "$wav")

  # Build the video filter chain: speed -> crop -> fit to 1080p -> pad -> speed chip.
  chain="setpts=PTS/${speed}"
  [[ "$crop" != "-" ]] && chain="$chain,crop=${crop}"
  chain="$chain,scale=${W}:${H}:force_original_aspect_ratio=decrease"
  chain="$chain,pad=${W}:${H}:(ow-iw)/2:(oh-ih)/2:color=${BG},fps=${FPS}"
  if [[ "$speed" != "1" && -f "$FONT" ]]; then
    chain="$chain,drawbox=x=iw-232:y=36:w=196:h=54:color=black@0.55:t=fill"
    chain="$chain,drawtext=fontfile='${FONT}':text='${speed}x speed':fontcolor=white@0.92:fontsize=30:x=iw-214:y=50"
  fi
  # Hold the final frame if the clip runs short, so a segment never ends on black.
  chain="$chain,tpad=stop_mode=clone:stop_duration=8"

  ffmpeg -y -v error -ss "$in" -i "$src" -filter_complex "[0:v]${chain}[v]" -map "[v]" \
    -t "$want" -an -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p "$OUT/v_$n.mp4"

  echo "file 'v_$n.mp4'" >> "$OUT/video_list.txt"
  echo "file '../$RAW/seg_$n.wav'" >> "$OUT/audio_list.txt"
  total=$(python3 -c "print(round($total + $want, 2))")
  printf "  seg %s  %-26s %6.2fs  speed=%sx crop=%s\n" "$n" "$clip" "$want" "$speed" "$crop"
done < "$SHOTS"

echo "  ---- narration total: ${total}s"

echo "== concatenating =="
ffmpeg -y -v error -f concat -safe 0 -i "$OUT/video_list.txt" -c copy "$OUT/video.mp4"
ffmpeg -y -v error -f concat -safe 0 -i "$OUT/audio_list.txt" -c:a pcm_s16le "$OUT/audio.wav"

echo "== muxing =="
ffmpeg -y -v error -i "$OUT/video.mp4" -i "$OUT/audio.wav" \
  -c:v copy -c:a aac -b:a 192k -shortest "$FINAL"

secs=$(duration "$FINAL")
printf "\nDONE: %s  (%.1fs)\n" "$FINAL" "$secs"
python3 -c "
import sys
d = $secs
print(f'  duration {int(d//60)}:{d%60:04.1f}')
sys.exit(1 if d > 180 else 0)
" || { echo "FAIL: over the 3:00 hackathon cap." >&2; exit 1; }
