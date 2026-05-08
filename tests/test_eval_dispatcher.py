"""Unit tests for tracer_ai/eval/dispatcher.py (Phase 5 Plan 04 Task 1).

Witness coverage:
  - DA1  enqueue spawns asyncio.create_task; returns synchronously
  - DA2  MockJudge happy path -> writer received rag.eval span with attrs +
         payload populated per D-5.03
  - DA3  TimeoutError -> rag.eval span with attrs[error.type]; faithfulness
         UPDATE NOT executed
  - DA4  RateLimitError -> attrs[error.type] == 'RateLimitError'
  - DA5  Cross-task parent linkage -- emitted rag.eval span has
         parent_span_id == root.span_id
  - DA6  After drain(), enqueue logs eval_dispatch_after_stop
  - DA7  drain timeout warns eval.dispatcher_drain_incomplete
  - DA8  drain with no pending tasks returns immediately
  - DA9  Successful score -> UPDATE traces SET faithfulness fired with right args
  - DA10 Pool UPDATE failure -> warn-log eval_update_traces_failed (Pitfall #5);
         emit still successful

Per Plan 05-01 testing pattern, env vars must be set BEFORE the module-top
``from tracer_ai.eval ...`` import so pytest autouse fixtures don't lose the
race against collection-time imports.
"""

from __future__ import annotations

import asyncio
import contextvars
import os
import sys
from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest

# Set env BEFORE the eval/llm_judge module is imported (autouse fixtures run
# AFTER collection-time imports per Plan 05-01 testing pattern).
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://t:t@db:5432/t")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-x")
os.environ.setdefault("VOYAGE_API_KEY", "pa-test")


@pytest.fixture(autouse=True)
def _configured_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://t:t@db:5432/t")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
    monkeypatch.setenv("VOYAGE_API_KEY", "pa-test")
    sys.modules.pop("tracer_ai.config", None)


# --- Test infrastructure ---------------------------------------------------


class _FakeWriter:
    """In-process TraceWriter recorder."""

    def __init__(self) -> None:
        self.emitted: list[Any] = []

    async def emit(self, span: Any) -> None:
        self.emitted.append(span)


class _FakeConn:
    def __init__(
        self,
        recorder: list[tuple[str, tuple[Any, ...]]],
        raise_on_execute: type[BaseException] | None = None,
    ) -> None:
        self._recorder = recorder
        self._raise = raise_on_execute

    async def execute(self, query: str, *args: Any) -> None:
        self._recorder.append((query, args))
        if self._raise is not None:
            raise self._raise("fake-pool execute failure")


class _FakeAcquireCtx:
    def __init__(
        self,
        recorder: list[tuple[str, tuple[Any, ...]]],
        raise_on_execute: type[BaseException] | None = None,
    ) -> None:
        self._recorder = recorder
        self._raise = raise_on_execute

    async def __aenter__(self) -> _FakeConn:
        return _FakeConn(self._recorder, raise_on_execute=self._raise)

    async def __aexit__(self, *exc: Any) -> None:
        return None


class _FakePool:
    def __init__(self, raise_on_execute: type[BaseException] | None = None) -> None:
        self.executed: list[tuple[str, tuple[Any, ...]]] = []
        self._raise = raise_on_execute

    def acquire(self, timeout: float | None = None) -> _FakeAcquireCtx:
        return _FakeAcquireCtx(self.executed, raise_on_execute=self._raise)


class _SlowMockJudge:
    """Sleep before returning -- used to test drain timeout."""

    name = "slow-mock"

    def __init__(self, sleep_seconds: float = 1.0) -> None:
        self._sleep = sleep_seconds

    async def score(self, answer: str, chunks: list[Any], query: str) -> Any:
        from tracer_ai.eval.protocols import EvalScores

        await asyncio.sleep(self._sleep)
        return EvalScores(faithfulness=0.5, relevance=0.5, rationale="slow")


def _make_chunk() -> Any:
    from tracer_ai.rag.types import RetrievedChunk

    return RetrievedChunk(
        id=uuid4(),
        doc_id="fake-doc",
        doc_section="auth",
        content="fake content",
        metadata={},
        score=0.9,
    )


