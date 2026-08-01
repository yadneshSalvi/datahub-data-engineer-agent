# Generated examples

Real artifacts from two triage runs against the seeded RideFlow warehouse. Nothing here is
hand-written or illustrative — every file is verbatim agent output, and these same two runs are the
basis of the measurement in the root README.

## The two runs

| Run                                | Trigger (symptom)                          | Root cause found | Recall                             | Time to root cause | Tool calls |
| ---------------------------------- | ------------------------------------------ | ---------------- | ---------------------------------- | -----------------: | ---------: |
| `run_93130e4fb6f84e58` (**cold**)   | `marts.agg_daily_rides` row-count assertion | `raw.trips_raw`  | none                               |             87.5 s |         93 |
| `run_332299d97bdd4b34` (**recall**) | `marts.agg_zone_demand` row-count assertion | `raw.trips_raw`  | prior post-mortem, 3 hops upstream |             33.2 s |         72 |

Same root cause, **different symptoms**, with `demo/reset.py --keep-memory` between them — so the
only difference is what the agent remembered. **These are the two runs shown in the demo video.**

## Files

```
postmortems/
  cold-run_93130e4fb6f84e58.{md,json}       post-mortem the cold run wrote back to DataHub
  recall-run_332299d97bdd4b34.{md,json}     post-mortem the memory-assisted run wrote back
runs/
  cold-run_93130e4fb6f84e58-events.json     full 282-frame event log
  recall-run_332299d97bdd4b34-events.json   full 220-frame event log
notifications/
  cold-run_93130e4fb6f84e58.json            exact owner-notification payload
  recall-run_332299d97bdd4b34.json          exact payload from the recall run
incidents/
  cold-incident.json, recall-incident.json  the raise_incident inputs and resulting URNs
snapshots/
  compare.json                              verbatim GET /api/compare response for this pair
  signals.json                              verbatim GET /api/signals feed
```

## How to read them

- The **`.md` post-mortems** are what a human opens from the root-cause dataset's institutional
  memory link in DataHub. The **`.json`** siblings are the same content as the structured-property
  value that powers recall.
- The **event logs** are the exact frames the UI replays; opening `/runs/<id>` in the app renders
  these identically. Every `tool_call` / `tool_result` pair is a real DataHub read or write,
  `finding` frames are per-node health evidence, and `recall` / `causal_path` / `blast_radius` /
  `action` frames drive the timeline.
- **`compare.json`** is the source for the headline claim; its `deltas` block carries both absolute
  and percentage change.
- **Incident payloads** are reconstructed from the committed event logs rather than read back from
  GMS, because a full reset hard-deletes the incidents it created. The `provenance` field in each
  file says so.

Notification receipts are written to `data/notifications/` at runtime (gitignored). The two here
are curated copies from the runs above, kept so the payload format is reviewable without running
anything.

## Regenerating

These are reproducible, not precious:

```bash
./scripts/reset.sh
cd backend
uv run python -m demo.break --scenario stale_upstream
uv run python -m oncall_agent.cli triage --auto      # the cold run
uv run python -m demo.reset --keep-memory
uv run python -m demo.break --scenario recall_hit
uv run python -m oncall_agent.cli triage --auto      # the recall run
```

Exact numbers differ run to run — the agent is not deterministic. What reproduces is the structure,
the root cause, and the direction and rough magnitude of the memory effect.
