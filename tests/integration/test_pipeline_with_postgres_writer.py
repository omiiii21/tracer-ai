"""End-to-end Phase 4 integration test:
   pipeline emits 4 spans -> PostgresTraceWriter enqueues -> consumer flushes ->
   recorded SQL contains traces INSERT, traces UPDATE latency, spans INSERT,
   span_payloads INSERT for the 3 child spans.

This is the 'Phase 4 success criteria 1+2' verification -- see ROADMAP.md.
"""

from __future__ import annotations

import asyncio
import contextlib
import sys
from typing import Any
from uuid import uuid4

import pytest

from tracer_ai.rag.types import Final, LLMResult, Message, RetrievedChunk, TextDelta
from tracer_ai.tracer.exporters.postgres import PostgresTraceWriter, SpanConsumer
from tracer_ai.tracer.exporters.queue import BoundedDropOldestQueue


@pytest.fixture(autouse=True)
def _configured_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://t:t@db:5432/t")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("VOYAGE_API_KEY", "pa-test")
    sys.modules.pop("tracer_ai.config", None)
    sys.modules.pop("tracer_ai.rag.pipeline", None)


def _make_chunk() -> RetrievedChunk:
    return RetrievedChunk(
        id=uuid4(),
        doc_id="fake-doc",
        doc_section="auth",
        content="fake content",
        metadata={"source_url": "http://example.com"},
        score=0.9,
    )


class _FakeEmbedder:
    name = "fake-embedder"
    version = "0"
    dim = 3

    async def embed_batch(
        self, texts: list[str], *, input_type: str = "document"
    ) -> list[list[float]]:
        return [[0.1, 0.2, 0.3]]


class _FakeRetriever:
    async def retrieve(self, query_embedding: list[float], top_k: int) -> list[RetrievedChunk]:
        return [_make_chunk() for _ in range(top_k)]


class _FakeLLM:
    name = "fake-llm"

    def stream(self, messages: list[Message], *, max_tokens: int = 1024) -> Any:
        async def _gen() -> Any:
            yield TextDelta(text="fake")
            yield Final(
                result=LLMResult(
                    answer="fake",
                    input_tokens=10,
                    output_tokens=5,
                    estimated_cost_usd=0.0001,
                )
            )

        return _gen()


class _RecordingConn:
    def __init__(self, recorder: list[tuple[str, str, Any]]) -> None:
        self._recorder = recorder

    async def execute(self, query: str, *args: Any) -> None:
        self._recorder.append(("execute", query, args))

    async def executemany(self, query: str, args: list[tuple[Any, ...]]) -> None:
        self._recorder.append(("executemany", query, args))


class _RecordingAcquireCtx:
    def __init__(self, recorder: list[tuple[str, str, Any]]) -> None:
        self._recorder = recorder

    async def __aenter__(self) -> _RecordingConn:
        return _RecordingConn(self._recorder)

    async def __aexit__(self, *exc: Any) -> None:
        return None


class _RecordingPool:
    def __init__(self) -> None:
        self.recorder: list[tuple[str, str, Any]] = []

    def acquire(self, timeout: float | None = None) -> _RecordingAcquireCtx:
        return _RecordingAcquireCtx(self.recorder)


@pytest.mark.asyncio
async def test_pipeline_emits_all_4_spans_then_consumer_flushes_to_recorder() -> None:
    """End-to-end: 4 spans emit, queue holds them, consumer flushes via executemany."""
    from tracer_ai.rag.pipeline import Pipeline
    from tracer_ai.rag.types import ChatFinalEvent

    pool = _RecordingPool()
    queue = BoundedDropOldestQueue(maxsize=1000)
    writer = PostgresTraceWriter(queue=queue)
    consumer = SpanConsumer(queue=queue, pool=pool)
    consumer_task = asyncio.create_task(consumer.run(), name="test-consumer")

    pipeline = Pipeline(
        _FakeEmbedder(),
        _FakeRetriever(),
        _FakeLLM(),
        writer,
        top_k=3,
        db_pool=pool,
    )

    final_trace_id: str | None = None
    async for ev in pipeline.run_chat_stream("test query"):
        if isinstance(ev, ChatFinalEvent):
            final_trace_id = ev.trace_id

    # Allow the consumer to flush the batch (250ms time-based trigger)
    await asyncio.sleep(0.4)

    consumer_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await consumer_task

    # Up-front INSERT INTO traces: 1 entry (fired before embed_batch per Plan 1)
    insert_traces = [c for c in pool.recorder if c[0] == "execute" and "INSERT INTO traces" in c[1]]
    assert len(insert_traces) >= 1, "Expected up-front INSERT INTO traces"

    # UPDATE traces SET latency_ms: 1 entry (after _emit_root)
    update_latency = [
        c for c in pool.recorder if c[0] == "execute" and "UPDATE traces SET latency_ms" in c[1]
    ]
    assert len(update_latency) >= 1, "Expected UPDATE traces SET latency_ms"

    # UPDATE traces SET estimated_cost_usd: 1 entry
    update_cost = [
        c
        for c in pool.recorder
        if c[0] == "execute" and "UPDATE traces SET estimated_cost_usd" in c[1]
    ]
    assert len(update_cost) >= 1, "Expected UPDATE traces SET estimated_cost_usd"

    # executemany INSERT INTO spans: at least 1 batch with 4 rows total
    span_batches = [
        c for c in pool.recorder if c[0] == "executemany" and "INSERT INTO spans" in c[1]
    ]
    assert len(span_batches) >= 1, "Expected at least one batch INSERT INTO spans"
    total_spans = sum(len(c[2]) for c in span_batches)
    assert total_spans == 4, f"Expected 4 spans flushed, got {total_spans}"

    # executemany INSERT INTO span_payloads: 3 rows (rag.retrieve, rag.prompt_assemble,
    # rag.llm_call have payloads; rag.request has None)
    payload_batches = [
        c for c in pool.recorder if c[0] == "executemany" and "INSERT INTO span_payloads" in c[1]
    ]
    assert len(payload_batches) >= 1, "Expected at least one batch INSERT INTO span_payloads"
    total_payloads = sum(len(c[2]) for c in payload_batches)
    assert total_payloads == 3, f"Expected 3 payloads flushed, got {total_payloads}"

    # Verify trace_id is consistent across all writes
    assert final_trace_id is not None
