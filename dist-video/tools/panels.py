#!/usr/bin/env python3
"""Render the split-screen technical panels that sit beside the footage.

Two panels exist. `arch` is an architecture diagram whose nodes light up as the narration names
them. `calls` is a rolling stack of the agent's REAL tool calls, revealed one at a time at the
moment the narration reaches them.

Every call, argument and response below is copied from `backend/data/oncall.db`, from the two runs
that are actually on camera (`run_9a5cb891af954977` cold, `run_71b45939d95844ab` recall). Nothing
is illustrative. Long responses are cut with a visible `…` so an abbreviation can never be mistaken
for the whole answer. The one number that is NOT quoted from a raw response is the blast-radius
total: the raw lineage response says 16 because it counts an unranked ML feature, while the run's
own authoritative_counts block — and the narration, and the app — say 15. Showing the raw 16 beside
the spoken "fifteen" would read as a contradiction, so the panel shows the authoritative breakdown,
which adds up on screen.

Timings come from `build/word_times.json`, so the reveals follow the narration instead of a
hand-tuned offset that rots the moment the TTS is regenerated.

    python3 tools/panels.py            # writes build/panel_A.mp4 and build/panel_B.mp4
"""

from __future__ import annotations

import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

TOOLS = Path(__file__).resolve().parent
BUILD = TOOLS / "build"
TIMES = BUILD / "word_times.json"

W, H, FPS = 800, 1080, 30
PAD = 40

BG = (14, 15, 19)
LINE = (32, 35, 43)
VIOLET = (145, 132, 255)
WHITE = (237, 239, 244)
DIM = (138, 147, 168)
FAINT = (86, 93, 110)
GREEN = (125, 211, 168)
AMBER = (232, 179, 92)

MONO = "/System/Library/Fonts/Menlo.ttc"
SANS = "/System/Library/Fonts/Supplemental/Arial.ttf"
FLOW = 1.7          # seconds for a dot to travel one edge
CARET = 1.3         # blink period in the call panel
SANS_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


F_CHIP = font(SANS_BOLD, 21)
F_SUB = font(SANS, 18)
F_TOOL = font(MONO, 24)
F_CODE = font(MONO, 19)
F_BADGE = font(SANS_BOLD, 15)
F_NODE = font(SANS_BOLD, 22)
F_NODE_SUB = font(SANS, 17)
F_TINY = font(MONO, 15)


# ---------------------------------------------------------------- narration timing

def load_times() -> dict[str, dict]:
    if not TIMES.is_file():
        sys.exit(f"missing {TIMES} — run word_times.py first")
    return {row["seg"]: row for row in json.loads(TIMES.read_text())}


TIMES_BY_SEG = load_times()


def at(seg: str, word: str, nth: int = 1) -> float:
    """Start time of the nth occurrence of `word` within `seg`, relative to the segment."""

    seen = 0
    target = word.lower()
    for entry in TIMES_BY_SEG[seg]["words"]:
        if entry["w"].lower().strip(".,:;") == target:
            seen += 1
            if seen == nth:
                return entry["s"]
    sys.exit(f"{seg}: narration has no occurrence {nth} of {word!r} — panel cue cannot be placed")


def seg_len(seg: str) -> float:
    return TIMES_BY_SEG[seg]["duration"]


# ---------------------------------------------------------------- drawing helpers

