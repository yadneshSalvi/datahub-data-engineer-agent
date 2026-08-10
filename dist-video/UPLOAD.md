# Demo video — upload package

**Files in this folder**

| file | what |
|---|---|
| `oncall-demo.mp4` | final cut, 2:51.6 (171.561 s), 1920×1080, H.264 + AAC, 25,038,088 bytes |
| `oncall-demo.srt` | 43 captions, timed from the audio, worded from the script |

Under the hackathon's 3:00 cap. Every frame of footage is the real running app against a live
DataHub quickstart. The only drawn elements are the split-screen panels, and everything they
display is quoted from the run log of the two runs on screen.

Rebuild it with `tools/`: `tts.py` → `verify_audio.py` → `word_times.py` → `panels.py` →
`assemble.py` → `subtitles.py`, then `verify_cut.py` and `check_evidence.py` to gate it.

---

## Who this cut is for

A hackathon judge who wants to know **how DataHub was used**, with the technical detail, in order.
The narration therefore follows one line: what breaks, what DataHub provides, how the agent uses
each capability at the moment it uses it, and what it costs. Terms are defined the first time they
appear — catalog, MCP server, assertion, lineage, structured property, column-level lineage.

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

Alongside the footage, split-screen panels show the actual MCP and SDK calls the agent made,
with their real responses, at the moment the narration reaches them.

Chapters:
0:00  What a data catalog is, and what DataHub maps
0:17  How the agent reaches DataHub: the MCP server and the Python SDK
0:37  The control panel: 23 healthy assets, empty signal inbox
0:48  A stopped ingestion job, and the assertions that start failing
1:03  One click hands over the page
1:15  Memory first — a cold start, then the walk up the lineage
1:33  The four checks it runs at every table
1:45  The root cause: trips_raw, 26 hours stale, and the stop rule that confirms it
2:03  Blast radius ranked by usage, and the write-backs landing in DataHub
2:21  A second incident three hops away — the agent recalls its own post-mortem
2:36  Cold versus memory-assisted, side by side

How it reads and writes DataHub:
· Catalog reads go through the DataHub MCP Server — six read tools: search, get_entities,
  get_lineage, get_lineage_paths_between, list_schema_fields, get_dataset_queries.
· Assertion status, freshness, usage, incidents and every write go through the DataHub Python SDK
  and GraphQL — seventeen native tools. That split is deliberate: on OSS, MCP's
  get_dataset_assertions is Cloud-only, so it cannot supply the trigger.
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

## The split-screen panels, and what is in them

Four times the frame splits: the footage holds in a pixel-locked 1120×1080 left pane and a panel
animates beside it. The panels are the only drawn material in the cut.

| beat | panel |
|---|---|
| 0:17 | Architecture. Agent → DataHub MCP server (6 read tools) and → Python SDK + GraphQL (17 native tools) → DataHub. Nodes light as the narration names them. |
| 1:15–2:36 | The agent's real calls, revealed one at a time: `recall_postmortems`, `datahub_get_lineage`, the four health checks, `confirm_no_upstreams`, `get_usage_stats`, `raise_incident`, `tag_assets`, `notify_owners`, `write_postmortem`, `datahub_get_lineage_paths_between`. |

**Every figure on a panel is quoted from `backend/data/oncall.db`** — the persisted run log of
`run_9a5cb891af954977` (cold) and `run_71b45939d95844ab` (recall), the two runs on screen.
`tools/check_evidence.py` enforces this mechanically: it re-reads the database and fails the build
unless every number and every quoted string printed on a panel appears verbatim in the arguments or
response of a call of that name in that run. 89 figures across 16 cards currently pass.

Long responses are abbreviated with a visible `…`, never silently truncated.

**One number is not quoted from a raw response, deliberately.** The raw downstream lineage response
reads `"total": 16`, because it counts an unranked ML feature; the run's own `authoritative_counts`
— and the app, and the narration — say 15. Putting the raw 16 beside the spoken "fifteen" would
read as a contradiction, so the panel shows the authoritative breakdown instead: 7 datasets +
4 charts + 3 dashboards + 1 ML model = 15. `check_evidence.py` checks that breakdown against the
run's `authoritative_counts` rather than waving it through.

## What is on screen, and what is claimed

| spoken | verified against |
|---|---|
| "twenty three assets … all healthy" | `/api/demo/state` → 23 entities; catalog donut 23 / 0 / 0 |
| "collapsed to four rows … expected at least twenty five" | `demo/catalog.py` assertion `ROW_COUNT BETWEEN 25 AND 400`; `demo/break.py` sets `row_count=4` |
| "twenty six hours stale against a six hour limit" | `get_freshness` on `raw.trips_raw`: `hours_stale 26.03`, `sla_hours 6.0`, `breaching true` |
| "fifteen assets" | run `blast_radius_total` = 15 |
| "twenty four percent fewer tool calls, fourteen percent less time, the same three hops" | the filmed pair: 92 → 70 calls, 83.02 s → 71.50 s to root cause, 3 → 3 hops. The `/compare` screen showing `24% LESS`, `14% LESS` and `SAME` is on camera while the line is spoken. |

The percentages are the only figures spoken aloud, they carry the qualifier "on this pair of runs",
and the screen showing them is in frame at that moment. No figure is rounded in our favour.

## Honesty notes on the edit

- **Nothing is sped up.** Every shot plays at 1.0× or slower — several are slowed slightly to cover
  their narration. No shot therefore carries a speed chip, and a slowed shot is never labelled as
  fast. `assemble.py` refuses to build a segment whose narration outruns its clip, so a shortfall
  fails the build instead of being padded with cloned frames.
- **1:33 and 1:45 are a deliberate replay** of the finished run, not the live take. The event
  timeline does not auto-scroll, so the live capture sits motionless for minutes. A completed run
  is a permanently replayable record, so it is driven on purpose to show the per-table checks and
  the resolved causal path. The elapsed counters in those shots read the finished run's totals;
  they are not a clock ticking.
- **2:03's left pane is a two-scene re-cut** (`clip09_split`) assembled from the existing clip09
  masters: the ranked blast radius, then a hard cut to the DataHub page carrying the write-backs.
  One fixed crop could not frame both. No footage was re-shot for this cut.
- **The camera is either still or moving on purpose.** Each full-frame shot establishes locked,
  draws an accent border around the region the narration is about to name, eases in over about a
  second, then holds perfectly still. Inside a split-screen block the camera never moves at all —
  the panel does. Measured across the finished cut: median inter-frame change 0.011, no sustained
  movement run over 2.5 s, and the longest span in which *nothing at all* moves is 3.9 s, which is
  an intended establish/dwell hold.
- **Captions** are worded from `tools/narration.txt` and timed from Deepgram's word alignment, so
  a recognition error can never become a caption. Measured sync across all 43 cues: median 0.000 s.

## Notes for whoever uploads

- **Turn captions on by default** if the platform allows it.
- Captions must not be regenerated from an auto-transcribe feature; they would lose the script's
  spelling of `agg_daily_rides`, `trips_raw` and the tool names.
- The chapter timestamps above are accurate to this cut. Re-derive them if the video is re-edited.
- Do not add a music bed without re-checking the narration level.
