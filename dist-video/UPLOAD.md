# Demo video — upload package

**Files in this folder**

| file | what |
|---|---|
| `oncall-demo.mp4` | final cut, 2:13, 1440×900, H.264 + AAC, 7.5 MB |
| `oncall-demo.srt` | 66 captions, word-timestamped |

Under the hackathon's 3:00 cap. Every frame is the real running app against a live DataHub
quickstart — no mockups, no motion graphics, no re-enactment.

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

What you're watching, in order:
0:00  The problem — the 2am page, and three hours of walking lineage by hand
0:17  A staged failure: an ingestion job stalls and quality signals fire
0:27  One click starts the triage
0:36  The investigation — memory first, then lineage upstream hop by hop, checking assertions,
      freshness, row counts and schema at every node, and stopping only at a breach with no
      unhealthy parent
1:17  Blast radius ranked by usage, then the write-back landing inside DataHub itself
1:40  The same root cause breaks a different table three hops away — the agent recalls its own
      post-mortem, verifies it against live evidence, and goes straight to the answer
1:58  Cold versus memory-assisted, side by side

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

## Notes for whoever uploads

- **Turn captions on by default** if the platform allows it — the narration is deliberately free of
  spoken percentages (per-run variance makes them unsafe to say aloud), so the on-screen figures
  and captions carry the numbers.
- The chapter timestamps above are accurate to this cut. Re-derive them if the video is re-edited.
- Do not add a music bed without re-checking the narration level (mean −20.4 dB, peak −2.9 dB).