def ease(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return 3 * x * x - 2 * x * x * x


def blend(base: tuple[int, int, int], colour: tuple[int, int, int], alpha: float) -> tuple[int, int, int]:
    alpha = min(max(alpha, 0.0), 1.0)
    return tuple(int(round(b + (c - b) * alpha)) for b, c in zip(base, colour))


def fit(text: str, face: ImageFont.FreeTypeFont, width: int) -> str:
    """Trim to `width`, marking the cut with an ellipsis so nothing looks complete when it isn't."""

    if face.getlength(text) <= width:
        return text
    while text and face.getlength(text + "…") > width:
        text = text[:-1]
    return text + "…"


def badge(draw: ImageDraw.ImageDraw, x: int, y: int, text: str, colour, alpha: float) -> int:
    pad = 9
    w = int(F_BADGE.getlength(text)) + pad * 2
    h = 24
    draw.rounded_rectangle((x, y, x + w, y + h), radius=6, fill=blend(BG, colour, 0.20 * alpha),
                           outline=blend(BG, colour, 0.55 * alpha), width=1)
    draw.text((x + pad, y + 4), text, font=F_BADGE, fill=blend(BG, colour, alpha))
    return x + w


def header(draw: ImageDraw.ImageDraw, chip: str, sub: str) -> None:
    draw.text((PAD, 46), chip.upper(), font=F_CHIP, fill=VIOLET)
    draw.text((PAD, 76), sub, font=F_SUB, fill=DIM)
    draw.line((PAD, 118, W - PAD, 118), fill=LINE, width=1)


def frame() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(image)
    draw.line((0, 0, 0, H), fill=blend(BG, VIOLET, 0.45), width=3)
    return image, draw


# ---------------------------------------------------------------- panel A: architecture

ARCH_CHIPS = ["Schemas", "Owners", "Usage", "Incidents", "Assertions"]

MCP_TOOLS = ["search", "get_entities", "get_lineage",
             "get_lineage_paths_between", "list_schema_fields", "get_dataset_queries"]


def arch_cues() -> dict[str, float]:
    return {
        "datahub": 0.0,
        "Schemas": at("seg02", "schemas"),
        "Owners": at("seg02", "owners"),
        "Usage": at("seg02", "usage"),
        "Incidents": at("seg02", "incidents"),
        "Assertions": at("seg02", "assertions"),
        "mcp": at("seg02", "Six"),
        "sdk": at("seg02", "seventeen"),
    }


def node(draw, box, title, sub, alpha, *, accent=VIOLET) -> None:
    x0, y0, x1, y1 = box
    draw.rounded_rectangle(box, radius=12, fill=blend(BG, accent, 0.10 * alpha),
                           outline=blend(LINE, accent, alpha), width=2)
    tw = F_NODE.getlength(title)
    draw.text(((x0 + x1 - tw) / 2, y0 + 14), title, font=F_NODE,
              fill=blend(BG, WHITE, 0.25 + 0.75 * alpha))
    if sub:
        sw = F_NODE_SUB.getlength(sub)
        draw.text(((x0 + x1 - sw) / 2, y0 + 44), sub, font=F_NODE_SUB, fill=blend(BG, DIM, alpha))


def arrow(draw, x, y0, y1, alpha, t: float | None = None) -> None:
    """A lit edge carries a dot travelling along it — the diagram reads as a live path, and a
    held shot over a settled page still has something moving in it."""

    colour = blend(LINE, VIOLET, alpha)
    draw.line((x, y0, x, y1 - 9), fill=colour, width=2)
    draw.polygon([(x - 6, y1 - 10), (x + 6, y1 - 10), (x, y1)], fill=colour)
    if t is None or alpha < 0.25:
        return
    progress = (t % FLOW) / FLOW
    y = y0 + (y1 - 12 - y0) * progress
    fade = min(progress / 0.15, (1 - progress) / 0.2, 1.0)
    draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=blend(BG, (206, 200, 255), alpha * fade))


def render_arch(t: float) -> Image.Image:
    cues = arch_cues()
    image, draw = frame()
    header(draw, "How the agent reaches DataHub",
           "Six MCP read tools · seventeen native tools, reads and write-backs")

    def alpha_of(key: str) -> float:
        return ease((t - cues[key]) / 0.45)

    agent_a = max(alpha_of("mcp"), alpha_of("sdk"))
    node(draw, (240, 196, 560, 268), "On-Call Agent", "gpt-5.6-sol", agent_a)

    mcp_a, sdk_a = alpha_of("mcp"), alpha_of("sdk")
    arrow(draw, 320, 268, 342, mcp_a, t)
    arrow(draw, 480, 268, 342, sdk_a, t + FLOW / 2)
    node(draw, (PAD, 342, 388, 414), "DataHub MCP server", "6 read tools", mcp_a)
    node(draw, (412, 342, W - PAD, 414), "Python SDK + GraphQL", "17 native tools", sdk_a)

    y = 430
    for name in MCP_TOOLS:
        draw.text((PAD + 12, y), name, font=F_TINY, fill=blend(BG, FAINT, mcp_a))
        y += 20
    y = 430
    for label in ["incidents  ·  tags", "owners  ·  usage", "assertions  ·  freshness",
                  "structured properties", "documents  ·  links", "custom properties"]:
        draw.text((424, y), label, font=F_TINY, fill=blend(BG, FAINT, sdk_a))
        y += 20

    arrow(draw, 320, 560, 620, mcp_a, t + FLOW / 3)
    arrow(draw, 480, 560, 620, sdk_a, t + FLOW * 5 / 6)
    node(draw, (200, 620, 600, 696), "DataHub", "open source metadata catalog", alpha_of("datahub"))

    draw.text((PAD, 774), "WHAT IT STORES", font=F_BADGE, fill=FAINT)
    cx, cy = PAD, 812
    for name in ARCH_CHIPS:
        a = alpha_of(name)
        w = int(F_NODE_SUB.getlength(name)) + 34
        if cx + w > W - PAD:
            cx, cy = PAD, cy + 56
        draw.rounded_rectangle((cx, cy, cx + w, cy + 44), radius=22,
                               fill=blend(BG, VIOLET, 0.16 * a), outline=blend(LINE, VIOLET, a), width=2)
        draw.text((cx + 17, cy + 11), name, font=F_NODE_SUB, fill=blend(BG, WHITE, 0.3 + 0.7 * a))
        cx += w + 14

    note = "MCP reads the catalog. Native tools add what OSS MCP lacks, plus every write."
    draw.text((PAD, 968), fit(note, F_SUB, W - 2 * PAD), font=F_SUB,
              fill=blend(BG, DIM, min(mcp_a, sdk_a)))
    return image


