"""EVAL-04 acceptance: rag.eval span emitted with correct parent linkage.

Witnesses:
  - PA1 ChatFinalEvent carries non-None ctx_snapshot, answer, chunks_for_judge
  - PA2 After enqueue + gather, the writer emitted exactly one rag.eval span
        with parent_span_id == rag.request span_id and trace_id matching
  - PA3 The rag.eval span's attrs[RAG_EVAL_FAITHFULNESS] == 0.8 (MockJudge)
        AND model_dump(mode="json") of ChatFinalEvent does NOT include the
        Phase 5 private fields (T-05-04-10 mitigation acceptance)
"""

from __future__ import annotations

import asyncio
import os
import sys
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
    async def retrieve(self, query_embedding: list[float], top_k: int) -> list[Any]:
        return [_make_chunk() for _ in range(top_k)]


class _FakeLLM:
    name = "fake-llm"

    def stream(self, messages: list[Any], *, max_tokens: int = 1024) -> Any:
        from tracer_ai.rag.types import Final, LLMResult, TextDelta

        async def _gen() -> Any:
            yield TextDelta(text="fake answer ")
            yield TextDelta(text="text")
            yield Final(
                result=LLMResult(
                    answer="fake answer text",
                    input_tokens=10,
                    output_tokens=5,
                    estimated_cost_usd=0.0001,
                )
            )

        return _gen()


class _RecordingWriter:
    """Captures every span emitted to the writer."""

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

    async def close(self) -> None:
        return None


# --- Tests ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pa1_chat_final_event_carries_phase_5_private_fields() -> None:
    """PA1: ChatFinalEvent has non-None ctx_snapshot, answer, chunks_for_judge."""
    from tracer_ai.rag.pipeline import Pipeline
    from tracer_ai.rag.types import ChatFinalEvent

    writer = _RecordingWriter()
    pool = _FakePool()
    pipeline = Pipeline(
        _FakeEmbedder(), _FakeRetriever(), _FakeLLM(), writer, top_k=2, db_pool=pool
    )

    final_event: ChatFinalEvent | None = None
    async for ev in pipeline.run_chat_stream("how does auth work?"):
        if isinstance(ev, ChatFinalEvent):
            final_event = ev

    assert final_event is not None
    assert final_event.ctx_snapshot is not None
    assert final_event.answer == "fake answer text"
    assert len(final_event.chunks_for_judge) == 2
    assert final_event.query == "how does auth work?"


@pytest.mark.asyncio
async def test_pa2_eval_span_parent_linkage() -> None:
    """PA2: rag.eval span has parent_span_id == rag.request span_id."""
    from tracer_ai.eval.dispatcher import EvalDispatcher
    from tracer_ai.eval.llm_judge import MockJudge
    from tracer_ai.rag.pipeline import Pipeline
    from tracer_ai.rag.types import ChatFinalEvent

    writer = _RecordingWriter()
    pool = _FakePool()
    pipeline = Pipeline(
        _FakeEmbedder(), _FakeRetriever(), _FakeLLM(), writer, top_k=2, db_pool=pool
    )
    judge = MockJudge(faithfulness=0.8, relevance=0.9)
    dispatcher = EvalDispatcher(judge=judge, writer=writer, pool=pool)

    final_event: ChatFinalEvent | None = None
    async for ev in pipeline.run_chat_stream("test query"):
        if isinstance(ev, ChatFinalEvent):
            final_event = ev

    assert final_event is not None
    # Find the rag.request span emitted by the pipeline (last one to emit).
    rag_request_spans = [s for s in writer.emitted if s.name == "rag.request"]
    assert len(rag_request_spans) == 1
    rag_request_span = rag_request_spans[0]

    # Dispatch the eval task using the captured snapshot.
    dispatcher.enqueue(
        trace_id=UUID(final_event.trace_id),
        ctx_snapshot=final_event.ctx_snapshot,
        answer=final_event.answer,
        chunks=final_event.chunks_for_judge,
        query=final_event.query,
    )
    await asyncio.gather(*dispatcher._pending, return_exceptions=True)

    # Find the rag.eval span.
    rag_eval_spans = [s for s in writer.emitted if s.name == "rag.eval"]
    assert len(rag_eval_spans) == 1
    rag_eval = rag_eval_spans[0]

    assert rag_eval.parent_span_id == rag_request_span.span_id
    assert rag_eval.trace_id == rag_request_span.trace_id


@pytest.mark.asyncio
async def test_pa3_eval_attrs_populated_and_private_fields_excluded_from_wire() -> None:
    """PA3: rag.eval has faithfulness=0.8; SSE wire body excludes Phase 5 fields."""
    from tracer_ai.eval.dispatcher import EvalDispatcher
    from tracer_ai.eval.llm_judge import MockJudge
    from tracer_ai.rag.pipeline import Pipeline
    from tracer_ai.rag.types import ChatFinalEvent
    from tracer_ai.tracer.span import RAG_EVAL_FAITHFULNESS

    writer = _RecordingWriter()
    pool = _FakePool()
    pipeline = Pipeline(
        _FakeEmbedder(), _FakeRetriever(), _FakeLLM(), writer, top_k=2, db_pool=pool
    )
    judge = MockJudge(faithfulness=0.8, relevance=0.9)
    dispatcher = EvalDispatcher(judge=judge, writer=writer, pool=pool)

    final_event: ChatFinalEvent | None = None
    async for ev in pipeline.run_chat_stream("test query"):
        if isinstance(ev, ChatFinalEvent):
            final_event = ev

    assert final_event is not None

    # Wire-shape acceptance (T-05-04-10): the dumped JSON does NOT include
    # the four Phase 5 private fields.
    wire = final_event.model_dump(mode="json")
    assert "ctx_snapshot" not in wire
    assert "chunks_for_judge" not in wire
    assert "query" not in wire
    assert "answer" not in wire

    dispatcher.enqueue(
        trace_id=UUID(final_event.trace_id),
        ctx_snapshot=final_event.ctx_snapshot,
        answer=final_event.answer,
        chunks=final_event.chunks_for_judge,
        query=final_event.query,
    )
    await asyncio.gather(*dispatcher._pending, return_exceptions=True)

    rag_eval_spans = [s for s in writer.emitted if s.name == "rag.eval"]
    assert len(rag_eval_spans) == 1
    assert rag_eval_spans[0].attrs[RAG_EVAL_FAITHFULNESS] == 0.8
