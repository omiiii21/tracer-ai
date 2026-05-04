"""tracer-ai FastAPI app -- entry point.

Per RESEARCH.md Topic 3 + FastAPI 0.100+ docs: uses ``lifespan=`` async
context manager (the on-event hook pattern is deprecated and removed in
modern FastAPI).

Per D-2.33: GET /healthz is the only Phase 2 endpoint. Phase 3+ adds chat,
feedback, traces, admin routes.

Per D-2.37: structured logging only -- bind a logger via the structlog
factory (see `log = ...` below); ad-hoc stdout writes are forbidden.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg
import structlog
from fastapi import FastAPI

from tracer_ai import __version__
from tracer_ai.config import settings

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """FastAPI lifespan: open asyncpg pool on startup, close on shutdown.

    Per RESEARCH.md Topic 3: convert SQLAlchemy DSN postgresql+asyncpg://...
    to asyncpg DSN postgresql://... by stripping the +asyncpg driver suffix
    (asyncpg expects the bare scheme; +asyncpg is a SQLAlchemy-only marker).

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
    try:
        yield
    finally:
        await app.state.db_pool.close()
        log.info("db_pool_closed")


app = FastAPI(
    title="tracer-ai",
    version=__version__,
    lifespan=lifespan,
)

# Routes registered after app creation per the canonical FastAPI pattern.
from tracer_ai.api import health  # noqa: E402

app.include_router(health.router)
