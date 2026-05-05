"""Retriever -- pgvector cosine via ``<=>`` against the HNSW index (RAG-01).

Phase 3 ships ONLY the pgvector adapter. MMR / cross-encoder re-rank is
reserved by config flag ``enable_reranker`` (config.py) -- Phase 5 work
(ADR 007).

The cosine ``<=>`` operator matches the existing HNSW index
``chunks_embedding_hnsw`` (alembic/versions/0001_initial.py:171-175,
``USING hnsw (embedding vector_cosine_ops)``). ``SET LOCAL hnsw.ef_search = 40``
is issued inside the retrieve transaction per RESEARCH.md s3 / s7.7 to
balance HNSW recall vs. speed for the ~5K-50K chunk Claude-docs corpus.

Score is ``1 - cosine_distance``, which yields a value in ``[0.0, 1.0]``
inclusive. HNSW distance computation can produce tiny floating-point drift
(e.g., ``-1e-7``) for vectors that are bit-equal; we clamp the resulting
score into ``[0.0, 1.0]`` so the ``RetrievedChunk.score: Field(ge=0.0, le=1.0)``
validation always succeeds.
"""

from __future__ import annotations

import json
from typing import Any

import asyncpg
import structlog

from tracer_ai.rag.types import RetrievedChunk

log = structlog.get_logger()


class PgvectorRetriever:
    """Retriever Protocol consumer -- cosine search via pgvector ``<=>``.

    Constructor:
        pool: asyncpg.Pool. Acquired with a 1.0s timeout (T-03-04-04 DoS bound).
        top_k_default: default top_k surfaced for callers that prefer a single
            ``Retriever`` instance over passing top_k every call. Phase 3
            pipeline always passes top_k explicitly, but the default is wired
            for symmetry with config.py future ``rag.top_k`` (RESEARCH.md s3).
    """

    def __init__(self, pool: asyncpg.Pool, *, top_k_default: int = 5) -> None:
        self._pool = pool
        self.top_k_default = top_k_default

    async def retrieve(self, query_embedding: list[float], top_k: int) -> list[RetrievedChunk]:
        """Return the top-K most-similar chunks to ``query_embedding``.

        Issues, inside one transaction with a 1.0s pool acquire timeout:
            1. ``SET LOCAL hnsw.ef_search = 40`` -- per-query tuning.
            2. ``SELECT ... ORDER BY embedding <=> $1::vector LIMIT $2``.

        ``query_embedding`` is rendered as a pgvector string literal
        ``[0.1,0.2,...]`` so we don't depend on the optional ``pgvector-python``
        codec being registered on the asyncpg pool. ``f"{x:.6f}"`` prevents any
        user-controlled string from interpolating into the SQL (T-03-04-01).
        """
        if top_k <= 0:
            raise ValueError(f"top_k must be > 0, got {top_k}")

        # pgvector string-literal form. ``:.6f`` is locale-independent and
        # bounds the per-row payload at ~10KB for a 1024-dim vector -- fine.
        emb_lit = "[" + ",".join(f"{x:.6f}" for x in query_embedding) + "]"

        async with self._pool.acquire(timeout=1.0) as conn, conn.transaction():
            await conn.execute("SET LOCAL hnsw.ef_search = 40")
            rows = await conn.fetch(
                "SELECT id, doc_id, doc_section, content, metadata, "
                "1 - (embedding <=> $1::vector) AS score "
                "FROM chunks "
                "ORDER BY embedding <=> $1::vector "
                "LIMIT $2",
                emb_lit,
                top_k,
            )

        results: list[RetrievedChunk] = []
        for r in rows:
            meta_raw = r["metadata"]
            # asyncpg may surface JSONB as str (no codec registered) OR dict
            # (when the application or pgvector codec adds a JSON parser);
            # accept both.
            meta: dict[str, Any] = (
                json.loads(meta_raw) if isinstance(meta_raw, str) else (meta_raw or {})
            )
            # Clamp into [0, 1] -- HNSW cosine distance can drift outside the
            # mathematical interval by 1e-7 or so on identical vectors.
            raw_score = float(r["score"])
            score = max(0.0, min(1.0, raw_score))
            results.append(
                RetrievedChunk(
                    id=r["id"],
                    doc_id=r["doc_id"],
                    doc_section=r["doc_section"],
                    content=r["content"],
                    metadata=meta,
                    score=score,
                )
            )

        log.info(
            "retrieve_ok",
            top_k=top_k,
            returned=len(results),
            score_mean=(sum(c.score for c in results) / len(results) if results else 0.0),
        )
        return results
