"""EVAL-02 acceptance: judge failures NEVER fail user requests.

Witnesses:
  - CF1 POST /chat with MockJudge(raise_on_call=TimeoutError) returns 200 +
        full SSE final frame
  - CF2 After the request completes, the eval dispatcher emitted exactly one
        rag.eval span with attrs[ERROR_TYPE] == "TimeoutError"
  - CF3 No UPDATE traces SET faithfulness statement was issued (Pitfall #5)
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any
from uuid import uuid4

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
    sys.modules.pop("tracer_ai.api.chat", None)
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


class _RecordingConn:
    def __init__(self, recorder: list[tuple[str, tuple[Any, ...]]]) -> None:
        self._recorder = recorder

    async def execute(self, query: str, *args: Any) -> None:
        self._recorder.append((query, args))


class _RecordingAcquireCtx:
    def __init__(self, recorder: list[tuple[str, tuple[Any, ...]]]) -> None:
        self._recorder = recorder

    async def __aenter__(self) -> _RecordingConn:
        return _RecordingConn(self._recorder)

    async def __aexit__(self, *exc: Any) -> None:
        return None


class _RecordingPool:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[Any, ...]]] = []

    def acquire(self, timeout: float | None = None) -> _RecordingAcquireCtx:
        return _RecordingAcquireCtx(self.executed)


def _build_app(pipeline: Any, dispatcher: Any) -> Any:
    from fastapi import FastAPI

    from tracer_ai.api import chat

    app = FastAPI(title="test")
    app.state.pipeline = pipeline
    app.state.eval_dispatcher = dispatcher
    app.include_router(chat.router)
    return app


# --- Tests ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cf1_chat_returns_200_with_final_frame_when_judge_times_out() -> None:
    """CF1: POST /chat returns 200 + full SSE final frame even when judge fails."""
    from fastapi.testclient import TestClient

    from tracer_ai.eval.dispatcher import EvalDispatcher
    from tracer_ai.eval.llm_judge import MockJudge
    from tracer_ai.rag.pipeline import Pipeline

    writer = _RecordingWriter()
    pool = _RecordingPool()
    pipeline = Pipeline(
        _FakeEmbedder(), _FakeRetriever(), _FakeLLM(), writer, top_k=2, db_pool=pool
    )
    judge = MockJudge(raise_on_call=TimeoutError)
    dispatcher = EvalDispatcher(judge=judge, writer=writer, pool=pool)
    app = _build_app(pipeline, dispatcher)

    client = TestClient(app)
    resp = client.post("/chat", json={"question": "test"})
    assert resp.status_code == 200
    body = resp.text
    assert "event: final" in body
    assert "event: token" in body

    # Drain pending eval tasks so cf2/cf3 assertions can read their results.
    await asyncio.gather(*dispatcher._pending, return_exceptions=True)


@pytest.mark.asyncio
async def test_cf2_eval_span_carries_error_type_on_timeout() -> None:
    """CF2: rag.eval span has attrs[ERROR_TYPE] == 'TimeoutError'."""
    from fastapi.testclient import TestClient

    from tracer_ai.eval.dispatcher import EvalDispatcher
    from tracer_ai.eval.llm_judge import MockJudge
    from tracer_ai.rag.pipeline import Pipeline
    from tracer_ai.tracer.span import ERROR_TYPE

    writer = _RecordingWriter()
    pool = _RecordingPool()
    pipeline = Pipeline(
        _FakeEmbedder(), _FakeRetriever(), _FakeLLM(), writer, top_k=2, db_pool=pool
    )
    judge = MockJudge(raise_on_call=TimeoutError)
    dispatcher = EvalDispatcher(judge=judge, writer=writer, pool=pool)
    app = _build_app(pipeline, dispatcher)

    client = TestClient(app)
    resp = client.post("/chat", json={"question": "test"})
    assert resp.status_code == 200
    # Drain pending eval tasks
    await asyncio.gather(*dispatcher._pending, return_exceptions=True)

    rag_eval_spans = [s for s in writer.emitted if s.name == "rag.eval"]
    assert len(rag_eval_spans) == 1
    assert rag_eval_spans[0].attrs[ERROR_TYPE] == "TimeoutError"


@pytest.mark.asyncio
async def test_cf3_no_faithfulness_update_on_judge_failure() -> None:
    """CF3: No `UPDATE traces SET faithfulness` statement issued (Pitfall #5)."""
    from fastapi.testclient import TestClient

    from tracer_ai.eval.dispatcher import EvalDispatcher
    from tracer_ai.eval.llm_judge import MockJudge
    from tracer_ai.rag.pipeline import Pipeline

    writer = _RecordingWriter()
    pool = _RecordingPool()
    pipeline = Pipeline(
        _FakeEmbedder(), _FakeRetriever(), _FakeLLM(), writer, top_k=2, db_pool=pool
    )
    judge = MockJudge(raise_on_call=TimeoutError)
    dispatcher = EvalDispatcher(judge=judge, writer=writer, pool=pool)
    app = _build_app(pipeline, dispatcher)

    client = TestClient(app)
    resp = client.post("/chat", json={"question": "test"})
    assert resp.status_code == 200
    await asyncio.gather(*dispatcher._pending, return_exceptions=True)

    faithfulness_updates = [
        (q, args) for (q, args) in pool.executed if "UPDATE traces SET faithfulness" in q
    ]
    assert len(faithfulness_updates) == 0
