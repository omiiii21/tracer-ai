"""GET /healthz -- sole Phase 2 endpoint.

Per D-2.33: Returns {status: "ok"|"degraded", version: str, db: "ok"|"unreachable"}.
On db unreachable (asyncpg pool acquire/SELECT 1 timeout > 500ms), status_code=503
(NOT 500 -- important for orchestrators that retry-on-503-but-not-on-500).

Per docs/api.md Pydantic v2 strict-mode: the response model below uses the
strict ConfigDict policy that rejects unknown fields at validation time.
Per T-2-04-07 mitigation: this prevents silent contract drift between
docs/api.md and the wire format.
"""
import asyncio
from typing import Literal

import asyncpg
import structlog
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict

from tracer_ai import __version__

log = structlog.get_logger()
router = APIRouter()


class HealthResponse(BaseModel):
    """GET /healthz response shape (D-2.33)."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "degraded"]
    version: str
    db: Literal["ok", "unreachable"]


@router.get("/healthz", response_model=HealthResponse)
async def healthz(request: Request, response: Response) -> HealthResponse:
    """Liveness + readiness check.

    Probes the asyncpg pool with a 500ms timeout SELECT 1. On timeout or
    PostgresError, returns 503 + status="degraded" + db="unreachable".
    """
    pool: asyncpg.Pool = request.app.state.db_pool
    try:
        async with pool.acquire(timeout=0.5) as conn:
            await asyncio.wait_for(conn.fetchval("SELECT 1"), timeout=0.5)
    except (TimeoutError, asyncpg.PostgresError, OSError) as e:
        log.warning("healthz_db_probe_failed", error=str(e))
        response.status_code = 503
        return HealthResponse(status="degraded", version=__version__, db="unreachable")
    return HealthResponse(status="ok", version=__version__, db="ok")
