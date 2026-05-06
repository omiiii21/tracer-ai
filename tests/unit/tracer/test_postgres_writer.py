"""Unit tests for PostgresTraceWriter + SpanConsumer (Phase 4 TRCR-06)."""

from __future__ import annotations

import asyncio
import contextlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from tracer_ai.tracer.exporters.postgres import (
    _BATCH_SIZE,
    PostgresTraceWriter,
    SpanConsumer,
)
from tracer_ai.tracer.exporters.queue import BoundedDropOldestQueue
from tracer_ai.tracer.writer import Span


def _make_span(
    *,
    name: str = "rag.retrieve",
    payload: dict[str, Any] | None = None,
    parent_span_id: Any = None,
    trace_id: Any = None,
) -> Span:
    return Span(
        trace_id=trace_id or uuid4(),
        span_id=uuid4(),
        parent_span_id=parent_span_id,
        name=name,
        started_at=datetime.now(UTC),
        ended_at=datetime.now(UTC),
        attrs={"gen_ai.operation.name": "retrieval"},
        payload=payload,
    )


class _FakeConn:
    def __init__(self, recorder: list[tuple[str, str, Any]]) -> None:
        self._recorder = recorder

    async def executemany(self, query: str, args: list[tuple[Any, ...]]) -> None:
        self._recorder.append(("executemany", query, args))

    async def execute(self, query: str, *args: Any) -> None:
        self._recorder.append(("execute", query, args))


class _FakeAcquireCtx:
    def __init__(self, recorder: list[tuple[str, str, Any]]) -> None:
        self._recorder = recorder

    async def __aenter__(self) -> _FakeConn:
        return _FakeConn(self._recorder)

    async def __aexit__(self, *exc: Any) -> None:
        return None


class _FakePool:
    def __init__(self) -> None:
        self.recorder: list[tuple[str, str, Any]] = []

    def acquire(self, timeout: float | None = None) -> _FakeAcquireCtx:
        return _FakeAcquireCtx(self.recorder)


@pytest.mark.asyncio
async def test_emit_enqueues_span_and_returns_none() -> None:
    queue = BoundedDropOldestQueue(maxsize=10)
    writer = PostgresTraceWriter(queue=queue)
    span = _make_span()
    # emit() returns None per the TraceWriter Protocol
    await writer.emit(span)
    assert queue.qsize() == 1


@pytest.mark.asyncio
async def test_emit_swallows_queue_exception() -> None:
    """T-04-03-04: emit() must NEVER raise back into pipeline."""

    class _BadQueue:
        async def put(self, item: Any) -> bool:
            raise RuntimeError("simulated queue failure")

        def qsize(self) -> int:
            return 0

    writer = PostgresTraceWriter(queue=_BadQueue())  # type: ignore[arg-type]
    span = _make_span()
    # Must not raise
    await writer.emit(span)


@pytest.mark.asyncio
async def test_consumer_flushes_spans_before_payloads() -> None:
    """D-4.13: spans INSERT must precede span_payloads INSERT."""
    pool = _FakePool()
    queue = BoundedDropOldestQueue(maxsize=10)
    consumer = SpanConsumer(queue=queue, pool=pool)
    span = _make_span(payload={"retrieved_chunks": [{"score": 0.9}]})
    await consumer._flush([span])
    method_queries = [(method, query) for method, query, _ in pool.recorder]
    # Find the index of the spans INSERT and the span_payloads INSERT
    spans_idx = next(i for i, (_m, q) in enumerate(method_queries) if "INSERT INTO spans" in q)
    payloads_idx = next(
        i for i, (_m, q) in enumerate(method_queries) if "INSERT INTO span_payloads" in q
    )
    assert spans_idx < payloads_idx


