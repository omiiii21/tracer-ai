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
