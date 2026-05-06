"""Phase 4 lifespan shutdown drain -- `tracer.shutdown_drain_incomplete remaining=N`."""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest

from tracer_ai.tracer.exporters.postgres import SpanConsumer
from tracer_ai.tracer.exporters.queue import BoundedDropOldestQueue
from tracer_ai.tracer.writer import Span


@pytest.fixture(autouse=True)
def _configured_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://t:t@db:5432/t")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("VOYAGE_API_KEY", "pa-test")
    sys.modules.pop("tracer_ai.config", None)


def _make_span() -> Span:
    return Span(
        trace_id=uuid4(),
        span_id=uuid4(),
        parent_span_id=None,
        name="rag.request",
        started_at=datetime.now(UTC),
        ended_at=datetime.now(UTC),
        attrs={"gen_ai.operation.name": "chat"},
        payload=None,
    )


class _SlowConn:
    """Conn whose flush methods stall longer than the 5s drain budget.

    fetchrow() returns None instantly so the lifespan CORP-04 startup probe
    treats the corpus as empty (warn log, not failure). executemany() and
    execute() stall 6s each so the drain's per-batch flush exceeds the 5s
    asyncio.wait_for timeout in lifespan.py.
    """

    async def fetchrow(self, query: str, *args: Any) -> None:
        # CORP-04 probe path -- empty corpus is acceptable; lifespan logs warning.
        return None

    async def fetch(self, query: str, *args: Any) -> list[Any]:
        return []

    async def execute(self, query: str, *args: Any) -> None:
        await asyncio.sleep(6.0)

    async def executemany(self, query: str, args: list[tuple[Any, ...]]) -> None:
        await asyncio.sleep(6.0)


class _SlowAcquireCtx:
    async def __aenter__(self) -> _SlowConn:
        return _SlowConn()

    async def __aexit__(self, *exc: Any) -> None:
        return None


class _SlowPool:
    """Pool whose flush calls stall 6s -- drain will time out under 5s budget."""

    def acquire(self, timeout: float | None = None) -> _SlowAcquireCtx:
        return _SlowAcquireCtx()

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_drain_logs_warning_when_timeout_exceeded() -> None:
    """If drain() takes longer than 5s, the lifespan logs `tracer.shutdown_drain_incomplete`.

    This test exercises the REAL `tracer_ai/api/lifespan.py` finally block by entering
    its async context manager directly. We do NOT manually call log.warning() -- that
    would be a false positive (the warn-log path inside lifespan.py would never run).

    Approach (option (b) from the checker -- minimal-friction):
      1. Patch `tracer_ai.api.lifespan.log` with a mock so we can capture calls.
      2. Build a minimal FastAPI app and seed `app.state` with the queue + a slow pool
         so the lifespan finds them on shutdown (matches what main.py wires).
      3. Enter the lifespan context (`async with lifespan(app):`) -- this invokes the
         real startup; on context exit the real finally block runs, hits the drain
         timeout against the slow pool, and (if implemented per D-4.10) emits the
         `tracer.shutdown_drain_incomplete` warn-log.
      4. Assert the patched logger was called with `event_name="tracer.shutdown_drain_incomplete"`
         and a non-zero `remaining=` kwarg.
    """
    from fastapi import FastAPI

    from tracer_ai.api.lifespan import lifespan

    app = FastAPI()
    queue = BoundedDropOldestQueue(maxsize=200)
    pool = _SlowPool()
    # Pre-fill the queue beyond what the slow pool can drain inside the timeout.
    # Drain pulls items into a batch of size 50 then flushes. With executemany
    # stalling 6s on the FIRST flush, the 5s wait_for timeout fires while the
    # remaining items are still in the queue (qsize >= 1).
    for _ in range(150):
        await queue.put(_make_span())

    # Wire app.state so the lifespan finds the queue+pool (mirrors main.py wiring).
    # The lifespan implementation in Plan 3 is responsible for reading these and
    # constructing the SpanConsumer; tests use the same surface contract.
    app.state.trace_queue = queue
    app.state.db_pool = pool
    # Also support attribute name variants the lifespan might use:
    app.state.span_queue = queue

    with patch("tracer_ai.api.lifespan.log") as mock_log:
        # Patch the construction path so the real lifespan picks up our pre-loaded
        # queue + slow pool instead of constructing fresh ones during startup.
        # Lifespan in Plan 03 builds these inside the try/Pipeline-construction
        # block; we override the names it stores on app.state via a side effect
        # on asyncpg.create_pool to return our slow pool.
        with patch("tracer_ai.api.lifespan.asyncpg.create_pool") as mock_create_pool:

            async def _fake_create_pool(**kwargs: Any) -> _SlowPool:
                return pool

            mock_create_pool.side_effect = _fake_create_pool
            # Patch SpanConsumer/PostgresTraceWriter/BoundedDropOldestQueue so the
            # lifespan's local `consumer` variable references our pre-loaded queue.
            with (
                patch(
                    "tracer_ai.api.lifespan.BoundedDropOldestQueue",
                    return_value=queue,
                ),
                patch(
                    "tracer_ai.api.lifespan.SpanConsumer",
                    return_value=SpanConsumer(queue=queue, pool=pool),
                ),
            ):
                # The lifespan's pipeline construction may fail (no real adapters);
                # that path falls back to NoopTraceWriter. The finally block still
                # runs and exercises the drain.
                async with lifespan(app):
                    pass  # lifespan body is a no-op; we only need the finally to execute on exit.

        # The finally block must have invoked log.warning with the drain-incomplete event.
        # Two acceptable shapes (depending on Plan 3's implementation):
        #   log.warning("tracer.shutdown_drain_incomplete", remaining=N)
        #   log.warning("tracer.shutdown_drain_incomplete", remaining=N, ...)
        warning_calls = [
            c
            for c in mock_log.warning.call_args_list
            if c.args and c.args[0] == "tracer.shutdown_drain_incomplete"
        ]
        assert len(warning_calls) >= 1, (
            f"Expected lifespan finally to log 'tracer.shutdown_drain_incomplete'; "
            f"got warning calls: {mock_log.warning.call_args_list}"
        )
        # Verify the kwarg `remaining` is present and positive (queue still had items)
        kwargs = warning_calls[0].kwargs
        assert "remaining" in kwargs, f"warn-log missing remaining= kwarg: {warning_calls[0]}"
        assert kwargs["remaining"] >= 1, f"remaining should be >= 1 since drain timed out: {kwargs}"


@pytest.mark.asyncio
async def test_drain_completes_when_pool_is_responsive() -> None:
    """Happy path: drain finishes inside the 5s budget when the pool is fast."""

    class _FastConn:
        async def executemany(self, query: str, args: list[tuple[Any, ...]]) -> None:
            return None

        async def execute(self, query: str, *args: Any) -> None:
            return None

    class _FastAcquireCtx:
        async def __aenter__(self) -> _FastConn:
            return _FastConn()

        async def __aexit__(self, *exc: Any) -> None:
            return None

    class _FastPool:
        def acquire(self, timeout: float | None = None) -> _FastAcquireCtx:
            return _FastAcquireCtx()

    queue = BoundedDropOldestQueue(maxsize=10)
    pool = _FastPool()
    consumer = SpanConsumer(queue=queue, pool=pool)
    for _ in range(5):
        await queue.put(_make_span())
    await asyncio.wait_for(consumer.drain(), timeout=5.0)
    assert queue.qsize() == 0, "drain should have flushed all items"
