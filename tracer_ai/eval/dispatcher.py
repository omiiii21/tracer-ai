"""EvalDispatcher -- async judge dispatch via asyncio.create_task (D-5.10).

Dispatched from tracer_ai/api/chat.py SSE generator immediately after the
``final`` frame yields. The dispatcher captures the contextvar snapshot from
the SSE generator (Pitfall #1 -- BEFORE rag.request ends), uses
``asyncio.create_task`` to spawn the judge call as a background coroutine, and
routes the resulting rag.eval span through the SAME BoundedDropOldestQueue
+ SpanConsumer path Phase 4 uses for sync spans (D-5.08).

Failure semantics (Pitfall #3 / D-5.07): every layer is wrapped in try/except.
Judge timeout / rate-limit / parse-shape errors emit a rag.eval span with
``attrs[error.type]`` populated and traces.faithfulness UPDATE skipped. The
user request NEVER fails because of an eval failure.

Drain (D-5.10): lifespan finally block calls ``dispatcher.drain(5.0)`` BEFORE
``consumer.drain()`` -- eval may emit spans into the consumer's queue, so the
consumer must outlive the dispatcher.
"""

from __future__ import annotations

import asyncio
import time
from contextvars import Context
from datetime import UTC, datetime
from uuid import UUID, uuid4

import asyncpg
import structlog

from tracer_ai.config import settings
from tracer_ai.eval.llm_judge import PROMPT_VERSION, get_judge_semaphore
from tracer_ai.eval.protocols import Judge
from tracer_ai.rag.types import RetrievedChunk
from tracer_ai.tracer.context import attach_context, current_span
from tracer_ai.tracer.span import (
    ERROR_TYPE,
    RAG_EVAL_FAITHFULNESS,
    RAG_EVAL_JUDGE_LATENCY_MS,
    RAG_EVAL_JUDGE_MODEL,
    RAG_EVAL_JUDGE_PROMPT_VERSION,
    RAG_EVAL_RELEVANCE,
)
from tracer_ai.tracer.writer import Span, TraceWriter

log = structlog.get_logger()

_SPAN_EVAL = "rag.eval"


