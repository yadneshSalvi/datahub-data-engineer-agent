#!/usr/bin/env python3
"""Prove every figure on the split-screen panels came out of the filmed runs.

The panels quote real tool calls. "Quote" is easy to claim and easy to drift from, so this checks
it mechanically: for each card, find the matching call in `backend/data/oncall.db`, then require
that every number and every quoted string printed on the card appears verbatim in that call's own
arguments or response. A fabricated figure, a stale copy-paste, or a number nudged to look better
fails here rather than in front of a judge.

    python3 tools/check_evidence.py

Exit 0 = every panel figure is traceable to a row in the run log.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
DB = TOOLS.parents[1] / "backend" / "data" / "oncall.db"

COLD = "run_9a5cb891af954977"
RECALL = "run_71b45939d95844ab"
RUN_OF = {"seg06": COLD, "seg07": COLD, "seg08": COLD, "seg09": COLD, "seg10": RECALL}

# Values that are true of the cut rather than of one call, each with where it is checked instead.
ALLOWED = {
    "15": "blast_radius_total in write_postmortem's authoritative_counts",
    "7": "authoritative_counts.datasets",
    "4": "authoritative_counts.charts",
    "3": "authoritative_counts.dashboards / max_hops",
    "1": "authoritative_counts.ml_models",
}


def events(run: str) -> list[tuple[dict, dict]]:
    db = sqlite3.connect(DB)
    calls, results = {}, {}
    for (payload,) in db.execute(
            "select payload from run_events where run_id=? and kind='tool_call' order by seq", (run,)):
        row = json.loads(payload)
        calls[row["call_id"]] = row
    for (payload,) in db.execute(
            "select payload from run_events where run_id=? and kind='tool_result' order by seq", (run,)):
        row = json.loads(payload)
        results[row["call_id"]] = row
    return [(call, results.get(cid, {})) for cid, call in calls.items()]


def squash(text: str) -> str:
    """Collapse runs of whitespace: a panel wraps a long response over several lines, and the
    line breaks are a layout choice, not a difference in what it says."""

    return re.sub(r"\s+", " ", text)


def haystack(call: dict, result: dict) -> str:
    return squash(json.dumps(call.get("args", {})) + " " + json.dumps(result.get("payload", {}))
                  + " " + str(result.get("summary", "")))


def tokens(card: dict) -> list[str]:
    """The numbers and quoted phrases a viewer can read off the card."""

    text = squash(" ".join(card.get("args", []) + (card.get("resp", []) or [])))
    found = re.findall(r'"[^"]{2,}"', text) + re.findall(r"-?\d+\.?\d*", text)
    return [squash(t.strip('"')) for t in found]


def main() -> int:
    sys.path.insert(0, str(TOOLS))
    import panels                                          # noqa: E402

    # An `update` entry carries the response for the card before it. Fold the two together so a
    # deferred response is checked as part of its own card rather than silently skipped.
    merged = []
    pending = None
    for card in panels.calls_script():
        if card.get("update"):
            if pending:
                pending = dict(pending)
                pending["resp"] = card["resp"]
                merged.append(pending)
                pending = None
            continue
        if pending:
            merged.append(pending)
        pending = card
    if pending:
        merged.append(pending)

    cache = {run: events(run) for run in {COLD, RECALL}}
    failures, checked = [], 0

    for card in merged:
        run = RUN_OF[card["seg"]]
        matches = [(c, r) for c, r in cache[run] if c["tool"] == card["tool"]]
        if not matches:
            failures.append(f'{card["seg"]} {card["tool"]}: no such call in {run}')
            continue

        for value in tokens(card):
            checked += 1
            if any(value in haystack(c, r) for c, r in matches):
                continue
            if value in ALLOWED:
                continue
            failures.append(f'{card["seg"]} {card["tool"]}: {value!r} is on the panel '
                            f"but not in any {card['tool']} call of {run}")

    # The blast-radius breakdown is the one panel figure sourced from a different field; check it
    # explicitly rather than waving it through the allow-list.
    counts = None
    for call, result in cache[COLD]:
        if call["tool"] == "write_postmortem":
            counts = (result.get("payload") or {}).get("authoritative_counts")
    if not counts:
        failures.append("cold run has no authoritative_counts to source the blast radius from")
    else:
        expected = {"blast_radius_total": 15, "datasets": 7, "charts": 4,
                    "dashboards": 3, "ml_models": 1}
        for key, value in expected.items():
            checked += 1
            if counts.get(key) != value:
                failures.append(f"authoritative_counts.{key} is {counts.get(key)}, panel says {value}")
        if sum(expected[k] for k in ("datasets", "charts", "dashboards", "ml_models")) != 15:
            failures.append("the breakdown shown on the panel does not add up to 15")

    print(f"cards checked: {len(merged)}   figures checked: {checked}")
    print(f"cold run   {COLD}: {len(cache[COLD])} calls")
    print(f"recall run {RECALL}: {len(cache[RECALL])} calls")
    if failures:
        print(f"\nFAIL — {len(failures)} figure(s) not traceable:")
        for line in failures:
            print(f"  {line}")
        return 1
    print("\nPASS: every number and quoted string on the panels appears in the run log it claims.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
