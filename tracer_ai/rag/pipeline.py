"""RAG pipeline orchestrator (Phase 3 Plan 05, RAG-04; extended Plan 06 RAG-05).

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

Plan 06 extension:
  - Public ``run_stream`` now delegates to a private ``_orchestrate`` helper
    that emits all four spans and returns a 4-tuple
    ``(trace_id, chunks, llm_text_iterator, usage_holder)``. ``run_stream``
    consumes the iterator and yields the existing ``StreamEvent`` shape so
    Plan 05 callers see no contract change.
  - New public ``run_chat_stream`` method is the chat SSE-friendly variant:
    yields ``TextDelta`` events and exactly one ``ChatFinalEvent`` whose
    ``cited_chunks`` are built from the retrieved chunks and whose
    ``latency_ms`` is wall-clock from ``run_chat_stream`` entry to the moment
    the final event is yielded.
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
from tracer_ai.rag.types import (
    ChatFinalEvent,
    CitedChunk,
    Final,
    LLMResult,
    RetrievedChunk,
    StreamEvent,
    TextDelta,
)
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

    async def _orchestrate(
        self, query: str
    ) -> tuple[
        UUID,
        list[RetrievedChunk],
        AsyncIterator[str],
        dict[str, int | float],
    ]:
        """Run embed -> retrieve -> assemble; return (trace_id, chunks, text_iter, usage_holder).

        The returned ``text_iter`` is an async iterator that yields each LLM
        text-delta string and, in its ``finally`` block, populates
        ``usage_holder`` with ``{"input_tokens", "output_tokens",
        "estimated_cost_usd"}`` so the caller can read the usage figures
        AFTER fully draining the iterator. The four spans (rag.request,
        rag.retrieve, rag.prompt_assemble, rag.llm_call) are emitted here on
        success AND on mid-flight failure (per-stage try/finally per
        Pitfall 7.8 / T-03-05-04).
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

        usage_holder: dict[str, int | float] = {
            "input_tokens": 0,
            "output_tokens": 0,
            "estimated_cost_usd": 0.0,
        }

        # Stage 1 (embed): rolled into the rag.request root span latency.
        q_embeddings = await self.embedder.embed_batch([query], input_type="query")
        q_emb = q_embeddings[0]

        # Stage 2 (retrieve) -- own span emitted in finally.
        chunks: list[RetrievedChunk] = []
        retrieve_span_id = uuid4()
        retrieve_started = _now()
        retrieve_attrs: dict[str, Any] = {
            _ATTR_RETRIEVAL_TOP_K: self.top_k,
        }
        retrieve_failed = False
        try:
            chunks = await self.retriever.retrieve(q_emb, self.top_k)
        except BaseException:
            retrieve_failed = True
            raise
        finally:
            if chunks:
                scores = [c.score for c in chunks]
                retrieve_attrs[RAG_RETRIEVAL_SCORE_MEAN] = mean(scores)
                retrieve_attrs[RAG_RETRIEVAL_SCORE_MIN] = min(scores)
            else:
                retrieve_attrs[RAG_RETRIEVAL_SCORE_MEAN] = 0.0
                retrieve_attrs[RAG_RETRIEVAL_SCORE_MIN] = 0.0
            retrieve_attrs[RAG_RETRIEVED_CHUNKS] = [str(c.id) for c in chunks]
            try:
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
            finally:
                if retrieve_failed:
                    # Emit root span before propagating retrieve failure.
                    await self._emit_root(trace_id, root_span_id, root_started, root_attrs, t0)

        # Stage 3 (prompt_assemble) -- own span emitted in finally.
        prompt_span_id = uuid4()
        prompt_started = _now()
        prompt_attrs: dict[str, Any] = {}
        messages = None
        prompt_failed = False
        try:
            messages, prompt_token_count, prompt_template_id = assemble(query, chunks)
            prompt_attrs[RAG_PROMPT_TEMPLATE_ID] = prompt_template_id
            prompt_attrs[_ATTR_PROMPT_TOKEN_COUNT] = prompt_token_count
        except BaseException:
            prompt_failed = True
            raise
        finally:
            try:
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
            finally:
                if prompt_failed:
                    await self._emit_root(trace_id, root_span_id, root_started, root_attrs, t0)

        # Stage 4 (llm_call) -- yield text deltas; emit span in finally.
        llm_span_id = uuid4()
        llm_started = _now()
        llm_attrs: dict[str, Any] = {
            GEN_AI_REQUEST_MODEL: self.llm.name,
            GEN_AI_USAGE_INPUT_TOKENS: 0,
            GEN_AI_USAGE_OUTPUT_TOKENS: 0,
        }

        writer = self.writer

        # Closure capturing references; populates usage_holder + emits spans
        # in its finally block so the caller of `run_stream` /
        # `run_chat_stream` can read usage AFTER draining the iterator.
        async def _llm_text_iter() -> AsyncIterator[str]:
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
                        yield ev.text
                    elif isinstance(ev, Final):
                        final_event = ev
            finally:
                if final_event is not None:
                    result: LLMResult = final_event.result
                    llm_attrs[GEN_AI_USAGE_INPUT_TOKENS] = result.input_tokens
                    llm_attrs[GEN_AI_USAGE_OUTPUT_TOKENS] = result.output_tokens
                    usage_holder["input_tokens"] = result.input_tokens
                    usage_holder["output_tokens"] = result.output_tokens
                    usage_holder["estimated_cost_usd"] = result.estimated_cost_usd
                try:
                    await writer.emit(
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
                    # Always emit the root rag.request span -- even if a stage
                    # raised mid-flight or the consumer cancelled iteration.
                    await self._emit_root(trace_id, root_span_id, root_started, root_attrs, t0)

        return trace_id, chunks, _llm_text_iter(), usage_holder

    async def _emit_root(
        self,
        trace_id: UUID,
        root_span_id: UUID,
        root_started: datetime,
        root_attrs: dict[str, Any],
        t0: float,
    ) -> None:
        """Emit the root ``rag.request`` span with end-to-end latency."""
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

    async def run_stream(self, query: str) -> AsyncIterator[StreamEvent]:
        """Run the pipeline; yield ``TextDelta`` deltas + one ``Final``.

        Plan 05 wire-level interface preserved: callers see ``TextDelta`` and
        a final ``Final(LLMResult)`` -- the same shape ``Pipeline`` shipped in
        Plan 05. Internally delegates to ``_orchestrate`` (Plan 06 refactor).
        """
        _trace_id, _chunks, text_iter, usage_holder = await self._orchestrate(query)
        answer_parts: list[str] = []
        async for text in text_iter:
            answer_parts.append(text)
            yield TextDelta(text=text)
        # Build Final from the usage_holder populated by the iterator's finally.
        result = LLMResult(
            answer="".join(answer_parts),
            input_tokens=int(usage_holder["input_tokens"]),
            output_tokens=int(usage_holder["output_tokens"]),
            estimated_cost_usd=float(usage_holder["estimated_cost_usd"]),
        )
        yield Final(result=result)

    async def run_chat_stream(self, query: str) -> AsyncIterator[TextDelta | ChatFinalEvent]:
        """SSE-friendly variant: yield TextDelta deltas + one ChatFinalEvent.

        ``latency_ms`` is wall-clock from method entry to the moment the
        ``ChatFinalEvent`` is yielded -- this is the value the chat UI
        displays in the metadata strip and is the chat client's reading of
        end-to-end pipeline latency including the SSE generator overhead.

        ``cited_chunks`` are built from the retrieved chunks; ``doc_url`` is
        sourced from ``chunk.metadata["source_url"]`` (populated at ingest
        time per RESEARCH.md s2 line 87) and falls back to "" when missing.
        """
        t0 = time.perf_counter()
        trace_id, chunks, text_iter, usage_holder = await self._orchestrate(query)
        async for text in text_iter:
            yield TextDelta(text=text)
        cited = [
            CitedChunk(
                idx=i + 1,
                doc_url=str(c.metadata.get("source_url", "")),
                section_title=c.doc_section,
                text=c.content,
                score=c.score,
            )
            for i, c in enumerate(chunks)
        ]
        latency_ms = int((time.perf_counter() - t0) * 1000)
        yield ChatFinalEvent(
            trace_id=str(trace_id),
            cited_chunks=cited,
            latency_ms=latency_ms,
            input_tokens=int(usage_holder["input_tokens"]),
            output_tokens=int(usage_holder["output_tokens"]),
            estimated_cost_usd=float(usage_holder["estimated_cost_usd"]),
        )
