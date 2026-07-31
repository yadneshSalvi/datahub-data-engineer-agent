"""Async facade over the local SQLite run, event, and post-mortem mirror."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from oncall_agent.agent.events import Event, event_from_json, utc_now_iso
from oncall_agent.agent.models import PostMortem, TriageReport, TriggerSpec

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY, created_at TEXT NOT NULL, finished_at TEXT,
  status TEXT NOT NULL,
  trigger_urn TEXT NOT NULL, trigger_name TEXT NOT NULL,
  signal_kind TEXT NOT NULL, signal_detail TEXT,
  scenario TEXT,
  root_cause_urn TEXT, root_cause_name TEXT,
  incident_urn TEXT, postmortem_id TEXT,
  summary TEXT,
  duration_s REAL, time_to_root_cause_s REAL,
  tool_calls INTEGER DEFAULT 0, hops_walked INTEGER DEFAULT 0,
  recall_used INTEGER DEFAULT 0,
  recalled_ids TEXT,
  causal_path TEXT, blast_radius TEXT, actions TEXT, findings TEXT,
  error TEXT
);
CREATE TABLE IF NOT EXISTS run_events (
  run_id TEXT NOT NULL, seq INTEGER NOT NULL, ts TEXT NOT NULL,
  kind TEXT NOT NULL, payload TEXT NOT NULL,
  PRIMARY KEY (run_id, seq)
);
CREATE TABLE IF NOT EXISTS postmortems (
  id TEXT PRIMARY KEY, run_id TEXT NOT NULL, created_at TEXT NOT NULL,
  title TEXT NOT NULL, symptom TEXT, symptom_urn TEXT,
  root_cause_urn TEXT NOT NULL, root_cause_name TEXT,
  doc_markdown TEXT NOT NULL, doc_json TEXT NOT NULL,
  datahub_document_urn TEXT, datahub_links TEXT,
  reused_count INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_events_run ON run_events(run_id, seq);
CREATE INDEX IF NOT EXISTS ix_pm_root ON postmortems(root_cause_urn);
"""

_JSON_RUN_COLUMNS = {"recalled_ids", "causal_path", "blast_radius", "actions", "findings"}