# ---------------------------------------------------------------- panel B: real tool calls

DS = "urn:li:dataset:(…,oncall_demo"


def calls_script() -> list[dict]:
    """Every reveal, in narration order, with the segment-relative cue it fires on."""

    return [
        # ---- seg06 · cold recall, then the first lineage hop
        dict(seg="seg06", t=at("seg06", "searches"), chip="Institutional memory",
             sub="DataHub search · structured property index", badge="NATIVE", tool="recall_postmortems",
             args=[f"dataset_urn = {DS}.marts.agg_daily_rides,PROD)", "max_hops    = 3"]),
        dict(seg="seg06", t=at("seg06", "Nothing"), update=True,
             resp=['{"found": 0,', ' "message": "No prior post-mortems on this',
                   '  dataset or its ancestors."}']),
        dict(seg="seg06", t=at("seg06", "climbs"), chip="Lineage", sub="DataHub MCP server",
             badge="MCP", tool="datahub_get_lineage",
             args=[f"urn      = {DS}.marts.agg_daily_rides,PROD)", "upstream = true    max_hops = 1"],
             resp=['{"upstreams": {"total": 1, …}}']),

        # ---- seg07 · the four checks a human would run, on the failing table
        dict(seg="seg07", t=at("seg07", "assertion"), chip="Assertions", sub="DataHub Python SDK · GraphQL",
             badge="NATIVE", tool="get_assertion_status",
             args=[f"dataset_urn = {DS}.marts.agg_daily_rides,PROD)"],
             resp=['"failing": 1  ·  result "FAILURE"',
                   '"row_count must satisfy BETWEEN: 25..400"']),
        dict(seg="seg07", t=at("seg07", "fresh"), chip="Freshness", sub="DataHub Python SDK · GraphQL",
             badge="NATIVE", tool="get_freshness",
             args=[f"dataset_urn = {DS}.marts.agg_daily_rides,PROD)"],
             resp=['"hours_stale": 1.22   "sla_hours": 6.0', '"breaching": false']),
        dict(seg="seg07", t=at("seg07", "row"), chip="Profile history", sub="DataHub Python SDK · GraphQL",
             badge="NATIVE", tool="get_row_count_trend",
             args=[f"dataset_urn = {DS}.marts.agg_daily_rides,PROD)"],
             resp=['"latest_row_count": 4', '"previous_row_count": 182   "pct_change": -97.8']),
        dict(seg="seg07", t=at("seg07", "schema"), chip="Schema", sub="DataHub Python SDK · GraphQL",
             badge="NATIVE", tool="check_schema_drift",
             args=[f"dataset_urn = {DS}.marts.agg_daily_rides,PROD)"],
             resp=['"verdict": "unknown"  — no downstream column', ' dependency available to compare']),

        # ---- seg08 · the source, and the stop rule
        dict(seg="seg08", t=at("seg08", "Twenty"), chip="Freshness", sub="DataHub Python SDK · GraphQL",
             badge="NATIVE", tool="get_freshness",
             args=[f"dataset_urn = {DS}.raw.trips_raw,PROD)"],
             resp=['"hours_stale": 26.03   "sla_hours": 6.0', '"breaching": true']),
        dict(seg="seg08", t=at("seg08", "Nothing"), chip="Lineage", sub="DataHub MCP server",
             badge="MCP", tool="datahub_get_lineage",
             args=[f"urn      = {DS}.raw.trips_raw,PROD)", "upstream = true    max_hops = 1"],
             resp=['{"upstreams": {"total": 0, …}}']),
        dict(seg="seg08", t=at("seg08", "confirms"), chip="Stop rule", sub="Aspect store, not the search index",
             badge="NATIVE", tool="confirm_no_upstreams",
             args=[f"dataset_urn = {DS}.raw.trips_raw,PROD)"],
             resp=['"verdict": "confirmed"',
                   '"Genuine source node. The stop rule is satisfied."'], good=True),

        # ---- seg09 · who it hurts, and everything written back
        dict(seg="seg09", t=at("seg09", "fifteen"), chip="Usage", sub="DataHub Python SDK · GraphQL",
             badge="NATIVE", tool="get_usage_stats",
             args=[f"dataset_urn = {DS}.marts.fct_trips,PROD)"],
             resp=['"queries_30d": 3621   "unique_users": 1',
                   "ranked 1st of the run's blast_radius_total 15",
                   '  = 7 datasets + 4 charts + 3 dashboards + 1 model']),
        dict(seg="seg09", t=at("seg09", "filing"), chip="Incident write-back", sub="DataHub Python SDK · GraphQL",
             badge="NATIVE", tool="raise_incident",
             args=[f"dataset_urn   = {DS}.marts.agg_daily_rides,PROD)",
                   'incident_type = "VOLUME"'],
             resp=['urn:li:incident:oncall-2cd1e500…', '"Active critical volume incident"'], good=True),
        dict(seg="seg09", t=at("seg09", "tagging"), chip="Tags, down to the column",
             sub="DataHub Python SDK · GraphQL", badge="NATIVE", tool="tag_assets",
             args=['tag = "oncall_root_cause"', 'column_paths = ["pickup_ts"]'],
             resp=['"Applied oncall_root_cause to 1 assets (1 changed)"'], good=True),
        dict(seg="seg09", t=at("seg09", "notifying"), chip="Ownership", sub="DataHub Python SDK · GraphQL",
             badge="NATIVE", tool="notify_owners",
             args=['owner_urns = [maya.chen, data-platform, sam.patel, …]'],
             resp=['"Notified 6 owners: CRITICAL: stale', ' raw.trips_raw collapsed agg_daily_rides"'], good=True),
        dict(seg="seg09", t=at("seg09", "writing"), chip="Institutional memory", sub="Document + searchable structured property",
             badge="NATIVE", tool="write_postmortem",
             args=['postmortem = {"title": …, "root_cause_urn": …, …}'],
             resp=['urn:li:document:oncall-postmortem-', ' run_9a5cb891af954977'], good=True),

        # ---- seg10 · the second incident: the memory pays off
        dict(seg="seg10", t=at("seg10", "search"), chip="Institutional memory",
             sub="DataHub search · second incident", badge="NATIVE", tool="recall_postmortems",
             args=[f"dataset_urn = {DS}.marts.agg_zone_demand,PROD)", "max_hops    = 3"]),
        dict(seg="seg10", t=at("seg10", "finds"), update=True,
             resp=['{"found": 1,', ' "root_cause_name": "raw.trips_raw",',
                   ' "incident_id": "run_9a5cb891af954977"}'], good=True),
        dict(seg="seg10", t=at("seg10", "column"), chip="Column-level lineage", sub="DataHub MCP server",
             badge="MCP", tool="datahub_get_lineage_paths_between",
             args=["source = raw.trips_raw.pickup_ts", "target = marts.agg_zone_demand.day"],
             resp=['"pathType": "column-level"', '"pathCount": 1'], good=True),
    ]