class EvalDispatcher:
    """Async LLM-as-judge dispatcher (D-5.10 / D-5.08 / D-5.07).

    Owned by ``tracer_ai/api/lifespan.py`` and stashed at
    ``app.state.eval_dispatcher``. The SSE generator in
    ``tracer_ai/api/chat.py`` calls ``enqueue(...)`` immediately after the
    ``event: final`` frame yields; the dispatcher spawns a background task,
    awaits the judge inside the task (with the snapshotted ``_current_span``
    re-attached so ``current_span()`` returns the rag.request root), then
    emits a ``rag.eval`` span via the injected ``TraceWriter`` and stamps
    ``traces.faithfulness`` via the injected ``asyncpg.Pool``.
    """

    def __init__(
        self,
        judge: Judge,
        writer: TraceWriter,
        pool: asyncpg.Pool,
    ) -> None:
        self._judge = judge
        self._writer = writer
        self._pool = pool
        self._pending: set[asyncio.Task[None]] = set()
        self._stopped = False

    def enqueue(
        self,
        trace_id: UUID,
        ctx_snapshot: Context,
        answer: str,
        chunks: list[RetrievedChunk],
        query: str,
    ) -> None:
        """Spawn a tracked background judge task. Returns immediately.

        Pitfall #3: this method must NEVER raise back into the SSE generator.
        Any unexpected error during ``asyncio.create_task`` is caught and
        logged. After ``drain()``, subsequent calls log ``eval_dispatch_after_stop``
        and skip task creation.
        """
        if self._stopped:
            log.warning("eval_dispatch_after_stop", trace_id=str(trace_id))
            return
        try:
            task = asyncio.create_task(
                self._run_in_context(trace_id, ctx_snapshot, answer, chunks, query),
                name=f"eval-{trace_id}",
            )
            self._pending.add(task)
            task.add_done_callback(self._pending.discard)
        except Exception as exc:
            log.warning(
                "eval.enqueue_swallowed",
                error=str(exc),
                trace_id=str(trace_id),
            )

    async def _run_in_context(
        self,
        trace_id: UUID,
        ctx_snapshot: Context,
        answer: str,
        chunks: list[RetrievedChunk],
        query: str,
    ) -> None:
        """Re-install the snapshot's ``_current_span`` and dispatch scoring."""
        attach_context(ctx_snapshot)
        await self._do_score(trace_id, answer, chunks, query)

    async def _do_score(
        self,
        trace_id: UUID,
        answer: str,
        chunks: list[RetrievedChunk],
        query: str,
    ) -> None:
        """Score the answer; emit rag.eval span; UPDATE traces denorm column.

        Pitfall #3: every external operation (judge call, writer.emit,
        pool.acquire+execute) is wrapped in try/except so the eval pipeline
        never re-raises. Pitfall #5: the traces UPDATE only fires on score
        success; UPDATE failure is logged but does not corrupt the rag.eval
        span emit.
        """
        parent = current_span()
        started_at = datetime.now(UTC)
        t0 = time.perf_counter()

        eval_span: Span = Span(
            trace_id=parent.trace_id if parent is not None else trace_id,
            span_id=uuid4(),
            parent_span_id=parent.span_id if parent is not None else None,
            name=_SPAN_EVAL,
            started_at=started_at,
            ended_at=None,
            attrs={},
            payload=None,
        )

        scores = None
        try:
            async with get_judge_semaphore():
                scores = await self._judge.score(answer, chunks, query)
        except BaseException as exc:
            # Pitfall #3 -- never re-raise.
            log.warning(
                "eval.judge_failed",
                trace_id=str(trace_id),
                error=str(exc),
                error_type=type(exc).__name__,
            )
            eval_span.attrs[ERROR_TYPE] = type(exc).__name__
        finally:
            eval_span.ended_at = datetime.now(UTC)
            eval_span.attrs[RAG_EVAL_JUDGE_MODEL] = settings.llm_judge_model
            eval_span.attrs[RAG_EVAL_JUDGE_PROMPT_VERSION] = PROMPT_VERSION
            if scores is not None:
                if scores.faithfulness is not None:
                    eval_span.attrs[RAG_EVAL_FAITHFULNESS] = scores.faithfulness
                if scores.relevance is not None:
                    eval_span.attrs[RAG_EVAL_RELEVANCE] = scores.relevance
                eval_span.attrs[RAG_EVAL_JUDGE_LATENCY_MS] = scores.judge_latency_ms or int(
                    (time.perf_counter() - t0) * 1000
                )
                eval_span.payload = {
                    "judge_prompt": scores.judge_prompt,
                    "judge_response": scores.judge_response,
                    "input_tokens": scores.input_tokens,
                    "output_tokens": scores.output_tokens,
                }

            # Emit span -- never re-raise.
            try:
                await self._writer.emit(eval_span)
            except BaseException as exc:
                log.warning(
                    "eval.emit_swallowed",
                    error=str(exc),
                    trace_id=str(trace_id),
                )

            # Pitfall #5: UPDATE traces denorm column ONLY on score success.
            if scores is not None and scores.faithfulness is not None:
                try:
                    async with self._pool.acquire(timeout=2.0) as conn:
                        await conn.execute(
                            "UPDATE traces SET faithfulness = $1 WHERE id = $2",
                            float(scores.faithfulness),
                            trace_id,
                        )
                except BaseException as exc:
                    log.warning(
                        "eval_update_traces_failed",
                        error=str(exc),
                        trace_id=str(trace_id),
                    )

            log.info(
                "eval.scored",
                trace_id=str(trace_id),
                faithfulness=getattr(scores, "faithfulness", None),
                relevance=getattr(scores, "relevance", None),
                error_type=eval_span.attrs.get(ERROR_TYPE),
            )

    async def drain(self, timeout: float = 5.0) -> None:
        """Lifespan finally block awaits this BEFORE the SpanConsumer drain.

        Sets ``_stopped = True`` to prevent new enqueue calls; awaits all
        pending tasks up to ``timeout`` seconds; on timeout, warn-log
        ``eval.dispatcher_drain_incomplete remaining=N``. Never raises -- the
        lifespan finally chain must always reach pool.close().
        """
        self._stopped = True
        if not self._pending:
            return
        try:
            await asyncio.wait_for(
                asyncio.gather(*self._pending, return_exceptions=True),
                timeout=timeout,
            )
        except TimeoutError:
            log.warning(
                "eval.dispatcher_drain_incomplete",
                remaining=len(self._pending),
            )
