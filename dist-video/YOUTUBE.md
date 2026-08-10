# YouTube upload: copy-paste pack

**Published:** <https://youtu.be/8VTZzn7bgtE>

**Video file:** `oncall-demo.mp4` · **Captions:** upload `oncall-demo.srt` (English) ·
**Thumbnail:** `oncall-demo-thumbnail.png` (1280x720) · **Visibility:** Public

## Title (89 characters, limit is 100)

```
On-Call Data Engineer Agent: root-cause triage that writes its memory back into DataHub
```

## Description

```
An autonomous on-call data engineer for DataHub. When a data-quality assertion fails or a freshness SLA breaks, it walks column-level lineage upstream to the first intrinsically broken node, ranks the downstream blast radius by real usage, files an incident, tags the root cause down to the column, notifies the owners it read off the ownership metadata, and writes a structured post-mortem back into DataHub so the next incident on that lineage resolves faster.

Code, setup instructions and the committed run artifacts: https://github.com/yadneshSalvi/datahub-data-engineer-agent

Built for "Build with DataHub: The Agent Hackathon", in the Agents That Do Real Work track. Every frame of footage is the real app running against a live DataHub quickstart. The split-screen panels are the only drawn elements, and everything they display is quoted from the recorded logs of the two runs on screen.

How it reads and writes DataHub:
- Catalog reads go through the DataHub MCP Server. Six read tools: search, get_entities, get_lineage, get_lineage_paths_between, list_schema_fields, get_dataset_queries.
- Seventeen native tools on the DataHub Python SDK and GraphQL cover what OSS MCP cannot reach (assertion status, freshness, row-count history, usage) as well as every write. The division is not reads versus writes: ten of the seventeen are reads. On OSS, MCP's get_dataset_assertions is Cloud-only, so it cannot supply the trigger at all.
- Write-back: incidents, dataset and column-level tags, institutional-memory links, a searchable oncall.postmortem structured property that acts as the recall index, document entities, and merged custom properties.

The comparison at the end is two runs on one seeded warehouse, same root cause, different symptoms: 24% fewer tool calls and 14% less time to root cause with memory. The agent is non-deterministic and the figures move between runs; the repo commits both runs' verbatim records and documents the observed variance.

Chapters
0:00 What a data catalog is, and what DataHub maps
0:18 How the agent reaches DataHub: six MCP tools and seventeen of its own
0:39 The control panel: 23 healthy assets, empty signal inbox
0:51 A stopped ingestion job, and the assertions that start failing
1:06 One click hands over the page
1:18 Memory first: a cold start, then the walk up the lineage
1:36 The four checks it runs at every table
1:47 The root cause: trips_raw, 26 hours stale, and the stop rule that confirms it
2:03 Blast radius ranked by usage, and the write-backs landing in DataHub
2:22 A second incident three hops away: the agent recalls its own post-mortem
2:38 Cold versus memory-assisted, side by side

Apache 2.0, reproducible from scratch against a stock datahub docker quickstart.

#DataHub #DataEngineering #AIAgents #MCP #DataLineage #DataQuality
```

## Tags (video tags field)

```
datahub, data engineering, data quality, data lineage, ai agents, llm, observability, root cause analysis, mcp, model context protocol, openai agents sdk, data catalog, incident response
```

## After upload

1. Confirm visibility is Public and captions are attached.
2. Paste the URL into README.md (replace the "upload pending" line in the Demo video section).
3. Paste the URL into the Devpost form (see `plans/09b_devpost_submission_final.md`).
