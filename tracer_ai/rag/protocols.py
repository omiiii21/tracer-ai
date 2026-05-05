"""RAG Protocols — Embedder, Retriever, LLM (Phase 3 contract surface).

Every Phase 3 RAG adapter consumes a Protocol shape — no concrete-class
coupling between rag/, corpus/, api/. Phase 3 Plan 01 ships ONLY these
typed contracts; downstream plans (CORP-*, RAG-*, CHAT-*, ADMN-*) build
adapters against the shapes pinned here.

Per D-2.38 (enforced by tests/test_anti_patterns.py): NO ``import voyageai``
or ``import anthropic`` in this module. SDK imports live ONLY in
``tracer_ai/rag/embedder.py`` (voyageai) and ``tracer_ai/rag/llm.py`` (anthropic).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from tracer_ai.rag.types import Message, RetrievedChunk, StreamEvent


@runtime_checkable
class Embedder(Protocol):
    """Embed text into a fixed-dimension vector.

    Adapters: ``VoyageEmbedder`` (Phase 3 RAG-* / CORP-05 — primary,
    1024-dim ``voyage-code-3``) and ``STEmbedder`` (offline-fallback;
    768-dim, NOT wired to the live ``chunks VECTOR(1024)`` table in v1).
    """

    name: str
    version: str
    dim: int

    async def embed_batch(
        self, texts: list[str], *, input_type: str = "document"
    ) -> list[list[float]]: ...


@runtime_checkable
class Retriever(Protocol):
    """Retrieve top-K chunks by vector similarity.

    Phase 3 adapter: ``PgvectorRetriever`` — cosine via pgvector ``<=>``
    against the existing ``chunks_embedding_hnsw`` index.
    """

    async def retrieve(self, query_embedding: list[float], top_k: int) -> list[RetrievedChunk]: ...


@runtime_checkable
class LLM(Protocol):
    """Stream tokens from an LLM provider.

    Phase 3 adapter: ``AnthropicLLM`` wrapping ``AsyncAnthropic.messages.stream()``.
    Yields ``TextDelta(text=...)`` events followed by exactly one
    ``Final(result=LLMResult)`` event.
    """

    name: str

    async def stream(
        self, messages: list[Message], *, max_tokens: int = 1024
    ) -> AsyncIterator[StreamEvent]: ...
