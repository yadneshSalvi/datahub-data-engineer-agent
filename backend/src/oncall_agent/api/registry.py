"""Background triage ownership and per-subscriber live event fan-out."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field

from oncall_agent.agent.events import Event
from oncall_agent.agent.models import TriggerSpec
from oncall_agent.agent.runner import Deps, run_triage
from oncall_agent.store import Store

log = logging.getLogger(__name__)

EventSource = Callable[[], AsyncIterator[Event]]


@dataclass(slots=True)
class LiveRun:
    """One owned producer task and its independent subscriber queues."""

    run_id: str
    task: asyncio.Task[None]
    subscribers: set[asyncio.Queue[Event | None]] = field(default_factory=set)

    async def publish(self, event: Event | None) -> None:
        """Fan one event or terminal sentinel to every current subscriber."""

        for queue in tuple(self.subscribers):
            await queue.put(event)


class RunRegistry:
    """Own agent tasks independently of SSE connections and fan out their DTOs."""

    def __init__(self, store: Store) -> None:
        self.store = store
        self._runs: dict[str, LiveRun] = {}
        self._lock = asyncio.Lock()
        self._closing = False

    async def start(self, trigger: TriggerSpec, deps: Deps) -> str:
        """Start ``run_triage`` immediately and return its first event's run identifier."""

        return await self.start_source(lambda: run_triage(trigger, deps))

    async def start_source(self, source_factory: EventSource) -> str:
        """Start an event source, primarily allowing deterministic offline SSE tests."""

        if self._closing:
            raise RuntimeError("Run registry is shutting down")
        loop = asyncio.get_running_loop()
        ready: asyncio.Future[str] = loop.create_future()
        task = asyncio.create_task(
            self._consume(source_factory, ready),
            name="triage-starting",
        )
        try:
            return await ready
        except BaseException:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            raise

    async def _consume(
        self,
        source_factory: EventSource,
        ready: asyncio.Future[str],
    ) -> None:
        entry: LiveRun | None = None
        current = asyncio.current_task()
        assert current is not None
        try:
            async for event in source_factory():
                if entry is None:
                    entry = LiveRun(run_id=event.run_id, task=current)
                    current.set_name(f"triage-{event.run_id}")
                    async with self._lock:
                        self._runs[event.run_id] = entry
                    if not ready.done():
                        ready.set_result(event.run_id)
                await self.store.append_event(event)
                await entry.publish(event)
        except asyncio.CancelledError:
            if not ready.done():
                ready.set_exception(RuntimeError("Run was cancelled before it started"))
            raise
        except Exception as exc:
            if not ready.done():
                ready.set_exception(exc)
            log.exception(
                "Background triage source failed run_id=%s",
                entry.run_id if entry else None,
            )
        finally:
            if entry is not None:
                await entry.publish(None)
                async with self._lock:
                    self._runs.pop(entry.run_id, None)

    async def subscribe(self, run_id: str) -> asyncio.Queue[Event | None] | None:
        """Subscribe to future events before a caller snapshots persisted replay state."""

        queue: asyncio.Queue[Event | None] = asyncio.Queue()
        async with self._lock:
            entry = self._runs.get(run_id)
            if entry is None:
                return None
            entry.subscribers.add(queue)
        return queue

    async def unsubscribe(self, run_id: str, queue: asyncio.Queue[Event | None]) -> None:
        """Remove one disconnected subscriber without changing the agent task."""

        async with self._lock:
            entry = self._runs.get(run_id)
            if entry is not None:
                entry.subscribers.discard(queue)

    async def cancel(self, run_id: str) -> bool:
        """Request cancellation of an active run task."""

        async with self._lock:
            entry = self._runs.get(run_id)
            if entry is None or entry.task.done():
                return False
            entry.task.cancel()
        return True

    async def close(self) -> None:
        """Cancel and drain all agent tasks during application shutdown."""

        self._closing = True
        async with self._lock:
            tasks = [entry.task for entry in self._runs.values() if not entry.task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