# --- Tests ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_da1_enqueue_returns_immediately_and_spawns_task() -> None:
    """DA1: enqueue is synchronous; spawned task is in _pending."""
    from tracer_ai.eval.dispatcher import EvalDispatcher
    from tracer_ai.eval.llm_judge import MockJudge

    judge = MockJudge()
    writer = _FakeWriter()
    pool = _FakePool()
    dispatcher = EvalDispatcher(judge=judge, writer=writer, pool=pool)

    trace_id = uuid4()
    ctx = contextvars.copy_context()
    dispatcher.enqueue(trace_id, ctx, "an answer", [_make_chunk()], "a query")

    # The task is in _pending immediately (returned synchronously).
    assert len(dispatcher._pending) == 1

    await asyncio.gather(*dispatcher._pending, return_exceptions=True)
    # After completion, callback empties the set.
    assert len(dispatcher._pending) == 0


@pytest.mark.asyncio
async def test_da2_happy_path_emits_rag_eval_span_with_attrs() -> None:
    """DA2: MockJudge returns scores; writer receives rag.eval span with attrs + payload."""
    from tracer_ai.config import settings
    from tracer_ai.eval.dispatcher import EvalDispatcher
    from tracer_ai.eval.llm_judge import PROMPT_VERSION, MockJudge
    from tracer_ai.tracer.span import (
        RAG_EVAL_FAITHFULNESS,
        RAG_EVAL_JUDGE_LATENCY_MS,
        RAG_EVAL_JUDGE_MODEL,
        RAG_EVAL_JUDGE_PROMPT_VERSION,
        RAG_EVAL_RELEVANCE,
    )

    judge = MockJudge(faithfulness=0.8, relevance=0.9)
    writer = _FakeWriter()
    pool = _FakePool()
    dispatcher = EvalDispatcher(judge=judge, writer=writer, pool=pool)

    trace_id = uuid4()
    ctx = contextvars.copy_context()
    dispatcher.enqueue(trace_id, ctx, "answer text", [_make_chunk()], "query text")

    await asyncio.gather(*dispatcher._pending, return_exceptions=True)

    assert len(writer.emitted) == 1
    span = writer.emitted[0]
    assert span.name == "rag.eval"
    assert span.attrs[RAG_EVAL_FAITHFULNESS] == 0.8
    assert span.attrs[RAG_EVAL_RELEVANCE] == 0.9
    assert span.attrs[RAG_EVAL_JUDGE_MODEL] == settings.llm_judge_model
    assert span.attrs[RAG_EVAL_JUDGE_PROMPT_VERSION] == PROMPT_VERSION
    assert RAG_EVAL_JUDGE_LATENCY_MS in span.attrs
    # Payload contract per D-5.03
    assert span.payload is not None
    assert "judge_prompt" in span.payload
    assert "judge_response" in span.payload
    assert "input_tokens" in span.payload
    assert "output_tokens" in span.payload


@pytest.mark.asyncio
async def test_da3_timeout_emits_failure_span_and_skips_update() -> None:
    """DA3: TimeoutError -> attrs[error.type], no UPDATE traces SET faithfulness."""
    from tracer_ai.eval.dispatcher import EvalDispatcher
    from tracer_ai.eval.llm_judge import MockJudge
    from tracer_ai.tracer.span import (
        ERROR_TYPE,
        RAG_EVAL_FAITHFULNESS,
    )

    judge = MockJudge(raise_on_call=TimeoutError)
    writer = _FakeWriter()
    pool = _FakePool()
    dispatcher = EvalDispatcher(judge=judge, writer=writer, pool=pool)

    trace_id = uuid4()
    ctx = contextvars.copy_context()
    dispatcher.enqueue(trace_id, ctx, "answer", [_make_chunk()], "q")

    await asyncio.gather(*dispatcher._pending, return_exceptions=True)

    assert len(writer.emitted) == 1
    span = writer.emitted[0]
    assert span.attrs[ERROR_TYPE] == "TimeoutError"
    assert RAG_EVAL_FAITHFULNESS not in span.attrs or span.attrs.get(RAG_EVAL_FAITHFULNESS) is None
    assert span.payload is None
    # Faithfulness UPDATE was NOT executed.
    update_calls = [q for (q, _) in pool.executed if "UPDATE traces SET faithfulness" in q]
    assert len(update_calls) == 0