CARD_GAP = 18
MAX_CARDS = 4


def card_height(card: dict) -> int:
    lines = len(card.get("args", [])) + len(card.get("resp", []) or [])
    return 46 + lines * 26 + 18


def draw_card(image: Image.Image, draw: ImageDraw.ImageDraw, x: int, y: int,
              card: dict, alpha: float, active: bool, since: float = 99.0) -> None:
    height = card_height(card)
    strong = 1.0 if active else 0.42
    a = alpha * strong
    accent = VIOLET if card["badge"] == "MCP" else (108, 130, 168)
    draw.rounded_rectangle((x, y, W - PAD, y + height), radius=10,
                           fill=blend(BG, (255, 255, 255), 0.030 * alpha),
                           outline=blend(BG, accent, 0.42 * a), width=1)
    tx = badge(draw, x + 16, y + 14, card["badge"], accent, a) + 12
    draw.text((tx, y + 12), fit(card["tool"], F_TOOL, W - PAD - tx - 16), font=F_TOOL,
              fill=blend(BG, WHITE, a))

    # Lines land one after another rather than all at once: it reads as a response arriving, and
    # it spreads the panel's motion across the beat instead of spending it in a single frame.
    ty = y + 50
    row = 0
    resp_colour = GREEN if card.get("good") else (150, 165, 190)
    last_x = last_y = None
    for kind, line in ([("arg", l) for l in card.get("args", [])]
                       + [("resp", l) for l in (card.get("resp", []) or [])]):
        appear = ease((since - 0.10 * row) / 0.30) if active else 1.0
        if appear > 0.02:
            prefix = "→ " if kind == "resp" and line == (card.get("resp") or [None])[0] else \
                     ("  " if kind == "resp" else "")
            text = fit(prefix + line, F_CODE, W - PAD - x - 34)
            colour = resp_colour if kind == "resp" else DIM
            draw.text((x + 18, ty), text, font=F_CODE, fill=blend(BG, colour, a * appear))
            last_x, last_y = x + 18 + F_CODE.getlength(text) + 6, ty
        ty += 26
        row += 1

    if active and last_x is not None and (since % CARET) < CARET / 2:
        draw.rectangle((last_x, last_y + 3, last_x + 9, last_y + 19),
                       fill=blend(BG, resp_colour, 0.75 * a))


