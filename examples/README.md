# Generated examples

Every artifact listed here came from the running backend on `localhost:8001` or from the active
incident read back from DataHub GMS. The post-mortems are paired Markdown and structured JSON
representations of the same generated content; none are hand-written fixtures.

Both comparison records report the `stale_upstream` scenario. The second is a real repeated triage
that recalled prior memory; it is the pair auto-selected by the live `/api/compare` endpoint. The
`recall_hit` walkthrough in the project README exercises the same memory branch from a different
symptom dataset.

## Cold run: `run_c47c5d9bd22f40b6`

- [Cold post-mortem, Markdown](postmortems/cold-run_c47c5d9bd22f40b6.md) — narrative stored in the
  DataHub Document.
- [Cold post-mortem, JSON](postmortems/cold-run_c47c5d9bd22f40b6.json) — structured payload stored
  in `oncall.postmortem` and used as the recall index.
- [Incident payload](incidents/incident-56de1e0c-77f6-45d1-a6ad-e9cad29d58b9.json) — the active
  incident read back through DataHub GraphQL. The idempotent action reused this incident on the
  later run.
- [Notification payload](notifications/56de1e0c-77f6-45d1-a6ad-e9cad29d58b9.json) — exact mock
  webhook receipt sent to the six resolved user/group owners during the cold run.

This run had no recalled memory. It made 71 tool calls and confirmed the root cause in 65.514
seconds.

## Recall run: `run_d7d8f9f635e54121`

- [Recall post-mortem, Markdown](postmortems/recall-run_d7d8f9f635e54121.md) — generated narrative
  after verifying a recalled root cause.
- [Recall post-mortem, JSON](postmortems/recall-run_d7d8f9f635e54121.json) — structured payload
  containing the prior incident IDs used by the run.
- [Full run event log](runs/recall-run_d7d8f9f635e54121-events.json) — the complete ordered event
  list returned by `/api/runs/run_d7d8f9f635e54121/events`, including recall, reasoning, tool,
  finding, action, post-mortem, metric, and completion events.

This run used memory, made 50 tool calls, and confirmed the root cause in 38.606 seconds.

## API snapshots

- [`/api/signals`](snapshots/signals.json) — live failing-signal inbox while `stale_upstream` was
  armed.
- [`/api/compare`](snapshots/compare.json) — the full cold and recalled run records plus computed
  deltas. It is the source for the rounded README comparison.

Other files in `notifications/` are receipts from earlier development runs and are retained as
real generated evidence; the notification linked above is the one corresponding to the submitted
cold/recall comparison pair's incident.