@pytest.mark.asyncio
async def test_da4_rate_limit_error_propagates_error_type() -> None:
    """DA4: any exception -> attrs[error.type] = type name."""

    class _RateLimitFake(Exception):
        pass

    # Rename class via metaclass-free trick: just verify that arbitrary type name lands.
    _RateLimitFake.__name__ = "RateLimitError"

    from tracer_ai.eval.dispatcher import EvalDispatcher
    from tracer_ai.eval.llm_judge import MockJudge
    from tracer_ai.tracer.span import ERROR_TYPE

    judge = MockJudge(raise_on_call=_RateLimitFake)
    writer = _FakeWriter()
    pool = _FakePool()
    dispatcher = EvalDispatcher(judge=judge, writer=writer, pool=pool)

    trace_id = uuid4()
    ctx = contextvars.copy_context()
    dispatcher.enqueue(trace_id, ctx, "answer", [_make_chunk()], "q")
    await asyncio.gather(*dispatcher._pending, return_exceptions=True)

    assert len(writer.emitted) == 1
    span = writer.emitted[0]
    assert span.attrs[ERROR_TYPE] == "RateLimitError"


@pytest.mark.asyncio
async def test_da5_cross_task_parent_linkage() -> None:
    """DA5: emitted rag.eval span has parent_span_id == root.span_id."""
    from tracer_ai.eval.dispatcher import EvalDispatcher
    from tracer_ai.eval.llm_judge import MockJudge
    from tracer_ai.tracer.context import capture_context, set_current_span
    from tracer_ai.tracer.writer import Span

    root = Span(
        trace_id=uuid4(),
        span_id=uuid4(),
        parent_span_id=None,
        name="rag.request",
        started_at=datetime.now(UTC),
        ended_at=None,
        attrs={},
        payload=None,
    )

    # Set the current span and capture the snapshot.
    set_current_span(root)
    ctx = capture_context()
    # Reset so the dispatcher has to install via attach_context.
    set_current_span(None)

    judge = MockJudge(faithfulness=0.7)
    writer = _FakeWriter()
    pool = _FakePool()
    dispatcher = EvalDispatcher(judge=judge, writer=writer, pool=pool)

    dispatcher.enqueue(root.trace_id, ctx, "answer", [_make_chunk()], "q")
    await asyncio.gather(*dispatcher._pending, return_exceptions=True)

    assert len(writer.emitted) == 1
    span = writer.emitted[0]
    assert span.parent_span_id == root.span_id
    assert span.trace_id == root.trace_id


@pytest.mark.asyncio
async def test_da6_enqueue_after_drain_logs_warning_and_skips_task() -> None:
    """DA6: dispatcher._stopped == True -> enqueue logs warning + does NOT spawn."""
    from tracer_ai.eval.dispatcher import EvalDispatcher
    from tracer_ai.eval.llm_judge import MockJudge

    dispatcher = EvalDispatcher(judge=MockJudge(), writer=_FakeWriter(), pool=_FakePool())
    await dispatcher.drain(timeout=0.1)
    assert dispatcher._stopped is True

    with patch("tracer_ai.eval.dispatcher.log") as mock_log:
        dispatcher.enqueue(uuid4(), contextvars.copy_context(), "a", [_make_chunk()], "q")
        # No task spawned.
        assert len(dispatcher._pending) == 0
        # Warn-log fired.
        warn_calls = [
            c
            for c in mock_log.warning.call_args_list
            if c.args and c.args[0] == "eval_dispatch_after_stop"
        ]
        assert len(warn_calls) >= 1