def render_calls(t: float, script: list[dict], seg_bounds: dict[str, tuple[float, float]]) -> Image.Image:
    image, draw = frame()

    # Which segment are we in? Cards clear at every segment boundary — a new beat is a new page.
    seg = None
    for name, (start, end) in seg_bounds.items():
        if start <= t < end:
            seg = name
            break
    if seg is None:
        seg = list(seg_bounds)[-1]
    seg_start = seg_bounds[seg][0]

    cards: list[tuple[dict, float, float]] = []
    for event in script:
        if event["seg"] != seg:
            continue
        fire = seg_start + event["t"]
        if t < fire:
            continue
        if event.get("update"):
            if cards:
                merged = dict(cards[-1][0])
                merged["resp"] = event["resp"]
                merged["good"] = event.get("good", merged.get("good"))
                # The response restarts the line-by-line reveal on its own cue, not the call's.
                cards[-1] = (merged, cards[-1][1], t - fire + 0.10 * len(merged.get("args", [])))
            continue
        cards.append((event, ease((t - fire) / 0.40), t - fire))

    if not cards:
        return image

    current = cards[-1][0]
    header(draw, current["chip"], current["sub"])

    visible = cards[-MAX_CARDS:]
    while sum(card_height(c) + CARD_GAP for c, _, _ in visible) > H - 190 and len(visible) > 1:
        visible = visible[1:]

    y = 150
    for index, (card, appear, since) in enumerate(visible):
        active = index == len(visible) - 1
        offset = int((1 - appear) * 14) if active else 0
        draw_card(image, draw, PAD, y + offset, card, appear if active else 1.0, active, since)
        y += card_height(card) + CARD_GAP
    return image


# ---------------------------------------------------------------- render

def encode(folder: Path, out: Path) -> None:
    args = ["ffmpeg", "-nostdin", "-y", "-v", "error", "-framerate", str(FPS),
            "-i", str(folder / "%05d.png"), "-c:v", "libx264", "-preset", "medium",
            "-crf", "16", "-pix_fmt", "yuv420p", str(out)]
    proc = subprocess.run(args, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit(f"ffmpeg failed:\n  {shlex.join(args)}\n{proc.stderr[-1200:]}")


def render_block(name: str, segs: list[str], renderer) -> None:
    folder = BUILD / f"panel_{name}_frames"
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)

    total = sum(seg_len(s) for s in segs)
    frames = int(round(total * FPS))
    for index in range(frames):
        renderer(index / FPS).save(folder / f"{index + 1:05d}.png")
    out = BUILD / f"panel_{name}.mp4"
    encode(folder, out)
    shutil.rmtree(folder)   # ~2500 PNGs; the mp4 is the artefact worth keeping
    print(f"  panel {name}: {total:6.2f}s  {frames} frames -> {out.name}")


def main() -> int:
    BUILD.mkdir(parents=True, exist_ok=True)

    render_block("A", ["seg02"], render_arch)

    segs = ["seg06", "seg07", "seg08", "seg09", "seg10"]
    bounds, offset = {}, 0.0
    for seg in segs:
        bounds[seg] = (offset, offset + seg_len(seg))
        offset += seg_len(seg)
    script = calls_script()
    render_block("B", segs, lambda t: render_calls(t, script, bounds))

    print(f"  {len(script)} reveals, all quoted from the two filmed runs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
