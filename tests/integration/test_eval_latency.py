"""EVAL-05 acceptance: eval span lands within 25s of SSE final frame.

LA1: With MockJudge returning instantly (no sleep), the wall-clock time from
"final frame yielded" to "all dispatcher tasks complete" is < 25s. Validates
that the queue + UPDATE path on its own is fast enough; comfortable headroom
under the 30s budget when the judge is real Anthropic Haiku (≤21s wall budget
per D-5.05). Uses asyncio.wait_for(..., timeout=25.0) to enforce.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from typing import Any
from uuid import UUID, uuid4

import pytest

# Plan 05-01 testing pattern: env vars BEFORE module-top imports.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://t:t@db:5432/t")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-x")
os.environ.setdefault("VOYAGE_API_KEY", "pa-test")


@pytest.fixture(autouse=True)
def _configured_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://t:t@db:5432/t")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
    monkeypatch.setenv("VOYAGE_API_KEY", "pa-test")
    sys.modules.pop("tracer_ai.config", None)
    sys.modules.pop("tracer_ai.rag.pipeline", None)


# --- Test infrastructure ---------------------------------------------------


def _make_chunk() -> Any:
    from tracer_ai.rag.types import RetrievedChunk

    return RetrievedChunk(
        id=uuid4(),
        doc_id="fake-doc",
        doc_section="auth",
        content="content",
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
    async def retrieve(self, query_embedding: list[float], top_k: int) -> list[Any]:
        return [_make_chunk() for _ in range(top_k)]


class _FakeLLM:
    name = "fake-llm"

    def stream(self, messages: list[Any], *, max_tokens: int = 1024) -> Any:
        from tracer_ai.rag.types import Final, LLMResult, TextDelta

        async def _gen() -> Any:
            yield TextDelta(text="ans")
            yield Final(
                result=LLMResult(
                    answer="ans",
                    input_tokens=10,
                    output_tokens=5,
                    estimated_cost_usd=0.0001,
                )
            )

        return _gen()


class _RecordingWriter:
    def __init__(self) -> None:
        self.emitted: list[Any] = []

    async def emit(self, span: Any) -> None:
        self.emitted.append(span)


class _FakeConn:
    async def execute(self, query: str, *args: Any) -> None:
        return None


class _FakeAcquireCtx:
    async def __aenter__(self) -> _FakeConn:
        return _FakeConn()

    async def __aexit__(self, *exc: Any) -> None:
        return None


class _FakePool:
    def acquire(self, timeout: float | None = None) -> _FakeAcquireCtx:
        return _FakeAcquireCtx()


# --- Tests ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_la1_eval_lands_within_25s_of_final_frame() -> None:
    """LA1: instant MockJudge -> dispatcher pending drains in << 25s."""
    from tracer_ai.eval.dispatcher import EvalDispatcher
    from tracer_ai.eval.llm_judge import MockJudge
    from tracer_ai.rag.pipeline import Pipeline
    from tracer_ai.rag.types import ChatFinalEvent

    writer = _RecordingWriter()
    pool = _FakePool()
    pipeline = Pipeline(
        _FakeEmbedder(), _FakeRetriever(), _FakeLLM(), writer, top_k=2, db_pool=pool
    )
    judge = MockJudge(faithfulness=0.7, relevance=0.7)
    dispatcher = EvalDispatcher(judge=judge, writer=writer, pool=pool)

    final_event: ChatFinalEvent | None = None
    async for ev in pipeline.run_chat_stream("query"):
        if isinstance(ev, ChatFinalEvent):
            final_event = ev
    assert final_event is not None

    # Mark the time the final frame "yielded" -- equivalent to immediately after
    # the final iterator yield in the SSE generator.
    t0 = time.perf_counter()
    dispatcher.enqueue(
        trace_id=UUID(final_event.trace_id),
        ctx_snapshot=final_event.ctx_snapshot,
        answer=final_event.answer,
        chunks=final_event.chunks_for_judge,
        query=final_event.query,
    )

    # Enforce the EVAL-05 25s budget on the dispatcher drain.
    await asyncio.wait_for(
        asyncio.gather(*dispatcher._pending, return_exceptions=True),
        timeout=25.0,
    )
    elapsed = time.perf_counter() - t0
    assert elapsed < 25.0, f"eval drain took {elapsed:.3f}s, exceeds 25s budget"

    rag_eval_spans = [s for s in writer.emitted if s.name == "rag.eval"]
    assert len(rag_eval_spans) == 1
    span = rag_eval_spans[0]
    # Sanity: span end_time - start_time is short on instant mock.
    if span.ended_at is not None:
        elapsed_span = (span.ended_at - span.started_at).total_seconds()
        assert elapsed_span < 1.0, f"rag.eval span duration {elapsed_span:.3f}s"
