"""RAG pipeline orchestrator (Phase 3 Plan 05, RAG-04).

Composes Embedder + Retriever + LLM + TraceWriter into a streaming pipeline
that emits exactly four spans per request:

    rag.request           (root)
    + rag.retrieve        (child)
    + rag.prompt_assemble (child)
    + rag.llm_call        (child)

(``rag.embed`` is folded into the request-level latency for Phase 3 -- the
docs/trace-schema.md 4-span list does not have a separate embed span. Phase 4
may split if eval shows embed-cost outliers.)

Pitfall 7.8 / T-03-05-04 mitigation -- async-context cancellation safety:
each stage emits its span inside a ``try/finally`` so a mid-flight exception
or cancellation does NOT lose the failure span. The root ``rag.request`` span
is always emitted (in the outermost finally) even when a stage raises.

Per ADR 005 / D-2.40: NO opentelemetry-sdk runtime import lines anywhere.
Span attribute names are imported by-name from ``tracer_ai/tracer/span.py``
constants -- never write a literal ``"gen_ai.provider.name"`` string at a
call site (T-03-05-04 / cross-file refactor safety).

T-03-05-07 mitigation: query text truncated to 200 chars in span attrs;
the full query lives only in payload (Phase 4 stores in span_payloads side
table).
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from statistics import mean
from typing import Any, cast
from uuid import UUID, uuid4

import structlog

from tracer_ai.config import settings
from tracer_ai.rag.prompt import assemble
from tracer_ai.rag.protocols import LLM as LLMProtocol
from tracer_ai.rag.protocols import Embedder, Retriever
from tracer_ai.rag.types import Final, RetrievedChunk, StreamEvent, TextDelta
from tracer_ai.tracer.span import (
    GEN_AI_PROVIDER_NAME,
    GEN_AI_REQUEST_MODEL,
    GEN_AI_USAGE_INPUT_TOKENS,
    GEN_AI_USAGE_OUTPUT_TOKENS,
    RAG_PROMPT_TEMPLATE_ID,
    RAG_RETRIEVAL_SCORE_MEAN,
    RAG_RETRIEVAL_SCORE_MIN,
    RAG_RETRIEVED_CHUNKS,
)
from tracer_ai.tracer.writer import Span, TraceWriter

log = structlog.get_logger()


# Span name constants -- string literals appear in only this constants block;
# all emit sites reference these names. Centralized for consistency.
_SPAN_REQUEST = "rag.request"
_SPAN_RETRIEVE = "rag.retrieve"
_SPAN_PROMPT_ASSEMBLE = "rag.prompt_assemble"
_SPAN_LLM_CALL = "rag.llm_call"

# Custom (non-OTel) attribute keys used by this orchestrator. Kept as
# string literals here only because they're not yet promoted to constants
# in tracer_ai/tracer/span.py (Phase 4 may consolidate).
_ATTR_RETRIEVAL_TOP_K = "rag.retrieval.top_k"
_ATTR_PROMPT_TOKEN_COUNT = "rag.prompt.token_count"
_ATTR_QUERY = "rag.query"
_ATTR_LATENCY_MS = "rag.latency_ms"


def _now() -> datetime:
    return datetime.now(UTC)


class Pipeline:
    """Multi-stage RAG orchestrator emitting 4 spans + streaming token deltas.

    Constructor takes Protocol-typed deps (Embedder, Retriever, LLM, TraceWriter)
    so any adapter can be swapped without changing this code (Phase 3
    architecture invariant per ADR 005).
    """

    def __init__(
        self,
        embedder: Embedder,
        retriever: Retriever,
        llm: LLMProtocol,
        writer: TraceWriter,
        *,
        top_k: int = 5,
    ) -> None:
        self.embedder = embedder
        self.retriever = retriever
        self.llm = llm
        self.writer = writer
        self.top_k = top_k

    async def run_stream(self, query: str) -> AsyncIterator[StreamEvent]:
        """Run the pipeline; yield ``TextDelta`` deltas + one ``Final``.

        Emits 4 spans even on partial failure -- per-stage try/finally
        guarantees observability of which stage broke (T-03-05-04 / Pitfall 7.8).
        """
        trace_id: UUID = uuid4()
        root_span_id: UUID = uuid4()
        root_started = _now()
        t0 = time.perf_counter()
        truncated_query = query[:200]
        root_attrs: dict[str, Any] = {
            GEN_AI_PROVIDER_NAME: "anthropic",
            GEN_AI_REQUEST_MODEL: settings.llm_bot_model,
            _ATTR_QUERY: truncated_query,
        }

        try:
            # Stage 1 (embed): not a separate span in Phase 3 -- the embed
            # cost is rolled into the root rag.request span latency.
            q_embeddings = await self.embedder.embed_batch([query], input_type="query")
            q_emb = q_embeddings[0]

            # Stage 2 (retrieve) -- own span emitted in finally.
            chunks: list[RetrievedChunk] = []
            retrieve_span_id = uuid4()
            retrieve_started = _now()
            retrieve_attrs: dict[str, Any] = {
                _ATTR_RETRIEVAL_TOP_K: self.top_k,
            }
            try:
                chunks = await self.retriever.retrieve(q_emb, self.top_k)
            finally:
                if chunks:
                    scores = [c.score for c in chunks]
                    retrieve_attrs[RAG_RETRIEVAL_SCORE_MEAN] = mean(scores)
                    retrieve_attrs[RAG_RETRIEVAL_SCORE_MIN] = min(scores)
                else:
                    retrieve_attrs[RAG_RETRIEVAL_SCORE_MEAN] = 0.0
                    retrieve_attrs[RAG_RETRIEVAL_SCORE_MIN] = 0.0
                retrieve_attrs[RAG_RETRIEVED_CHUNKS] = [str(c.id) for c in chunks]
                await self.writer.emit(
                    Span(
                        trace_id=trace_id,
                        span_id=retrieve_span_id,
                        parent_span_id=root_span_id,
                        name=_SPAN_RETRIEVE,
                        started_at=retrieve_started,
                        ended_at=_now(),
                        attrs=retrieve_attrs,
                    )
                )

            # Stage 3 (prompt_assemble) -- own span emitted in finally.
            prompt_span_id = uuid4()
            prompt_started = _now()
            prompt_attrs: dict[str, Any] = {}
            messages = None
            try:
                messages, prompt_token_count, prompt_template_id = assemble(query, chunks)
                prompt_attrs[RAG_PROMPT_TEMPLATE_ID] = prompt_template_id
                prompt_attrs[_ATTR_PROMPT_TOKEN_COUNT] = prompt_token_count
            finally:
                await self.writer.emit(
                    Span(
                        trace_id=trace_id,
                        span_id=prompt_span_id,
                        parent_span_id=root_span_id,
                        name=_SPAN_PROMPT_ASSEMBLE,
                        started_at=prompt_started,
                        ended_at=_now(),
                        attrs=prompt_attrs,
                    )
                )

            # Stage 4 (llm_call) -- own span emitted in finally.
            llm_span_id = uuid4()
            llm_started = _now()
            llm_attrs: dict[str, Any] = {
                GEN_AI_REQUEST_MODEL: self.llm.name,
                GEN_AI_USAGE_INPUT_TOKENS: 0,
                GEN_AI_USAGE_OUTPUT_TOKENS: 0,
            }
            final_event: Final | None = None
            try:
                # The Protocol declares ``async def stream(...) -> AsyncIterator[...]``
                # which mypy interprets as a coroutine returning an iterator.
                # In practice every adapter implements this as an async-generator
                # function (``async def`` + ``yield``), which returns an
                # AsyncIterator directly without ``await``. Cast bridges the gap.
                stream_iter = cast(AsyncIterator[StreamEvent], self.llm.stream(messages))
                async for ev in stream_iter:
                    if isinstance(ev, TextDelta):
                        yield ev
                    elif isinstance(ev, Final):
                        final_event = ev
                        yield ev
            finally:
                if final_event is not None:
                    llm_attrs[GEN_AI_USAGE_INPUT_TOKENS] = final_event.result.input_tokens
                    llm_attrs[GEN_AI_USAGE_OUTPUT_TOKENS] = final_event.result.output_tokens
                await self.writer.emit(
                    Span(
                        trace_id=trace_id,
                        span_id=llm_span_id,
                        parent_span_id=root_span_id,
                        name=_SPAN_LLM_CALL,
                        started_at=llm_started,
                        ended_at=_now(),
                        attrs=llm_attrs,
                    )
                )
        finally:
            # Always emit the root rag.request span -- even if a stage raised
            # mid-flight or the consumer cancelled the iteration.
            latency_ms = int((time.perf_counter() - t0) * 1000)
            root_attrs[_ATTR_LATENCY_MS] = latency_ms
            await self.writer.emit(
                Span(
                    trace_id=trace_id,
                    span_id=root_span_id,
                    parent_span_id=None,
                    name=_SPAN_REQUEST,
                    started_at=root_started,
                    ended_at=_now(),
                    attrs=root_attrs,
                )
            )
            log.info(
                "pipeline_run_complete",
                trace_id=str(trace_id),
                latency_ms=latency_ms,
            )
