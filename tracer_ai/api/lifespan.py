"""FastAPI lifespan -- pool open/close + CORP-04 embedding-model identity assertion.

Extracted from ``tracer_ai/api/main.py`` per PATTERNS.md s"Backend Subsystem 6"
(lines 358-373). Adds the CORP-04 startup assertion (Pitfall 7.3 mitigation):
on startup, read the latest ``chunks.embedding_model`` row and refuse to bind
the port if it doesn't match ``settings.embedding_model``.

Empty-corpus path is a structured warning (``corpus.empty``), NOT an error --
fresh checkouts must boot so the operator can hit ``/admin`` and click
re-index. Identity check failures other than mismatch (DB unreachable,
asyncpg PostgresError) downgrade to a structured warning so a transient DB
issue at boot doesn't take down the api.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg
import structlog
from fastapi import FastAPI

from tracer_ai.config import settings
from tracer_ai.errors import CorpusEmbeddingMismatchError

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

    try:
        yield
    finally:
        await app.state.db_pool.close()
        log.info("db_pool_closed")
