"""Corpus ingest orchestrator (Phase 3 Plan 05, CORP-01 / CORP-02).

Composes loader -> chunker -> embedder -> store into a single async
``run_ingest`` function consumed by both the CLI subcommand
(``tracer-ai ingest --source <dir>``) and the future admin route
(``POST /admin/ingest`` -- Phase 6).

Pipeline shape (per RESEARCH.md s2 lines 14-21):
    1. Discover paths (filesystem walk OR URL list).
    2. For each doc: load -> chunk; accumulate per-doc chunk lists.
    3. Batch all chunks (batch_size); per batch: embed -> upsert.
    4. After all batches succeed: delete_stale(current_doc_ids) so doc
       removals from the source bundle propagate to the live corpus.

T-03-05-06 mitigation -- partial-commit safety: if any embed/upsert raises,
``errors`` is populated with str(exc) AND ``delete_stale`` is SKIPPED so a
transient batch failure cannot wipe the corpus mid-ingest.

Idempotent re-runs (RESEARCH.md s2 lines 76-80): ``Chunk.id`` is a
deterministic UUIDv5 of (doc_id, chunk_index); the ON CONFLICT (id) DO
UPDATE in ``corpus/store.py`` means re-running ingest on unchanged docs
produces the same id list and updates rows in place.
"""

from __future__ import annotations

from collections.abc import Awaitable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import asyncpg
import structlog
from pydantic import BaseModel, ConfigDict, Field

from tracer_ai.corpus.chunker import Chunker
from tracer_ai.corpus.loader import discover, discover_urls, load, load_url
from tracer_ai.corpus.store import delete_stale, upsert_chunks
from tracer_ai.corpus.types import Chunk, RawDoc

log = structlog.get_logger()


class _EmbedderShape(Protocol):
    """Local structural-typing shape duck-matching ``rag.protocols.Embedder``.

    The full ``Embedder`` Protocol lives in ``tracer_ai.rag.protocols`` (layer 2);
    the import DAG forbids ``corpus`` (layer 1) -> ``rag`` (layer 2) except for
    the narrow ``corpus -> rag.embedder`` exception (D-2.27). Re-declaring the
    same shape here keeps run_ingest dependency-free at the layer boundary --
    both the rag.protocols.Embedder Protocol and any concrete adapter
    (VoyageEmbedder, STEmbedder, test fakes) structurally satisfy this shape.
    """

    name: str
    version: str
    dim: int

    def embed_batch(
        self, texts: list[str], *, input_type: str = "document"
    ) -> Awaitable[list[list[float]]]: ...


class IngestResult(BaseModel):
    """Aggregate result of one ``run_ingest`` invocation.

    Surfaced by the CLI (printed as JSON) and by ``GET /admin/ingest/{id}``
    (Phase 6) to drive admin-UI polling.
    """

    model_config = ConfigDict(extra="forbid")

    docs_processed: int = Field(ge=0)
    chunks_written: int = Field(ge=0)
    errors: list[str] = Field(default_factory=list)
    started_at: datetime
    finished_at: datetime


def _batched(items: list[Chunk], size: int) -> list[list[Chunk]]:
    """Slice ``items`` into chunks of ``size`` -- last batch may be shorter."""
    return [items[i : i + size] for i in range(0, len(items), size)]


async def run_ingest(
    source: Path | None = None,
    urls: list[str] | None = None,
    *,
    embedder: _EmbedderShape,
    chunker: Chunker,
    pool: asyncpg.Pool,
    batch_size: int = 64,
) -> IngestResult:
    """Run the full corpus ingest pipeline.

    Exactly one of ``source`` (filesystem dir of .md files) or ``urls``
    (list of HTTP(S) URLs) must be provided.

    Returns an ``IngestResult`` with counts; on partial failure ``errors``
    is populated and ``delete_stale`` is skipped (T-03-05-06).
    """
    if source is None and not urls:
        raise ValueError("must provide source or urls")
    if source is not None and urls:
        raise ValueError("provide either source OR urls, not both")

    started_at = datetime.now(UTC)
    errors: list[str] = []
    docs: list[RawDoc] = []
    all_chunks: list[Chunk] = []

    log.info(
        "ingest_started",
        source=str(source) if source else None,
        urls=len(urls) if urls else 0,
    )

    # --- Phase 1: discover + load + chunk ---
    if source is not None:
        try:
            paths = await discover(source)
            for p in paths:
                doc = await load(p)
                docs.append(doc)
                all_chunks.extend(chunker.split(doc))
        except Exception as exc:  # broad catch -- one bad file aborts ingest
            errors.append(f"load_or_chunk_failed: {exc}")
            log.warning("ingest_load_or_chunk_failed", error=str(exc))
            return IngestResult(
                docs_processed=len(docs),
                chunks_written=0,
                errors=errors,
                started_at=started_at,
                finished_at=datetime.now(UTC),
            )
    else:
        # urls path -- discover_urls is identity, load_url fetches each.
        url_list = discover_urls(urls or [])
        for url in url_list:
            try:
                doc = await load_url(url)
                docs.append(doc)
                all_chunks.extend(chunker.split(doc))
            except Exception as exc:
                errors.append(f"load_url_failed[{url}]: {exc}")
                log.warning("ingest_load_url_failed", url=url, error=str(exc))

    # --- Phase 2: batch embed + upsert ---
    chunks_written = 0
    embed_or_upsert_failed = False
    for batch in _batched(all_chunks, batch_size):
        try:
            texts = [c.content for c in batch]
            embeddings = await embedder.embed_batch(texts, input_type="document")
            n = await upsert_chunks(
                pool,
                batch,
                embeddings,
                embedding_model=embedder.name,
                embedding_model_version=embedder.version,
            )
            chunks_written += n
        except Exception as exc:
            errors.append(f"embed_or_upsert_failed: {exc}")
            log.warning("ingest_batch_failed", error=str(exc))
            embed_or_upsert_failed = True
            # T-03-05-06: do NOT continue past a failed batch -- any further
            # batches might also fail and we must skip delete_stale anyway.
            break

    # --- Phase 3: stale-row cleanup ONLY when every batch succeeded ---
    if not embed_or_upsert_failed and not errors:
        await delete_stale(pool, {d.doc_id for d in docs})

    finished_at = datetime.now(UTC)
    log.info(
        "ingest_completed",
        docs_processed=len(docs),
        chunks_written=chunks_written,
        errors=len(errors),
    )
    return IngestResult(
        docs_processed=len(docs),
        chunks_written=chunks_written,
        errors=errors,
        started_at=started_at,
        finished_at=finished_at,
    )


# Re-export to make imports tidy in the CLI / admin route.
__all__: list[str] = ["IngestResult", "run_ingest"]


# Suppress unused-import warning (Any is used by callers via re-export).
_ = Any
