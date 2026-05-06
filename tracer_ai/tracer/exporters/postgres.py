"""PostgresTraceWriter + SpanConsumer (Phase 4 D-4.06 / D-4.09 / D-4.10 / TRCR-06 / TRCR-07).

Fills the Phase 2 stub. The writer is a thin wrapper around BoundedDropOldestQueue;
the consumer is a background asyncio.Task started by lifespan.py that batch-flushes
to Postgres via executemany.

Per D-4.14: TraceWriter.emit(span) is the single Protocol method. Splitting payload
across two INSERTs is internal to this writer.

Per D-4.09: batch flushes when (len >= 50) OR (250ms since first item).

Per D-4.10: lifespan calls drain() with 5s timeout before closing the pool.

Per CLAUDE.md: failures in trace pipeline must NEVER fail user requests -- every
flush exception is caught and structlog'd; emit() never raises.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import TYPE_CHECKING

import asyncpg
import structlog

from tracer_ai.tracer.writer import Span

if TYPE_CHECKING:
    from tracer_ai.tracer.exporters.queue import BoundedDropOldestQueue

log = structlog.get_logger()

_BATCH_SIZE = 50
_FLUSH_INTERVAL = 0.250  # seconds (D-4.09)


class PostgresTraceWriter:
    """TraceWriter Protocol impl -- enqueues spans for the SpanConsumer to flush."""

    def __init__(self, queue: BoundedDropOldestQueue) -> None:
        self._queue = queue

    async def emit(self, span: Span) -> None:
        """Enqueue a span. Fire-and-forget -- saturation handled by queue itself.

        T-04-03-04: emit() must NEVER raise back into pipeline. If the queue
        itself raises (should be extremely rare), log and swallow.
        """
        try:
            await self._queue.put(span)
        except Exception as exc:
            log.warning("tracer.emit_swallowed", error=str(exc), span_name=span.name)


class SpanConsumer:
    """Background asyncio.Task that drains BoundedDropOldestQueue in batches.

    Started by lifespan via asyncio.create_task(consumer.run(), name="tracer-consumer").
    Stopped via lifespan finally block calling drain() then cancelling the task.
    """

    def __init__(
        self,
        queue: BoundedDropOldestQueue,
        pool: asyncpg.Pool,
    ) -> None:
        self._queue = queue
        self._pool = pool
        self.stop_accepting: bool = False  # reserved for shutdown signaling (D-4.10)

    async def run(self) -> None:
        """Main consumer loop -- runs forever until task is cancelled."""
        batch: list[Span] = []
        batch_started_at: float = time.monotonic()
        while True:
            elapsed = time.monotonic() - batch_started_at
            remaining = max(0.0, _FLUSH_INTERVAL - elapsed)
            try:
                span = await asyncio.wait_for(self._queue.get(), timeout=remaining)
                batch.append(span)
            except TimeoutError:
                pass  # time-based flush trigger
            except asyncio.CancelledError:
                # Task is being cancelled; flush whatever is in batch then re-raise.
                if batch:
                    try:
                        await self._flush(batch)
                    except Exception as exc:
                        log.exception(
                            "tracer.consumer_flush_on_cancel_failed",
                            error=str(exc),
                        )
                raise
            should_flush = len(batch) >= _BATCH_SIZE or (
                bool(batch) and time.monotonic() - batch_started_at >= _FLUSH_INTERVAL
            )
            if should_flush and batch:
                try:
                    await self._flush(batch)
                except Exception as exc:
                    # CLAUDE.md: tracer failures must not fail user requests.
                    log.exception(
                        "tracer.consumer_flush_failed",
                        batch_size=len(batch),
                        error=str(exc),
                    )
                batch = []
                batch_started_at = time.monotonic()

    async def drain(self) -> None:
        """Flush remaining items. Called by lifespan during shutdown (D-4.10)."""
        batch: list[Span] = []
        # Drain queue with short per-item timeout
        while self._queue.qsize() > 0:
            try:
                span = await asyncio.wait_for(self._queue.get(), timeout=0.1)
                batch.append(span)
            except TimeoutError:
                break
            if len(batch) >= _BATCH_SIZE:
                try:
                    await self._flush(batch)
                except Exception as exc:
                    log.exception("tracer.drain_flush_failed", error=str(exc))
                batch = []
        if batch:
            try:
                await self._flush(batch)
            except Exception as exc:
                log.exception("tracer.drain_flush_failed", error=str(exc))

    async def _flush(self, spans: list[Span]) -> None:
        """Persist a batch: INSERT spans first, then INSERT span_payloads.

        D-4.13: spans MUST INSERT before span_payloads (logical ordering;
        no FK at DDL level on partitioned table).

        Pitfall 3: jsonb columns require explicit json.dumps -- asyncpg does
        not auto-encode dict values to jsonb without codec registration.
        """
        span_rows = [
            (
                str(s.span_id),
                str(s.trace_id),
                str(s.parent_span_id) if s.parent_span_id else None,
                s.name,
                s.started_at,
                s.ended_at,
                json.dumps(s.attrs),  # explicit jsonb serialization (Pitfall 3)
            )
            for s in spans
        ]
        payload_rows = [
            (str(s.span_id), json.dumps(s.payload)) for s in spans if s.payload is not None
        ]
        async with self._pool.acquire() as conn:
            # D-4.13: spans MUST INSERT before span_payloads (logical ordering;
            # no FK at DDL level on partitioned table).
            await conn.executemany(
                "INSERT INTO spans (id, trace_id, parent_span_id, name, "
                "started_at, ended_at, attrs) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb) "
                "ON CONFLICT (id, started_at) DO NOTHING",
                span_rows,
            )
            if payload_rows:
                await conn.executemany(
                    "INSERT INTO span_payloads (span_id, payload) "
                    "VALUES ($1, $2::jsonb) "
                    "ON CONFLICT (span_id) DO NOTHING",
                    payload_rows,
                )
        log.debug(
            "tracer.consumer_flushed",
            spans=len(span_rows),
            payloads=len(payload_rows),
        )
