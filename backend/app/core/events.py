"""In-process pub/sub that bridges worker threads and WebSocket clients."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from typing import Any

log = logging.getLogger(__name__)

Event = dict[str, Any]


class EventBus:
    """Thread-safe publisher; subscribers are asyncio queues on the server loop."""

    def __init__(self, queue_size: int = 256) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._subscribers: set[asyncio.Queue[Event]] = set()
        self._queue_size = queue_size

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def publish(self, event_type: str, **payload: Any) -> None:
        """Publish from any thread. Events are dropped when no loop is bound (tests, CLI)."""
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        event: Event = {"type": event_type, **payload}
        with contextlib.suppress(RuntimeError):  # loop shutting down
            loop.call_soon_threadsafe(self._dispatch, event)

    def _dispatch(self, event: Event) -> None:
        for queue in list(self._subscribers):
            if queue.full():
                # Slow client: drop the oldest event rather than blocking everyone.
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            queue.put_nowait(event)

    @contextlib.asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[Event]]:
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=self._queue_size)
        self._subscribers.add(queue)
        try:
            yield queue
        finally:
            self._subscribers.discard(queue)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)