@pytest.mark.asyncio
async def test_da7_drain_timeout_warns_drain_incomplete() -> None:
    """DA7: slow judge + short drain timeout -> eval.dispatcher_drain_incomplete warn-log."""
    from tracer_ai.eval.dispatcher import EvalDispatcher

    judge = _SlowMockJudge(sleep_seconds=2.0)
    dispatcher = EvalDispatcher(judge=judge, writer=_FakeWriter(), pool=_FakePool())
    dispatcher.enqueue(uuid4(), contextvars.copy_context(), "a", [_make_chunk()], "q")

    with patch("tracer_ai.eval.dispatcher.log") as mock_log:
        await dispatcher.drain(timeout=0.1)

        warn_calls = [
            c
            for c in mock_log.warning.call_args_list
            if c.args and c.args[0] == "eval.dispatcher_drain_incomplete"
        ]
        assert len(warn_calls) >= 1

    # Cleanup: cancel surviving task so pytest doesn't complain about pending tasks.
    import contextlib

    for t in list(dispatcher._pending):
        t.cancel()
        with contextlib.suppress(BaseException):
            await t


@pytest.mark.asyncio
async def test_da8_drain_with_no_pending_returns_immediately() -> None:
    """DA8: drain with empty _pending returns without warn-log."""
    from tracer_ai.eval.dispatcher import EvalDispatcher
    from tracer_ai.eval.llm_judge import MockJudge

    dispatcher = EvalDispatcher(judge=MockJudge(), writer=_FakeWriter(), pool=_FakePool())
    with patch("tracer_ai.eval.dispatcher.log") as mock_log:
        await dispatcher.drain(timeout=5.0)
        warn_calls = [
            c
            for c in mock_log.warning.call_args_list
            if c.args and c.args[0] == "eval.dispatcher_drain_incomplete"
        ]
        assert len(warn_calls) == 0


@pytest.mark.asyncio
async def test_da9_successful_score_fires_update_traces_with_correct_args() -> None:
    """DA9: UPDATE traces SET faithfulness = $1 WHERE id = $2 fires with right args."""
    from tracer_ai.eval.dispatcher import EvalDispatcher
    from tracer_ai.eval.llm_judge import MockJudge

    judge = MockJudge(faithfulness=0.42, relevance=0.5)
    writer = _FakeWriter()
    pool = _FakePool()
    dispatcher = EvalDispatcher(judge=judge, writer=writer, pool=pool)

    trace_id = uuid4()
    ctx = contextvars.copy_context()
    dispatcher.enqueue(trace_id, ctx, "answer", [_make_chunk()], "q")
    await asyncio.gather(*dispatcher._pending, return_exceptions=True)

    update_calls = [
        (q, args) for (q, args) in pool.executed if "UPDATE traces SET faithfulness" in q
    ]
    assert len(update_calls) == 1
    _, args = update_calls[0]
    assert args[0] == pytest.approx(0.42)
    assert args[1] == trace_id


@pytest.mark.asyncio
async def test_da10_pool_update_failure_logs_warning_does_not_reraise() -> None:
    """DA10: UPDATE failure -> warn-log eval_update_traces_failed; emit still happens."""
    from tracer_ai.eval.dispatcher import EvalDispatcher
    from tracer_ai.eval.llm_judge import MockJudge

    judge = MockJudge(faithfulness=0.7)
    writer = _FakeWriter()
    pool = _FakePool(raise_on_execute=RuntimeError)
    dispatcher = EvalDispatcher(judge=judge, writer=writer, pool=pool)

    trace_id = uuid4()
    ctx = contextvars.copy_context()
    with patch("tracer_ai.eval.dispatcher.log") as mock_log:
        dispatcher.enqueue(trace_id, ctx, "answer", [_make_chunk()], "q")
        await asyncio.gather(*dispatcher._pending, return_exceptions=True)

        warn_calls = [
            c
            for c in mock_log.warning.call_args_list
            if c.args and c.args[0] == "eval_update_traces_failed"
        ]
        assert len(warn_calls) >= 1

    # The eval span emit still happened (CLAUDE.md invariant: never fail user requests).
    assert len(writer.emitted) == 1
