"""Asynchronous demo subprocess jobs with replayable progress fan-out."""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from oncall_agent.api.models import DemoJobEvent

log = logging.getLogger(__name__)

_STEP_PATTERN = re.compile(r"^STEP (?P<step>\d+)/(?P<total>\d+) ")


@dataclass(slots=True)
class DemoJob:
    """In-memory progress history and subscribers for one subprocess."""

    job_id: str
    task: asyncio.Task[None]
    history: list[DemoJobEvent] = field(default_factory=list)
    subscribers: set[asyncio.Queue[DemoJobEvent | None]] = field(default_factory=set)
    done: bool = False

    async def emit(self, event: DemoJobEvent | None) -> None:
        """Store and fan out a progress event or terminal sentinel."""

        if event is not None:
            self.history.append(event)
        for queue in tuple(self.subscribers):
            await queue.put(event)


class DemoJobRegistry:
    """Own long-running seed, break, and reset subprocesses."""

    def __init__(self, backend_dir: Path) -> None:
        self.backend_dir = backend_dir
        self._jobs: dict[str, DemoJob] = {}

    def start(self, command: list[str]) -> str:
        """Start a demo command with no artificial timeout and return its job ID."""

        job_id = f"job_{uuid.uuid4().hex[:16]}"
        task = asyncio.create_task(self._run(job_id, command), name=f"demo-{job_id}")
        self._jobs[job_id] = DemoJob(job_id=job_id, task=task)
        return job_id

    async def _run(self, job_id: str, command: list[str]) -> None:
        job = self._jobs[job_id]
        process: asyncio.subprocess.Process | None = None
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=self.backend_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            assert process.stdout is not None
            while line_bytes := await process.stdout.readline():
                line = line_bytes.decode("utf-8", errors="replace").rstrip()
                match = _STEP_PATTERN.match(line)
                await job.emit(
                    DemoJobEvent(
                        seq=len(job.history) + 1,
                        job_id=job_id,
                        kind="progress",
                        line=line,
                        step=int(match.group("step")) if match else None,
                        total=int(match.group("total")) if match else None,
                    )
                )
            returncode = await process.wait()
            kind = "completed" if returncode == 0 else "error"
            line = "Demo job completed" if returncode == 0 else f"Demo job failed ({returncode})"
            await job.emit(
                DemoJobEvent(
                    seq=len(job.history) + 1,
                    job_id=job_id,
                    kind=kind,
                    line=line,
                    returncode=returncode,
                )
            )
        except asyncio.CancelledError:
            if process is not None and process.returncode is None:
                process.terminate()
                await process.wait()
            raise
        except Exception as exc:
            log.exception("Demo subprocess failed job_id=%s", job_id)
            await job.emit(
                DemoJobEvent(
                    seq=len(job.history) + 1,
                    job_id=job_id,
                    kind="error",
                    line=f"{type(exc).__name__}: {exc}",
                )
            )
        finally:
            job.done = True
            await job.emit(None)

    def subscribe(self, job_id: str) -> asyncio.Queue[DemoJobEvent | None] | None:
        """Return a queue preloaded with all progress emitted before subscription."""

        job = self._jobs.get(job_id)
        if job is None:
            return None
        queue: asyncio.Queue[DemoJobEvent | None] = asyncio.Queue()
        for event in job.history:
            queue.put_nowait(event)
        if job.done:
            queue.put_nowait(None)
        else:
            job.subscribers.add(queue)
        return queue

    def unsubscribe(self, job_id: str, queue: asyncio.Queue[DemoJobEvent | None]) -> None:
        """Detach a progress client without stopping the subprocess."""

        job = self._jobs.get(job_id)
        if job is not None:
            job.subscribers.discard(queue)

    async def close(self) -> None:
        """Terminate and drain active demo subprocesses on application shutdown."""

        tasks = [job.task for job in self._jobs.values() if not job.task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

