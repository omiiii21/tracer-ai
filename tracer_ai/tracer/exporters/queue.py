"""Custom bounded async queue with drop-oldest semantics (D-4.06/D-4.07/D-4.08).

Replaces asyncio.Queue for the PostgresTraceWriter span buffer. Custom
implementation avoids the put_nowait+except+get_nowait race window that
asyncio.Queue exhibits under concurrent producers — collections.deque with
asyncio.Lock gives deterministic ordering guarantees.

Per D-4.05: drop-oldest under saturation. Newer telemetry is more
representative of current system state; the request path must NEVER block on
trace emit.

Per D-4.08: rate-limited saturation log — at most once per 1s window while
saturated; per-event logging would swamp structured-log streams during burst.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any

import structlog

log = structlog.get_logger()


class BoundedDropOldestQueue:
    """Bounded queue that drops the OLDEST item when full (D-4.05/D-4.06/D-4.07).

    API surface (locked in D-4.06):
        __init__(maxsize: int) -> None
        async put(item: Any) -> bool   # True if queued, False if drop-to-make-room
        async get() -> Any              # awaits item availability
        qsize() -> int
    """

    def __init__(self, maxsize: int) -> None:
        self._maxsize = maxsize
        self._deque: deque[Any] = deque()
        self._lock = asyncio.Lock()
        self._not_empty = asyncio.Event()
        self._dropped_count: int = 0
        self._last_log_at: float = 0.0

    async def put(self, item: Any) -> bool:
        """Enqueue item. Returns True if queued, False if an old item was dropped."""
        dropped = False
        async with self._lock:
            if len(self._deque) >= self._maxsize:
                self._deque.popleft()  # drop oldest
                self._dropped_count += 1
                dropped = True
                # Rate-limited saturation log: at most once per 1s window (D-4.08).
                now = time.monotonic()
                if now - self._last_log_at >= 1.0:
                    log.warning(
                        "tracer.queue_saturated",
                        dropped=self._dropped_count,
                        window="1s",
                        queue_depth=len(self._deque),
                    )
                    self._dropped_count = 0
                    self._last_log_at = now
            self._deque.append(item)
            self._not_empty.set()
        return not dropped

    async def get(self) -> Any:
        """Await next item. Loops on spurious wake."""
        while True:
            await self._not_empty.wait()
            async with self._lock:
                if self._deque:
                    item = self._deque.popleft()
                    if not self._deque:
                        self._not_empty.clear()
                    return item
                # Spurious wake — loop and re-await.

    def qsize(self) -> int:
        """Read-only snapshot of current queue depth (not under lock)."""
        return len(self._deque)
