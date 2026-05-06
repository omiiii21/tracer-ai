"""FastAPI lifespan -- pool open/close + CORP-04 + Plan 06 pipeline construction.

Extracted from ``tracer_ai/api/main.py`` per PATTERNS.md s"Backend Subsystem 6"
(lines 358-373). Adds the CORP-04 startup assertion (Pitfall 7.3 mitigation):
on startup, read the latest ``chunks.embedding_model`` row and refuse to bind
the port if it doesn't match ``settings.embedding_model``.

Empty-corpus path is a structured warning (``corpus.empty``), NOT an error --
fresh checkouts must boot so the operator can hit ``/admin`` and click
re-index. Identity check failures other than mismatch (DB unreachable,
asyncpg PostgresError) downgrade to a structured warning so a transient DB
issue at boot doesn't take down the api.

Plan 06 extension: after the asyncpg pool opens AND the CORP-04 assertion
succeeds, this lifespan constructs and stashes a fully-wired ``Pipeline``
(VoyageEmbedder + PgvectorRetriever + AnthropicLLM + NoopTraceWriter) on
``app.state.pipeline``. The pipeline construction is wrapped in try/except so
test environments without real Voyage / Anthropic keys don't break startup;
on exception, ``app.state.pipeline = None`` and a structured warning is logged
(routes that need the pipeline must check for None at request time).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

import asyncpg
import structlog
from fastapi import FastAPI

from tracer_ai.config import settings
from tracer_ai.errors import CorpusEmbeddingMismatchError
from tracer_ai.rag.embedder import VoyageEmbedder
from tracer_ai.rag.llm import AnthropicLLM
from tracer_ai.rag.pipeline import Pipeline
from tracer_ai.rag.protocols import LLM
from tracer_ai.rag.retriever import PgvectorRetriever
from tracer_ai.tracer.exporters.postgres import PostgresTraceWriter, SpanConsumer
from tracer_ai.tracer.exporters.queue import BoundedDropOldestQueue
from tracer_ai.tracer.writer import NoopTraceWriter, TraceWriter

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """FastAPI lifespan: open asyncpg pool + run CORP-04 identity assertion + close pool.

    Per RESEARCH.md Topic 3 (Phase 2): convert SQLAlchemy DSN
    ``postgresql+asyncpg://...`` to asyncpg DSN ``postgresql://...`` by
    stripping the ``+asyncpg`` driver suffix.

    Per T-2-04-08 mitigation: the DSN is NOT logged -- only pool config is.
    """
    asyncpg_dsn = str(settings.database_url).replace("+asyncpg", "")
    pool = await asyncpg.create_pool(
        dsn=asyncpg_dsn,
        min_size=1,
        max_size=10,
        max_inactive_connection_lifetime=300.0,
    )
    app.state.db_pool = pool
    log.info("db_pool_ready", min_size=1, max_size=10)

    # CORP-04 startup assertion (RESEARCH.md s2 lines 53-71).
    # On mismatch, close the pool and re-raise -- uvicorn exits non-zero.
    try:
        async with pool.acquire(timeout=2.0) as conn:
            row = await conn.fetchrow(
                "SELECT embedding_model, embedding_model_version "
                "FROM chunks ORDER BY indexed_at DESC LIMIT 1"
            )
            if row is None:
                log.warning("corpus.empty", configured=settings.embedding_model)
            elif row["embedding_model"] != settings.embedding_model:
                raise CorpusEmbeddingMismatchError(
                    f"Config EMBEDDING_MODEL={settings.embedding_model!r} but "
                    f"chunks were written with {row['embedding_model']!r}. "
                    f"Either change EMBEDDING_MODEL or re-ingest."
                )
            else:
                log.info(
                    "corpus.embedding_model_ok",
                    model=row["embedding_model"],
                    version=row["embedding_model_version"],
                )
    except CorpusEmbeddingMismatchError:
        await pool.close()
        raise
    except (TimeoutError, asyncpg.PostgresError) as exc:
        # If the chunks table is unreachable (e.g., transient DB issue at boot),
        # downgrade to a warning so the api can still serve /healthz. The
        # health endpoint will surface degraded state via its own probe.
        log.warning("corpus.identity_check_failed", error=str(exc))

    # Plan 06: construct the Pipeline + adapters + writer and stash on app.state
    # for endpoint DI (chat, admin, feedback). Phase 4: swap NoopTraceWriter ->
    # PostgresTraceWriter; start consumer task; register drain in finally.
    consumer_task: asyncio.Task[None] | None = None
    consumer: SpanConsumer | None = None
    queue_obj: BoundedDropOldestQueue | None = None
    try:
        embedder = VoyageEmbedder()
        retriever = PgvectorRetriever(pool)
        # Concrete adapters implement ``stream`` as an async-generator function
        # (``async def`` + ``yield``) -- the structural shape matches the
        # ``LLM`` Protocol but mypy reads the Protocol-declared return type as
        # a coroutine. Cast bridges the gap at the construction boundary
        # (mirrors the cast pattern in pipeline.py at the call site).
        llm: LLM = cast(LLM, AnthropicLLM())
        # Phase 4 TRCR-06: BoundedDropOldestQueue + PostgresTraceWriter + SpanConsumer
        queue_obj = BoundedDropOldestQueue(maxsize=1000)
        writer: TraceWriter = PostgresTraceWriter(queue=queue_obj)
        consumer = SpanConsumer(queue=queue_obj, pool=pool)
        consumer_task = asyncio.create_task(consumer.run(), name="tracer-consumer")
        app.state.embedder = embedder
        app.state.retriever = retriever
        app.state.llm = llm
        app.state.trace_writer = writer
        app.state.consumer = consumer
        app.state.consumer_task = consumer_task
        app.state.queue = queue_obj
        # Plan 1 contract: Pipeline now takes db_pool kwarg for up-front INSERT INTO traces.
        app.state.pipeline = Pipeline(embedder, retriever, llm, writer, top_k=5, db_pool=pool)
        log.info(
            "pipeline_ready",
            embedder=embedder.name,
            llm=llm.name,
            writer="PostgresTraceWriter",
        )
    except Exception as exc:
        log.warning("pipeline_construction_skipped", error=str(exc))
        # Fallback: NoopTraceWriter; no consumer task started.
        app.state.pipeline = None
        app.state.embedder = None
        app.state.retriever = None
        app.state.llm = None
        app.state.trace_writer = NoopTraceWriter()
        app.state.consumer = None
        app.state.consumer_task = None
        app.state.queue = None

    try:
        yield
    finally:
        # D-4.10: 5s drain -> cancel consumer task -> close pool.
        if consumer is not None and queue_obj is not None:
            consumer.stop_accepting = True
            try:
                await asyncio.wait_for(consumer.drain(), timeout=5.0)
            except TimeoutError:
                log.warning(
                    "tracer.shutdown_drain_incomplete",
                    remaining=queue_obj.qsize(),
                )
        if consumer_task is not None:
            consumer_task.cancel()
            try:
                await consumer_task
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                log.warning("tracer.consumer_task_exit_unexpected", error=str(exc))
        await app.state.db_pool.close()
        log.info("db_pool_closed")
