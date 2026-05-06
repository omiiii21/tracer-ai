"""Phase 4 TRCR-08 perf gate -- async trace write adds <=100ms p95.

Approach: run the same Pipeline twice in series (NoopTraceWriter vs
PostgresTraceWriter) over N=200 iterations and compare p95 wall-clock latency.
The fake pool's execute()/executemany() complete instantly so we measure the
queue + consumer overhead, NOT the Postgres network cost (which RESEARCH
quantifies at < 5ms per indexed write on local Postgres).
"""

from __future__ import annotations

import asyncio
import contextlib
import statistics
import sys
import time
from typing import Any
from uuid import uuid4

import pytest

from tracer_ai.tracer.exporters.postgres import PostgresTraceWriter, SpanConsumer
from tracer_ai.tracer.exporters.queue import BoundedDropOldestQueue
from tracer_ai.tracer.writer import NoopTraceWriter

_ITERATIONS = 200
_P95_BUDGET_MS = 100.0
_WARMUP_ITERATIONS = 10


@pytest.fixture(autouse=True)
def _configured_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://t:t@db:5432/t")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("VOYAGE_API_KEY", "pa-test")
    sys.modules.pop("tracer_ai.config", None)
    sys.modules.pop("tracer_ai.rag.pipeline", None)


class _FakeEmbedder:
    name = "fake-embedder"

    async def embed_batch(self, texts: list[str], *, input_type: str) -> list[list[float]]:
        await asyncio.sleep(0.001)  # simulate ~1ms embedding
        return [[0.1, 0.2, 0.3]]


class _FakeChunk:
    def __init__(self) -> None:
        self.id = uuid4()
        self.content = "fake chunk content"
        self.score = 0.85
        self.doc_id = "fake-doc"
        self.doc_section = "auth"
        self.metadata: dict[str, Any] = {"source_url": "http://example.com"}


class _FakeRetriever:
    async def retrieve(self, embedding: list[float], top_k: int) -> list[Any]:
        await asyncio.sleep(0.001)
        return [_FakeChunk() for _ in range(top_k)]


class _FakeLLMResult:
    def __init__(self) -> None:
        self.answer = "fake answer"
        self.input_tokens = 100
        self.output_tokens = 50
        self.estimated_cost_usd = 0.001


class _FakeFinal:
    def __init__(self) -> None:
        self.result = _FakeLLMResult()


class _FakeTextDelta:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeLLM:
    name = "fake-llm"

    def stream(self, messages: list[dict[str, str]]) -> Any:
        async def _gen() -> Any:
            await asyncio.sleep(0.001)
            yield _FakeTextDelta("fake ")
            yield _FakeTextDelta("answer")
            yield _FakeFinal()

        return _gen()


class _NoopConn:
    async def execute(self, query: str, *args: Any) -> None:
        return None

    async def executemany(self, query: str, args: list[tuple[Any, ...]]) -> None:
        return None


class _NoopAcquireCtx:
    async def __aenter__(self) -> _NoopConn:
        return _NoopConn()

    async def __aexit__(self, *exc: Any) -> None:
        return None


class _NoopPool:
    def acquire(self, timeout: float | None = None) -> _NoopAcquireCtx:
        return _NoopAcquireCtx()


def _import_pipeline() -> Any:
    from tracer_ai.rag.pipeline import Pipeline

    return Pipeline


async def _run_pipeline_once(pipeline: Any) -> None:
    """Drain the chat stream for one query."""
    from tracer_ai.rag.types import ChatFinalEvent

    async for ev in pipeline.run_chat_stream("benchmark query"):
        if isinstance(ev, ChatFinalEvent):
            return


async def _measure(pipeline: Any, iterations: int) -> list[float]:
    """Run warmup then take N timed samples.

    Warmup eliminates cold-start effects on the event loop + Python JIT/import
    paths (first ~10-30 iterations of fresh asyncio code are typically slower
    than steady-state). Without warmup the first iterations bias p95 upward
    and produce flaky perf gates.
    """
    # Warmup -- discard timings; only the steady-state matters for p95.
    for _ in range(_WARMUP_ITERATIONS):
        await _run_pipeline_once(pipeline)
    # Measure
    samples: list[float] = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        await _run_pipeline_once(pipeline)
        samples.append((time.perf_counter() - t0) * 1000.0)  # ms
    return samples


@pytest.mark.asyncio
async def test_trace_write_p95_under_100ms_overhead() -> None:
    """TRCR-08: PostgresTraceWriter adds <=100ms p95 vs NoopTraceWriter baseline."""
    Pipeline = _import_pipeline()

    # Baseline: NoopTraceWriter, no db_pool
    baseline_pipeline = Pipeline(
        _FakeEmbedder(),
        _FakeRetriever(),
        _FakeLLM(),
        NoopTraceWriter(),
        top_k=3,
        db_pool=None,
    )
    baseline_samples = await _measure(baseline_pipeline, _ITERATIONS)

    # Phase 4: PostgresTraceWriter + consumer task + db_pool
    queue = BoundedDropOldestQueue(maxsize=1000)
    pool = _NoopPool()
    consumer = SpanConsumer(queue=queue, pool=pool)
    consumer_task = asyncio.create_task(consumer.run(), name="bench-consumer")
    phase4_pipeline = Pipeline(
        _FakeEmbedder(),
        _FakeRetriever(),
        _FakeLLM(),
        PostgresTraceWriter(queue=queue),
        top_k=3,
        db_pool=pool,
    )
    try:
        phase4_samples = await _measure(phase4_pipeline, _ITERATIONS)
    finally:
        consumer_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await consumer_task

    baseline_samples.sort()
    phase4_samples.sort()
    p95_baseline = statistics.quantiles(baseline_samples, n=20)[18]  # 95th percentile
    p95_phase4 = statistics.quantiles(phase4_samples, n=20)[18]
    delta = p95_phase4 - p95_baseline

    print(
        f"\n[TRCR-08 perf gate]\n"
        f"  baseline p95 = {p95_baseline:.2f}ms\n"
        f"  phase4   p95 = {p95_phase4:.2f}ms\n"
        f"  delta        = {delta:.2f}ms (budget {_P95_BUDGET_MS}ms)\n"
    )

    assert delta <= _P95_BUDGET_MS, (
        f"TRCR-08 violated: trace write p95 overhead {delta:.2f}ms > "
        f"budget {_P95_BUDGET_MS}ms (baseline {p95_baseline:.2f}, phase4 {p95_phase4:.2f})"
    )
