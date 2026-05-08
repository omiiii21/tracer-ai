"""Shared Pydantic v2 models for the RAG pipeline (Phase 3 contract surface).

Every model uses ``model_config = ConfigDict(extra="forbid")`` per the strict-mode
pattern locked in ``tracer_ai/api/health.py:27-33`` and PATTERNS.md
§"Pattern: Pydantic v2 strict-mode model" (lines 703-711). Unknown fields are
rejected at validation time; this prevents silent contract drift from any
downstream Phase 3 plan.

Per D-2.38 / tests/test_anti_patterns.py: NO SDK imports in this module.
This module is consumed by tracer_ai/rag/protocols.py (Phase 3 Plan 01) and
by every downstream RAG adapter and orchestrator.
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Message(BaseModel):
    """Anthropic-style message: role + content (no system prompt — handled separately)."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant"]
    content: str


class LLMResult(BaseModel):
    """Final LLM call result with token + cost accounting.

    Used as the payload of the ``Final`` stream event from
    ``tracer_ai.rag.protocols.LLM.stream`` and as the ``usage`` field of
    ``PipelineResult``.
    """

    model_config = ConfigDict(extra="forbid")

    answer: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    estimated_cost_usd: float = Field(ge=0.0)


class RetrievedChunk(BaseModel):
    """One retrieved chunk row from the vector store.

    ``score`` is ``1 - cosine_distance`` (pgvector ``<=>``), in [0.0, 1.0]
    inclusive — matches ``CitedChunk.score`` in docs/api.md.
    """

    model_config = ConfigDict(extra="forbid")

    id: UUID
    doc_id: str
    doc_section: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    score: float = Field(ge=0.0, le=1.0)


class TextDelta(BaseModel):
    """Streaming text delta event from ``LLM.stream``.

    The ``kind`` literal is the discriminator for the ``StreamEvent`` tagged union.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["text_delta"] = "text_delta"
    text: str


class Final(BaseModel):
    """Final stream event carrying the completed ``LLMResult``.

    Yielded exactly once at the end of an ``LLM.stream`` async iterator.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["final"] = "final"
    result: LLMResult


# Tagged-union of stream events from LLM.stream — discriminated on ``kind``.
StreamEvent = TextDelta | Final


class PipelineResult(BaseModel):
    """Result of one full RAG pipeline run (embed → retrieve → prompt → llm).

    ``trace_id`` ties this result to the ``rag.request`` root span.
    """

    model_config = ConfigDict(extra="forbid")

    answer: str
    chunks: list[RetrievedChunk]
    prompt_token_count: int = Field(ge=0)
    prompt_template_id: str
    usage: LLMResult
    trace_id: UUID


# ---------------------------------------------------------------------------
# Phase 3 Plan 06 -- chat SSE wire types (CitedChunk + ChatFinalEvent).
# Appended; existing classes above are preserved verbatim per Plan 06 task 1
# behavior contract ("preserves Plan 01 classes").
# ---------------------------------------------------------------------------


class CitedChunk(BaseModel):
    """One cited chunk in a chat ``ChatFinalEvent`` payload.

    Differs from ``RetrievedChunk`` (which carries the internal ``id`` UUID and
    the raw ``metadata`` dict) by surfacing only the fields the chat client
    needs to render the citation: 1-based ``idx``, click-through ``doc_url``,
    human-readable ``section_title``, the chunk ``text``, and the
    ``score`` (1 - cosine_distance, in [0, 1]).
    """

    model_config = ConfigDict(extra="forbid")

    idx: int
    doc_url: str
    section_title: str
    text: str
    score: float


class ChatFinalEvent(BaseModel):
    """Payload of the ``event: final`` SSE frame from POST /chat.

    Differs from ``Final`` (which carries the internal ``LLMResult`` and is
    consumed by the Pipeline orchestrator) by surfacing the chat-specific
    fields: trace_id (to link to the trace explorer), cited_chunks (citation
    list), latency_ms (end-to-end pipeline latency), and the token + cost
    accounting fields. JSON-serialized as the SSE ``data`` line.

    Phase 5 EVAL-04 extension (D-5.10): four additional in-process-only fields
    carry the contextvar snapshot, the full RetrievedChunk list, the original
    query, and the assembled answer text to the SSE generator so it can call
    ``EvalDispatcher.enqueue(...)`` AFTER yielding the ``final`` frame. All
    four use ``Field(exclude=True)`` so the wire shape from
    ``model_dump(mode="json")`` is byte-unchanged from Phase 4.
    ``arbitrary_types_allowed=True`` is required because ``contextvars.Context``
    is not a Pydantic-known type (we type as ``Any`` to avoid runtime
    validation cost on the hot path).
    """

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    trace_id: str
    cited_chunks: list[CitedChunk]
    latency_ms: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float

    # === Phase 5 EVAL-04 private fields (D-5.10; never serialized) ===
    # ``Field(exclude=True)`` keeps them out of model_dump(mode="json") so the
    # SSE final frame body is unchanged on the wire. They are read in-process
    # by tracer_ai/api/chat.py to dispatch the judge task.
    #
    # ``chunks_for_judge`` is typed ``list[Any]`` (not ``list[RetrievedChunk]``)
    # because this field is in-process pass-through only -- the SSE generator
    # forwards whatever the pipeline produced to ``EvalDispatcher.enqueue``,
    # which itself declares the runtime contract via its ``chunks: list[RetrievedChunk]``
    # parameter. In production all elements are real RetrievedChunk instances;
    # the relaxed typing here avoids strict-mode rejection of duck-typed test
    # doubles (e.g. tests/perf/test_trace_write_p95.py's _FakeChunk) without
    # weakening the dispatcher's typed contract one layer down.
    ctx_snapshot: Any | None = Field(default=None, exclude=True)
    chunks_for_judge: list[Any] = Field(default_factory=list, exclude=True)
    query: str = Field(default="", exclude=True)
    answer: str = Field(default="", exclude=True)