@pytest.mark.asyncio
async def test_consumer_skips_payload_insert_when_no_payload_spans() -> None:
    pool = _FakePool()
    queue = BoundedDropOldestQueue(maxsize=10)
    consumer = SpanConsumer(queue=queue, pool=pool)
    # All spans payload=None
    spans = [_make_span(payload=None) for _ in range(3)]
    await consumer._flush(spans)
    method_queries = [(method, query) for method, query, _ in pool.recorder]
    # spans INSERT is present
    assert any("INSERT INTO spans" in q for _, q in method_queries)
    # span_payloads INSERT is NOT present
    assert not any("INSERT INTO span_payloads" in q for _, q in method_queries)


@pytest.mark.asyncio
async def test_flush_serializes_attrs_and_payload_via_json_dumps() -> None:
    """Pitfall 3: jsonb columns require json.dumps() string."""
    pool = _FakePool()
    queue = BoundedDropOldestQueue(maxsize=10)
    consumer = SpanConsumer(queue=queue, pool=pool)
    span = _make_span(payload={"key": "value"})
    await consumer._flush([span])
    spans_call = next(
        call
        for call in pool.recorder
        if call[0] == "executemany" and "INSERT INTO spans" in call[1]
    )
    args = spans_call[2]
    assert isinstance(args, list) and len(args) == 1
    row = args[0]
    # The 7th column (attrs) must be a JSON-serialized string
    assert isinstance(row[6], str)
    json.loads(row[6])  # parses as JSON without raising
    payloads_call = next(
        call
        for call in pool.recorder
        if call[0] == "executemany" and "INSERT INTO span_payloads" in call[1]
    )
    p_row = payloads_call[2][0]
    assert isinstance(p_row[1], str)
    assert json.loads(p_row[1]) == {"key": "value"}


@pytest.mark.asyncio
async def test_consumer_flush_failure_is_logged_not_raised() -> None:
    """CLAUDE.md: tracer failures must NOT fail user requests."""

    class _RaisingPool:
        def acquire(self, timeout: float | None = None) -> Any:
            class _Ctx:
                async def __aenter__(self) -> Any:
                    raise RuntimeError("simulated db failure")

                async def __aexit__(self, *exc: Any) -> None:
                    return None

            return _Ctx()

    queue = BoundedDropOldestQueue(maxsize=10)
    consumer = SpanConsumer(queue=queue, pool=_RaisingPool())
    consumer_task = asyncio.create_task(consumer.run())
    await queue.put(_make_span())
    # Wait long enough for the time-based flush trigger
    await asyncio.sleep(0.5)
    consumer_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await consumer_task
    # The fact we reach here without RuntimeError propagating is the test:
    # the consumer caught and logged the simulated db failure.


@pytest.mark.asyncio
async def test_consumer_drain_flushes_remaining_items() -> None:
    pool = _FakePool()
    queue = BoundedDropOldestQueue(maxsize=10)
    consumer = SpanConsumer(queue=queue, pool=pool)
    for _ in range(5):
        await queue.put(_make_span())
    await consumer.drain()
    spans_inserts = [
        call
        for call in pool.recorder
        if call[0] == "executemany" and "INSERT INTO spans" in call[1]
    ]
    assert len(spans_inserts) == 1
    inserted_rows = spans_inserts[0][2]
    assert len(inserted_rows) == 5


@pytest.mark.asyncio
async def test_consumer_run_flushes_at_batch_size_threshold() -> None:
    """D-4.09: flush at len(batch) >= 50 OR 250ms elapsed."""
    pool = _FakePool()
    queue = BoundedDropOldestQueue(maxsize=200)
    consumer = SpanConsumer(queue=queue, pool=pool)
    consumer_task = asyncio.create_task(consumer.run())
    # Push exactly _BATCH_SIZE items quickly
    for _ in range(_BATCH_SIZE):
        await queue.put(_make_span())
    # Allow consumer to drain; the size threshold should fire within ~250ms
    await asyncio.sleep(0.4)
    consumer_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await consumer_task
    spans_inserts = [
        call
        for call in pool.recorder
        if call[0] == "executemany" and "INSERT INTO spans" in call[1]
    ]
    assert len(spans_inserts) >= 1
    total_rows = sum(len(call[2]) for call in spans_inserts)
    assert total_rows == _BATCH_SIZE
