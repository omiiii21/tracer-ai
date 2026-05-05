"""Corpus DB writer -- UPSERT chunks + delete-stale + list-corpus query (CORP-03).

Per RESEARCH.md s2: idempotent UPSERT keyed on the deterministic
``Chunk.id`` (UUIDv5 of ``(doc_id, chunk_index)`` from
``corpus/chunker.py``); re-running ingest on unchanged docs is safe and
produces no duplicate rows.

CORP-03 contract: every UPSERT writes the metadata triple
(``embedding_model``, ``embedding_model_version``, ``indexed_at``) on
both INSERT and DO UPDATE branches -- the ``indexed_at`` recovery on
re-ingest is what makes the CORP-04 lifespan assertion's
``ORDER BY indexed_at DESC LIMIT 1`` meaningful.

T-03-04-05 mitigation: ``delete_stale`` short-circuits when
``current_doc_ids`` is empty -- an unguarded ``DELETE FROM chunks WHERE
doc_id <> ALL('{}'::text[])`` would wipe the entire corpus (the
predicate is vacuously true for every row in Postgres).

GET /admin/corpus shape (consumed by Plan 07's admin route):
``{doc_count, chunk_count, embedding_model, embedding_model_version,
last_indexed_at, docs: [{id, doc_section, source_url, chunk_count,
ingested_at}, ...]}``.
"""

from __future__ import annotations

import json
from typing import Any

import asyncpg
import structlog

from tracer_ai.corpus.types import Chunk

log = structlog.get_logger()


_UPSERT_SQL = """
INSERT INTO chunks (
    id, doc_id, chunk_index, doc_section, content,
    embedding, embedding_model, embedding_model_version,
    indexed_at, metadata
)
VALUES ($1, $2, $3, $4, $5, $6::vector, $7, $8, now(), $9::jsonb)
ON CONFLICT (id) DO UPDATE SET
    content = EXCLUDED.content,
    embedding = EXCLUDED.embedding,
    embedding_model = EXCLUDED.embedding_model,
    embedding_model_version = EXCLUDED.embedding_model_version,
    indexed_at = now(),
    metadata = EXCLUDED.metadata
"""


async def upsert_chunks(
    pool: asyncpg.Pool,
    chunks: list[Chunk],
    embeddings: list[list[float]],
    *,
    embedding_model: str,
    embedding_model_version: str,
) -> int:
    """UPSERT ``chunks`` rows with the CORP-03 metadata triple populated.

    Returns the number of rows written. Idempotent: repeated calls with the
    same ``Chunk.id`` update the row in place (re-ingest is safe).

    The length-mismatch check fires BEFORE pool acquire so a
    misconfiguration doesn't leak a Postgres connection.
    """
    if len(chunks) != len(embeddings):
        raise ValueError(
            f"chunks ({len(chunks)}) != embeddings ({len(embeddings)}); "
            "the chunker and embedder outputs must align 1:1"
        )
    if not chunks:
        return 0

    async with pool.acquire(timeout=5.0) as conn, conn.transaction():
        for c, emb in zip(chunks, embeddings, strict=True):
            # pgvector string-literal form -- avoids depending on the
            # asyncpg pgvector codec being registered.
            emb_lit = "[" + ",".join(f"{x:.6f}" for x in emb) + "]"
            await conn.execute(
                _UPSERT_SQL,
                c.id,
                c.doc_id,
                c.chunk_index,
                c.doc_section,
                c.content,
                emb_lit,
                embedding_model,
                embedding_model_version,
                json.dumps(c.metadata),
            )

    log.info(
        "chunks_upserted",
        count=len(chunks),
        embedding_model=embedding_model,
        embedding_model_version=embedding_model_version,
    )
    return len(chunks)


async def delete_stale(pool: asyncpg.Pool, current_doc_ids: set[str]) -> int:
    """Delete chunks whose ``doc_id`` is NOT in ``current_doc_ids``.

    Returns the count deleted. Used by the ingest "final pass" so doc
    removals from the source bundle propagate to the live corpus.

    SAFETY GUARD: an empty ``current_doc_ids`` set is treated as a
    no-op (returns 0 + structured warning) -- ``WHERE doc_id <> ALL('{}')``
    is vacuously true and would otherwise wipe the entire chunks table.
    The guard's behavior is enforced by ``test_delete_stale_empty_set_does_not_delete``.
    """
    if not current_doc_ids:
        log.warning(
            "delete_stale_skipped",
            reason="empty current_doc_ids set; refusing to delete entire corpus",
        )
        return 0

    async with pool.acquire(timeout=5.0) as conn:
        result = await conn.execute(
            "DELETE FROM chunks WHERE doc_id <> ALL($1::text[])",
            list(current_doc_ids),
        )

    # asyncpg.Connection.execute returns "DELETE N" for DELETE statements.
    n = 0
    if result and result.startswith("DELETE"):
        try:
            n = int(result.split()[-1])
        except (IndexError, ValueError):
            n = 0
    log.info("chunks_stale_deleted", count=n)
    return n


async def list_corpus(pool: asyncpg.Pool) -> dict[str, Any]:
    """Aggregate corpus state for ``GET /admin/corpus``.

    Returns the nested shape consumed by the admin UI's four KPI cards
    (doc_count, chunk_count, embedding_model, last_indexed_at) plus the
    per-doc table.

    Uses two queries (one aggregate row + one per-doc fetch) inside a
    single pool acquire to keep the round-trip count bounded.
    """
    async with pool.acquire(timeout=2.0) as conn:
        agg = await conn.fetchrow(
            "SELECT COUNT(DISTINCT doc_id) AS doc_count, "
            "COUNT(*) AS chunk_count, "
            "MAX(indexed_at) AS last_indexed_at, "
            "MAX(embedding_model) AS embedding_model, "
            "MAX(embedding_model_version) AS embedding_model_version "
            "FROM chunks"
        )
        docs = await conn.fetch(
            "SELECT doc_id AS id, "
            "MIN(doc_section) AS doc_section, "
            "MIN(metadata->>'source_url') AS source_url, "
            "COUNT(*) AS chunk_count, "
            "MAX(indexed_at) AS ingested_at "
            "FROM chunks GROUP BY doc_id ORDER BY doc_id"
        )

    if agg is None:
        # Defensive: COUNT() over empty table still returns a row, but if a
        # caller mocks fetchrow=None we should still produce the empty shape.
        return {
            "doc_count": 0,
            "chunk_count": 0,
            "embedding_model": "",
            "embedding_model_version": "",
            "last_indexed_at": None,
            "docs": [],
        }

    return {
        "doc_count": int(agg["doc_count"] or 0),
        "chunk_count": int(agg["chunk_count"] or 0),
        "embedding_model": agg["embedding_model"] or "",
        "embedding_model_version": agg["embedding_model_version"] or "",
        "last_indexed_at": agg["last_indexed_at"],
        "docs": [
            {
                "id": d["id"],
                "doc_section": d["doc_section"] or "",
                "source_url": d["source_url"] or "",
                "chunk_count": int(d["chunk_count"]),
                "ingested_at": d["ingested_at"],
            }
            for d in docs
        ],
    }
