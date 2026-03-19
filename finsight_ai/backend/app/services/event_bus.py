"""
EventBus — async per-session event queue for SSE streaming.

Architecture
============
Each ingestion job or chat session gets its own ``EventBus`` instance.
Producers (supervisor nodes, services) call ``bus.emit(event)`` to push
an ``SSEEvent`` into the bus.  The SSE generator in the route handler
calls ``bus.drain()`` to consume events as they arrive.

The ``EventBusRegistry`` is a module-level singleton that maps
session/document IDs to their buses.  Routes register before starting
background work; background workers look up the bus by ID and emit.
If no bus is registered (e.g. the client disconnected before the
background task ran), ``emit()`` silently discards — no crashes.

Lifecycle
---------
1. Route registers a bus:   ``bus = registry.create(session_id)``
2. Background task starts   (ingestion graph / chat)
3. Background emits events: ``await registry.emit(session_id, event)``
4. SSE generator drains:    ``async for event in bus.drain(): yield event.to_sse()``
5. When done, emit sentinel:``await registry.close(session_id)``
6. Registry removes the bus after ``close()``

Thread Safety
-------------
``asyncio.Queue`` is used as the underlying buffer.  All callers must
run in the same asyncio event loop (guaranteed for FastAPI workers).
The registry uses a plain dict — safe for single-loop use.

Bus Capacity
------------
Default max size is 512 events.  If a producer overflows the queue
(e.g. document with thousands of chunks), older events are dropped
with a warning logged.  Chat sessions typically emit < 20 events.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

import structlog

from app.api.schemas.sse_schemas import SSEEvent, StreamDoneEvent

logger = structlog.get_logger(__name__)

_QUEUE_MAX_SIZE = 512
_SENTINEL = object()  # Signals drain() to stop iterating


class EventBus:
    """
    Single-session async event queue.

    Producers call ``await bus.emit(event)`` from any coroutine.
    The SSE route handler calls ``async for event in bus.drain()``.
    """

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_MAX_SIZE)
        self._closed = False

    async def emit(self, event: SSEEvent) -> None:
        """
        Push an event into the bus.

        Silently drops the event if the bus is already closed or the
        queue is full (avoids blocking the ingestion pipeline).
        """
        if self._closed:
            return
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning(
                "event_bus.queue_full",
                session_id=self.session_id,
                event_type=event.event_type,
            )

    async def close(self, done_event: StreamDoneEvent | None = None) -> None:
        """
        Signal to the drainer that the stream is complete.

        Optionally emits a ``StreamDoneEvent`` before the sentinel so
        the frontend receives a typed terminal event.
        """
        if self._closed:
            return
        self._closed = True
        if done_event:
            try:
                self._queue.put_nowait(done_event)
            except asyncio.QueueFull:
                pass
        try:
            self._queue.put_nowait(_SENTINEL)
        except asyncio.QueueFull:
            # Force sentinel in — drop oldest item if needed
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            self._queue.put_nowait(_SENTINEL)

    async def drain(self) -> AsyncIterator[SSEEvent | StreamDoneEvent]:
        """
        Async generator that yields events until the sentinel is received.

        Usage::

            async for event in bus.drain():
                yield event.to_sse()
        """
        while True:
            item = await self._queue.get()
            if item is _SENTINEL:
                break
            yield item  # type: ignore[misc]

    @property
    def is_closed(self) -> bool:
        return self._closed


class EventBusRegistry:
    """
    Module-level singleton mapping session IDs to their ``EventBus`` instances.

    Ingestion service registers a bus before launching the background task.
    Supervisor nodes look up the bus by document_id to emit stage events.
    """

    def __init__(self) -> None:
        self._buses: dict[str, EventBus] = {}

    def create(self, session_id: str) -> EventBus:
        """
        Create and register a new bus for ``session_id``.

        If a bus already exists for that ID it is returned as-is
        (idempotent — safe for retry scenarios).
        """
        if session_id not in self._buses:
            self._buses[session_id] = EventBus(session_id)
            logger.debug("event_bus.registered", session_id=session_id)
        return self._buses[session_id]

    def get(self, session_id: str) -> EventBus | None:
        """Return the bus for ``session_id``, or None if not registered."""
        return self._buses.get(session_id)

    async def emit(self, session_id: str, event: SSEEvent) -> None:
        """
        Emit an event to a registered bus.

        Silently no-ops if the bus does not exist (client disconnected,
        feature flag off, etc.).
        """
        bus = self._buses.get(session_id)
        if bus:
            await bus.emit(event)

    async def close(
        self,
        session_id: str,
        done_event: StreamDoneEvent | None = None,
    ) -> None:
        """
        Close the bus and remove it from the registry.

        Should be called by the producer when the pipeline finishes
        (success or failure).
        """
        bus = self._buses.pop(session_id, None)
        if bus:
            await bus.close(done_event)
            logger.debug("event_bus.closed", session_id=session_id)

    def has(self, session_id: str) -> bool:
        return session_id in self._buses


# Module-level singleton — import this everywhere
bus_registry = EventBusRegistry()


# ── Factory helpers ────────────────────────────────────────────────────────────

def make_ingestion_event(
    *,
    session_id: str,
    event_type: str,
    stage: str,
    message: str,
    status: str = "complete",
    agent_name: str = "ingestion_pipeline",
    progress: float | None = None,
    document_id: str | None = None,
    duration_ms: int | None = None,
    warnings: list[str] | None = None,
    payload: dict | None = None,
) -> SSEEvent:
    """
    Convenience factory for ingestion pipeline SSE events.

    Keeps call sites terse while ensuring all required fields are set.
    """
    return SSEEvent(
        session_id=session_id,
        event_type=event_type,
        stage=stage,
        message=message,
        status=status,
        agent_name=agent_name,
        progress=progress,
        document_id=document_id,
        duration_ms=duration_ms,
        warnings=warnings or [],
        payload=payload or {},
    )


def make_chat_event(
    *,
    session_id: str,
    event_type: str,
    stage: str,
    message: str,
    status: str = "complete",
    agent_name: str = "chat_pipeline",
    progress: float | None = None,
    duration_ms: int | None = None,
    warnings: list[str] | None = None,
    payload: dict | None = None,
) -> SSEEvent:
    """
    Convenience factory for chat / RAG pipeline SSE events.
    """
    return SSEEvent(
        session_id=session_id,
        event_type=event_type,
        stage=stage,
        message=message,
        status=status,
        agent_name=agent_name,
        progress=progress,
        duration_ms=duration_ms,
        warnings=warnings or [],
        payload=payload or {},
    )