class Store:
    """Serialize SQLite work through ``asyncio.to_thread`` with WAL enabled."""

    def __init__(self, path: Path, connection: sqlite3.Connection) -> None:
        self.path = path
        self._connection = connection
        self._lock = threading.RLock()
        self._closed = False

    @classmethod
    async def open(cls, path: str | Path) -> Store:
        """Create the database and schema, then return an open store."""

        resolved = Path(path).expanduser().resolve()
        return await asyncio.to_thread(cls._open_sync, resolved)

    @classmethod
    def _open_sync(cls, path: Path) -> Store:
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        connection.executescript(SCHEMA)
        connection.commit()
        return cls(path, connection)

    async def close(self) -> None:
        """Flush and close the underlying SQLite connection."""

        if self._closed:
            return
        await asyncio.to_thread(self._close_sync)

    def _close_sync(self) -> None:
        with self._lock:
            if not self._closed:
                self._connection.commit()
                self._connection.close()
                self._closed = True

    async def create_run(
        self,
        run_id: str,
        trigger: TriggerSpec,
        *,
        scenario: str | None = None,
    ) -> None:
        """Insert the initial running row for a triage."""

        await asyncio.to_thread(self._create_run_sync, run_id, trigger, scenario)

    async def start_run(
        self,
        run_id: str,
        trigger: TriggerSpec,
        *,
        scenario: str | None = None,
    ) -> None:
        """Alias for ``create_run`` used by lifecycle callers."""

        await self.create_run(run_id, trigger, scenario=scenario)

    def _create_run_sync(
        self,
        run_id: str,
        trigger: TriggerSpec,
        scenario: str | None,
    ) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO runs (
                  id, created_at, status, trigger_urn, trigger_name,
                  signal_kind, signal_detail, scenario
                ) VALUES (?, ?, 'running', ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    utc_now_iso(),
                    trigger.dataset_urn,
                    trigger.name,
                    trigger.signal_kind,
                    trigger.signal_detail,
                    scenario,
                ),
            )

    async def append_event(self, event: Event) -> None:
        """Persist one explicit event DTO."""

        await self.append_events([event])

    async def append_events(self, events: list[Event]) -> None:
        """Persist an ordered batch idempotently."""

        rows = [
            (event.run_id, event.seq, event.ts, event.kind, event.model_dump_json())
            for event in events
        ]
        await asyncio.to_thread(self._append_events_sync, rows)

    def _append_events_sync(self, rows: list[tuple[str, int, str, str, str]]) -> None:
        with self._lock, self._connection:
            self._connection.executemany(
                """
                INSERT OR REPLACE INTO run_events (run_id, seq, ts, kind, payload)
                VALUES (?, ?, ?, ?, ?)
                """,
                rows,
            )

    async def finish_run(self, report: TriageReport) -> None:
        """Finalize all metrics and JSON accumulators for a run."""

        await asyncio.to_thread(self._finish_run_sync, report)

    async def complete_run(self, report: TriageReport) -> None:
        """Alias for ``finish_run`` used by lifecycle callers."""

        await self.finish_run(report)

    def _finish_run_sync(self, report: TriageReport) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                UPDATE runs SET
                  finished_at=?, status=?, root_cause_urn=?, root_cause_name=?,
                  incident_urn=?, postmortem_id=?, summary=?, duration_s=?,
                  time_to_root_cause_s=?, tool_calls=?, hops_walked=?, recall_used=?,
                  recalled_ids=?, causal_path=?, blast_radius=?, actions=?, findings=?, error=?
                WHERE id=?
                """,
                (
                    utc_now_iso(),
                    report.status,
                    report.root_cause_urn,
                    report.root_cause_name,
                    report.incident_urn,
                    report.postmortem_id,
                    report.summary,
                    report.duration_s,
                    report.time_to_root_cause_s,
                    report.tool_calls,
                    report.hops_walked,
                    int(report.recall_used),
                    json.dumps(report.recalled_ids),
                    json.dumps([item.model_dump(mode="json") for item in report.causal_path]),
                    json.dumps([item.model_dump(mode="json") for item in report.blast_radius]),
                    json.dumps([item.model_dump(mode="json") for item in report.actions]),
                    json.dumps([item.model_dump(mode="json") for item in report.findings]),
                    report.error,
                    report.run_id,
                ),
            )

    async def get_events(self, run_id: str) -> list[Event]:
        """Replay a run's events in ascending sequence order."""

        payloads = await asyncio.to_thread(self._get_event_payloads_sync, run_id)
        return [event_from_json(payload) for payload in payloads]

    def _get_event_payloads_sync(self, run_id: str) -> list[str]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT payload FROM run_events WHERE run_id=? ORDER BY seq", (run_id,)
            ).fetchall()
        return [str(row["payload"]) for row in rows]

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        """Return one run with JSON columns expanded."""

        row = await asyncio.to_thread(self._get_run_sync, run_id)
        return self._expand_run(row) if row is not None else None

    def _get_run_sync(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        return dict(row) if row is not None else None

    async def list_runs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        """Return newest runs first with expanded JSON columns."""

        rows = await asyncio.to_thread(self._list_runs_sync, limit)
        return [self._expand_run(row) for row in rows]

    def _list_runs_sync(self, limit: int) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _expand_run(row: dict[str, Any]) -> dict[str, Any]:
        expanded = dict(row)
        for column in _JSON_RUN_COLUMNS:
            raw = expanded.get(column)
            expanded[column] = json.loads(raw) if raw else []
        return expanded

    async def save_postmortem(
        self,
        *,
        run_id: str,
        postmortem: PostMortem,
        markdown: str,
        document_urn: str | None,
        datahub_links: list[str],
    ) -> None:
        """Upsert a local post-mortem while preserving its reuse counter."""

        await asyncio.to_thread(
            self._save_postmortem_sync,
            run_id,
            postmortem,
            markdown,
            document_urn,
            datahub_links,
        )

    def _save_postmortem_sync(
        self,
        run_id: str,
        postmortem: PostMortem,
        markdown: str,
        document_urn: str | None,
        datahub_links: list[str],
    ) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO postmortems (
                  id, run_id, created_at, title, symptom, symptom_urn,
                  root_cause_urn, root_cause_name, doc_markdown, doc_json,
                  datahub_document_urn, datahub_links, reused_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT(id) DO UPDATE SET
                  title=excluded.title, symptom=excluded.symptom,
                  symptom_urn=excluded.symptom_urn,
                  root_cause_urn=excluded.root_cause_urn,
                  root_cause_name=excluded.root_cause_name,
                  doc_markdown=excluded.doc_markdown, doc_json=excluded.doc_json,
                  datahub_document_urn=excluded.datahub_document_urn,
                  datahub_links=excluded.datahub_links
                """,
                (
                    postmortem.incident_id,
                    run_id,
                    utc_now_iso(),
                    postmortem.title,
                    postmortem.symptom,
                    postmortem.symptom_urn,
                    postmortem.root_cause_urn,
                    postmortem.root_cause_name,
                    markdown,
                    postmortem.model_dump_json(),
                    document_urn,
                    json.dumps(datahub_links),
                ),
            )

    async def increment_reused_count(self, postmortem_ids: list[str]) -> None:
        """Increment every unique recalled post-mortem's reuse counter once."""

        await asyncio.to_thread(
            self._increment_reused_count_sync, list(dict.fromkeys(postmortem_ids))
        )

    def _increment_reused_count_sync(self, postmortem_ids: list[str]) -> None:
        with self._lock, self._connection:
            self._connection.executemany(
                "UPDATE postmortems SET reused_count=reused_count+1 WHERE id=?",
                [(value,) for value in postmortem_ids],
            )

    async def get_postmortem(self, postmortem_id: str) -> dict[str, Any] | None:
        """Return one local memory row with JSON fields expanded."""

        row = await asyncio.to_thread(self._get_postmortem_sync, postmortem_id)
        if row is None:
            return None
        row["doc_json"] = json.loads(row["doc_json"])
        row["datahub_links"] = json.loads(row["datahub_links"] or "[]")
        return row

    def _get_postmortem_sync(self, postmortem_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM postmortems WHERE id=?", (postmortem_id,)
            ).fetchone()
        return dict(row) if row is not None else None

    async def count_runs(self) -> int:
        """Return the number of mirrored runs."""

        return await asyncio.to_thread(self._count_runs_sync)

    def _count_runs_sync(self) -> int:
        with self._lock:
            row = self._connection.execute("SELECT COUNT(*) AS n FROM runs").fetchone()
        return int(row["n"])

    async def compare_runs(
        self, run_a: str | None = None, run_b: str | None = None
    ) -> dict[str, Any] | None:
        """Compare an explicit pair or auto-select a cold/recall pair with one root cause."""

        runs = await self.list_runs(limit=100)
        if run_a and run_b:
            chosen = [
                next((row for row in runs if row["id"] == value), None) for value in (run_a, run_b)
            ]
            if any(row is None for row in chosen):
                return None
            first, second = chosen
        else:
            first = second = None
            for index, left in enumerate(runs):
                for right in runs[index + 1 :]:
                    if (
                        left.get("root_cause_urn")
                        and left.get("root_cause_urn") == right.get("root_cause_urn")
                        and int(left.get("recall_used") or 0) != int(right.get("recall_used") or 0)
                    ):
                        first, second = right, left
                        break
                if first is not None:
                    break
            if first is None or second is None:
                return None
        assert first is not None and second is not None
        deltas: dict[str, Any] = {}
        for metric in ("time_to_root_cause_s", "tool_calls", "hops_walked"):
            old = first.get(metric)
            new = second.get(metric)
            absolute = (new - old) if old is not None and new is not None else None
            pct = (absolute / old * 100) if absolute is not None and old else None
            deltas[metric] = {"absolute": absolute, "pct": pct}
        return {"a": first, "b": second, "deltas": deltas}
