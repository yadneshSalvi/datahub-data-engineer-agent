# Demo video — upload package

**Files in this folder**

| file | what |
|---|---|
| `oncall-demo.mp4` | final cut, 2:52.8 (172.761 s), 1920×1080, H.264 + AAC, 22,041,240 bytes |
| `oncall-demo.srt` | 45 captions, timed from the audio, worded from the script |

Under the hackathon's 3:00 cap. Every frame is the real running app against a live DataHub
quickstart — no mockups, no motion graphics, no re-enactment.

Rebuild it with `tools/`: `tts.py` → `verify_audio.py` → `assemble.sh` → `subtitles.py`.

---

## YouTube title

```
On-Call Data Engineer Agent — root-cause triage that writes its memory back into DataHub
```

Alternate, shorter:
```
An AI agent that triages data incidents in DataHub — and gets faster every time
```

## YouTube description

```
An autonomous on-call data engineer for DataHub. When a data-quality assertion fails or a
freshness SLA breaks, it walks column-level lineage upstream to the first intrinsically broken
node, ranks the downstream blast radius by real usage, files an incident, tags the root cause down
to the column, notifies the owners it read off the ownership metadata — and writes a structured
post-mortem back into DataHub so the next incident on that lineage resolves faster.

Built for "Build with DataHub: The Agent Hackathon" (Agents That Do Real Work).

Narrated for viewers who have never used DataHub: every term is defined the first time it appears.

Chapters:
0:00  What a data catalog is, and what DataHub tracks
0:18  The 2am page, and the hours of walking lineage by hand
0:32  The control panel: 23 healthy assets, empty signal inbox
0:45  A real failure, staged: an ingestion job stalls and the inbox fills
0:59  One click starts the triage
1:12  Memory first — a cold start, with no prior post-mortem to recall
1:25  Walking the lineage upward, checking what a human would at every table
1:41  The root cause: trips_raw, 26 hours stale against a 6-hour freshness limit
2:01  Blast radius ranked by usage, and the write-back landing inside DataHub
2:21  A different table breaks three hops away — the agent recalls its own post-mortem
2:37  Cold versus memory-assisted, side by side

How it reads and writes DataHub:
· Catalog reads go through the DataHub MCP Server (search, entities, lineage, lineage paths,
  schema fields, queries).
· Assertion status, freshness, incidents, usage and every write go through the DataHub Python SDK
  and GraphQL. That split is deliberate: on OSS, MCP's get_dataset_assertions is Cloud-only, so it
  cannot supply the trigger.
· Write-back: incidents, dataset and column-level tags, institutional-memory links, a searchable
  oncall.postmortem structured property (the recall index), document entities, and merged custom
  properties.

The memory effect shown at the end is two runs on one seeded warehouse — same root cause,
different symptoms — not a benchmark. The agent is non-deterministic and the figures move between
runs; the repo documents the measurement basis and the observed variance.

Apache-2.0, reproducible from scratch against a stock `datahub docker quickstart`:
https://github.com/yadneshSalvi/datahub-data-engineer-agent
```

## Tags

`datahub` `data engineering` `data quality` `data lineage` `ai agents` `llm` `observability`
`root cause analysis` `mcp` `model context protocol` `openai agents sdk` `data catalog`

---

## What is on screen, and what is claimed

Every number spoken in the narration is a deterministic property of the seeded scenario, verified
against the run that is on screen at that moment:

| spoken | verified against |
|---|---|
| "twenty three assets … all healthy" | `/api/demo/state` → 23 entities; catalog donut 23 / 0 / 0 |
| "collapsed to four rows … expected at least twenty five" | `demo/catalog.py` assertion `ROW_COUNT BETWEEN 25 AND 400`; `demo/break.py` sets `row_count=4` |
| "twenty six hours stale against a six hour freshness limit" | signal detail `26.0h stale · SLA 6h`; run summary `26.03 hours` |
| "fifteen assets" | run blast radius length = 15 |

No percentage or timing figure is ever spoken, because those move run to run. The `/compare`
panel shows them on screen and the captions carry them, so the claim is always tied to the pair of
runs being displayed.

## Honesty notes on the edit

- **The `2x speed` chip at 1:12** is real and required. The screen recorder only emits a frame when
  pixels change, so the live-run capture is 166 s of video for a 315 s run — the elapsed counter in
  that shot advances about twice real time. The chip says so rather than letting the clock imply
  the agent is faster than it is. No other shot is sped up; several are slightly *slowed* to cover
  their narration, and slow shots are never labelled as fast.
- **1:25 and 1:41 are a deliberate replay** of the finished run, not the live take. The event
  timeline does not auto-scroll, so the live capture sits motionless for minutes. A completed run
  is a permanently replayable record, so it is driven on purpose to show the per-table checks and
  the resolved causal path.
- **Every shot pans slowly** across a 2x (3200×1800) master. That is what keeps the frame alive
  through passages where the UI itself is not animating; the pixels are unretouched app output.

## Notes for whoever uploads

- **Turn captions on by default** if the platform allows it — the narration is deliberately free of
  spoken percentages, so the on-screen figures and captions carry the numbers.
- Captions are worded from `tools/narration.txt` and timed from the audio, so they never contain a
  speech-recognition error. Do not regenerate them from an auto-transcribe feature.
- The chapter timestamps above are accurate to this cut. Re-derive them if the video is re-edited.
- Do not add a music bed without re-checking the narration level (mean −21.4 dB, peak −1.1 dB).
