"""POST/GET/PATCH /admin/* -- corpus admin API (Phase 3 Plan 07 / ADMN-01..04).

# NOTE: /admin endpoints have no authentication -- v1 is single-user local-dev only
# (ADR 009). Production hardening (auth, RBAC, audit) is reserved for v1.5+.
# Compose `db` service exposes 5432 only on the internal network; api is :8000 on localhost.
# This is documentation, not enforcement -- enough for portfolio purposes.

Endpoints (per RESEARCH.md s5 + UI-SPEC s4):
  - GET    /admin/corpus             -> CorpusState (live doc list + chunking config)
  - POST   /admin/ingest             -> 202 + IngestResponse(ingest_job_id, status)
  - GET    /admin/ingest/{job_id}    -> IngestStatus (polled every 2s by UI)
  - PATCH  /admin/chunking-config    -> ChunkingConfig (next-ingest-applies)

Concurrency model (RESEARCH.md s2 lines 79-80): single in-process
``asyncio.Lock`` + ``_active_job_id: UUID | None`` global. The lock is held
ONLY around the active-job check + assignment so the lock window is microseconds;
a concurrent POST while a job is running raises 409.

In-memory state (Phase 3 ships in-memory only; the persistent
``corpus_ingest_jobs`` table is documented as a Phase 7 polish item):
  - ``_jobs: dict[UUID, JobState]`` -- per-job state board.
  - ``_active_job_id: UUID | None`` -- the single-flight guard.
  - ``_chunking_config: dict[str, int]`` -- live chunker params (next ingest applies).
  - ``_ingest_lock: asyncio.Lock`` -- atomicity around ``_active_job_id`` checks.

Background dispatch (RESEARCH.md s2 + Plan 05 hand-off): ``run_ingest`` from
Plan 05 is invoked via FastAPI ``BackgroundTasks.add_task``; no Celery/RQ.
On exception, the JobState transitions to ``failed`` with ``str(exc)`` only
(T-03-07-09: full traceback to structlog).

URL validation (T-03-07-02): the ``urls`` body field is validated by the
Plan 01 ``IngestUrlsRequest`` schema's regex (``^https?://``); FastAPI returns
422 on a malformed URL. Server-side Pydantic re-validates regardless of any
client-side check.

Chunking config validation (T-03-07-05): the Plan 01 ``ChunkingConfigPatch``
schema enforces ``chunk_size in [100, 4000]`` and ``overlap in [0, 500]``.
The chunker constructor (Plan 02) re-validates so even a bypass via direct
module mutation cannot produce invalid Chunker instances.
"""

from __future__ import annotations

import asyncio
import traceback
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import structlog
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from tracer_ai.api.schemas import (
    ChunkingConfig,
    ChunkingConfigPatch,
    CorpusState,
    EvalConfigResponse,
    IngestRequest,
    IngestResponse,
    IngestSourceRequest,
    IngestStatus,
    IngestUrlsRequest,
    QueueHealthResponse,
)
from tracer_ai.config import settings
from tracer_ai.corpus.ingest import run_ingest
from tracer_ai.corpus.store import list_corpus

log = structlog.get_logger()
router = APIRouter(prefix="/admin")


# --- Module-level state (in-memory; per-process; restart wipes job board) ---

# JobState shape:
#   {"status": "queued"|"running"|"succeeded"|"failed",
#    "started_at": datetime | None,
#    "finished_at": datetime | None,
#    "docs_processed": int,
#    "docs_total": int | None,
#    "chunks_written": int,
#    "progress": float in [0, 1],
#    "error": str | None}
_jobs: dict[UUID, dict[str, Any]] = {}
_active_job_id: UUID | None = None
_chunking_config: dict[str, int] = {
    "chunk_size": settings.chunking_default_size,
    "overlap": settings.chunking_default_overlap,
}
_ingest_lock = asyncio.Lock()


# --- GET /admin/corpus ------------------------------------------------------


@router.get("/corpus", response_model=CorpusState)
async def get_corpus(request: Request) -> CorpusState:
    """Return the live corpus state (doc list + chunk count + chunking config).

    Reads aggregates via ``corpus.store.list_corpus(pool)`` and merges the
    current in-memory ``_chunking_config`` so the UI can render the four KPI
    cards + the chunking config form atomically (one request, one snapshot).

    Empty-corpus path: ``list_corpus`` returns zero counts + empty doc list;
    the admin UI must render on a fresh checkout (see ``corpus/store.py``).
    """
    pool: asyncpg.Pool = request.app.state.db_pool
    state = await list_corpus(pool)
    log.info("corpus_listed", doc_count=state["doc_count"], chunk_count=state["chunk_count"])
    return CorpusState(
        doc_count=state["doc_count"],
        chunk_count=state["chunk_count"],
        embedding_model=state["embedding_model"],
        embedding_model_version=state["embedding_model_version"],
        last_indexed_at=state["last_indexed_at"],
        docs=state["docs"],
        chunking_config=ChunkingConfig(**_chunking_config),
    )


# --- POST /admin/ingest -----------------------------------------------------


def _is_source_request(body: IngestRequest) -> bool:
    """Discriminator helper: true if ``body`` is an IngestSourceRequest."""
    return isinstance(body, IngestSourceRequest)


def _is_urls_request(body: IngestRequest) -> bool:
    """Discriminator helper: true if ``body`` is an IngestUrlsRequest."""
    return isinstance(body, IngestUrlsRequest)


@router.post("/ingest", status_code=202, response_model=IngestResponse)
async def post_ingest(
    body: IngestRequest,
    background_tasks: BackgroundTasks,
    request: Request,
) -> IngestResponse:
    """Dispatch a corpus ingest job in the background; return immediately.

    Single-flight guard (T-03-07-03): if a job is currently running, return
    409. Otherwise, register a new ``_jobs[job_id]`` entry, set
    ``_active_job_id``, and dispatch ``_run_ingest_job`` via FastAPI
    BackgroundTasks. The handler returns 202 + the new ``ingest_job_id``;
    the UI polls ``GET /admin/ingest/{job_id}`` until the job finishes.

    Per RESEARCH.md s2: only one ingest job runs at a time (no Celery / RQ /
    workers in v1).
    """
    global _active_job_id

    async with _ingest_lock:
        if _active_job_id is not None:
            existing = _jobs.get(_active_job_id, {}).get("status", "running")
            log.warning(
                "ingest_concurrent_blocked",
                active_job_id=str(_active_job_id),
                active_status=existing,
            )
            raise HTTPException(
                status_code=409,
                detail="Ingest already in progress",
            )

        job_id = uuid4()
        _jobs[job_id] = {
            "status": "queued",
            "started_at": None,
            "finished_at": None,
            "docs_processed": 0,
            "docs_total": None,
            "chunks_written": 0,
            "progress": 0.0,
            "error": None,
        }
        _active_job_id = job_id

    pool: asyncpg.Pool = request.app.state.db_pool
    source_value: str | None = None
    urls_value: list[str] | None = None
    if _is_source_request(body):
        # body is IngestSourceRequest -- mypy needs the explicit cast.
        source_value = body.source if isinstance(body, IngestSourceRequest) else None
    elif _is_urls_request(body):
        urls_value = body.urls if isinstance(body, IngestUrlsRequest) else None

    background_tasks.add_task(
        _run_ingest_job,
        job_id,
        source=source_value,
        urls=urls_value,
        pool=pool,
    )
    log.info(
        "ingest_dispatched",
        ingest_job_id=str(job_id),
        source=source_value,
        urls_count=len(urls_value) if urls_value else 0,
    )
    return IngestResponse(ingest_job_id=job_id, status="queued")


async def _run_ingest_job(
    job_id: UUID,
    *,
    source: str | None,
    urls: list[str] | None,
    pool: asyncpg.Pool,
) -> None:
    """Background-task entry point: build adapters and call ``run_ingest``.

    Updates ``_jobs[job_id]`` across queued -> running -> succeeded|failed.
    On any exception, ``_jobs[job_id]["status"] = "failed"`` and ``error``
    holds ``str(exc)`` only (T-03-07-09: full traceback to structlog).

    Always clears ``_active_job_id`` in finally so the next ingest can start.
    """
    global _active_job_id
    from pathlib import Path

    from tracer_ai.corpus.chunker import MarkdownHeaderChunker
    from tracer_ai.rag.embedder import VoyageEmbedder

    _jobs[job_id]["status"] = "running"
    _jobs[job_id]["started_at"] = datetime.now(UTC)

    try:
        chunker = MarkdownHeaderChunker(
            chunk_size=_chunking_config["chunk_size"],
            overlap=_chunking_config["overlap"],
        )
        embedder = VoyageEmbedder()
        result = await run_ingest(
            source=Path(source) if source == "claude-docs" else None,
            urls=urls,
            embedder=embedder,
            chunker=chunker,
            pool=pool,
        )
        _jobs[job_id]["docs_processed"] = result.docs_processed
        _jobs[job_id]["chunks_written"] = result.chunks_written
        _jobs[job_id]["finished_at"] = datetime.now(UTC)
        _jobs[job_id]["progress"] = 1.0
        if result.errors:
            _jobs[job_id]["status"] = "failed"
            _jobs[job_id]["error"] = "; ".join(result.errors)
        else:
            _jobs[job_id]["status"] = "succeeded"
        log.info(
            "ingest_completed",
            ingest_job_id=str(job_id),
            status=_jobs[job_id]["status"],
            docs_processed=result.docs_processed,
            chunks_written=result.chunks_written,
        )
    except Exception as exc:
        _jobs[job_id]["status"] = "failed"
        _jobs[job_id]["finished_at"] = datetime.now(UTC)
        _jobs[job_id]["error"] = str(exc)  # T-03-07-09: no traceback in user-visible field
        log.error(
            "ingest_job_failed",
            ingest_job_id=str(job_id),
            error=str(exc),
            traceback=traceback.format_exc(),
        )
    finally:
        _active_job_id = None


# --- GET /admin/ingest/{job_id} ---------------------------------------------


@router.get("/ingest/{job_id}", response_model=IngestStatus)
async def get_ingest_status(job_id: UUID) -> IngestStatus:
    """Return the current state of one ingest job.

    Returns 404 if ``job_id`` is unknown (process restart wipes the in-memory
    job board; UIs that polled across a restart should treat 404 as terminal).
    """
    state = _jobs.get(job_id)
    if state is None:
        raise HTTPException(status_code=404, detail="ingest job not found")
    return IngestStatus(
        ingest_job_id=job_id,
        status=state["status"],
        started_at=state["started_at"],
        finished_at=state["finished_at"],
        docs_processed=state["docs_processed"],
        docs_total=state["docs_total"],
        chunks_written=state["chunks_written"],
        progress=state["progress"],
        error=state["error"],
    )


# --- PATCH /admin/chunking-config -------------------------------------------


@router.patch("/chunking-config", response_model=ChunkingConfig)
async def patch_chunking_config(body: ChunkingConfigPatch) -> ChunkingConfig:
    """Update the in-memory chunking config; new values apply on next ingest.

    Per RESEARCH.md s5: ``chunk_size`` 100..4000 and ``overlap`` 0..500 are
    enforced by the Plan 01 schema (FastAPI returns 422 on out-of-bounds).
    The chunker constructor (Plan 02) re-validates so even a direct module
    mutation cannot produce an invalid Chunker (T-03-07-05 defense in depth).
    """
    _chunking_config["chunk_size"] = body.chunk_size
    _chunking_config["overlap"] = body.overlap
    log.info(
        "chunking_config_updated",
        chunk_size=body.chunk_size,
        overlap=body.overlap,
    )
    return ChunkingConfig(chunk_size=body.chunk_size, overlap=body.overlap)


# --- GET /admin/eval-config (Phase 5 Plan 03 / D-5.13) ----------------------


@router.get("/eval-config", response_model=EvalConfigResponse)
async def get_eval_config() -> EvalConfigResponse:
    """Return the runtime eval threshold + judge model + prompt version (D-5.13).

    Single source of truth for the bad-answer-queue threshold; the frontend
    (Plan 05-07) reads this at mount so the UI filter and the operator-set
    env var stay aligned. Read-only; no DB access; pure ``settings`` +
    module-constant read.

    The ``PROMPT_VERSION`` import is LOCAL inside the handler body so this
    route does not force ``tracer_ai.eval.llm_judge`` to be import-clean at
    ``admin.py`` load time. If ``eval/`` import fails (e.g., missing
    ANTHROPIC_API_KEY in dev), the rest of ``/admin/*`` still mounts. Pattern
    documented in PATTERNS.md `tracer_ai/api/admin.py` analog.
    """
    # Local imports keep eval/ optional at admin.py load time.
    from tracer_ai.eval.llm_judge import PROMPT_VERSION

    return EvalConfigResponse(
        threshold=settings.bad_answer_faithfulness_threshold,
        judge_prompt_version=PROMPT_VERSION,
        judge_model=settings.llm_judge_model,
        calibration_date=settings.calibration_date,
    )


# --- GET /admin/queue-health (Phase 5 Plan 03 / FBCK-07) --------------------


@router.get("/queue-health", response_model=QueueHealthResponse)
async def get_queue_health(request: Request) -> QueueHealthResponse:
    """Return live counts for the dashboard 5th KpiCard (FBCK-07).

    ``queue_size``: unresolved thumbs-down feedback rows. Uses Plan 05-02's
    partial index ``feedback_unresolved_idx ON feedback (trace_id) WHERE
    resolved_at IS NULL`` for an O(log N) count.

    ``resolved_this_week``: feedback rows resolved in the last 7 days
    (``resolved_at >= NOW() - INTERVAL '7 days'``). The natural fallback to a
    sequential scan is acceptable for the dominant query pattern (operator
    KPI poll, frontend caches with staleTime: 30_000).

    Single-user local; no auth in v1 (T-05-03-04 / T-05-03-06 accept).
    Pure read-only against the feedback table.
    """
    pool: asyncpg.Pool = request.app.state.db_pool
    async with pool.acquire(timeout=2.0) as conn:
        queue_size = await conn.fetchval(
            "SELECT COUNT(*) FROM feedback " "WHERE rating = -1 AND resolved_at IS NULL"
        )
        resolved_this_week = await conn.fetchval(
            "SELECT COUNT(*) FROM feedback " "WHERE resolved_at >= NOW() - INTERVAL '7 days'"
        )
    log.info(
        "queue_health_reported",
        queue_size=int(queue_size or 0),
        resolved_this_week=int(resolved_this_week or 0),
    )
    return QueueHealthResponse(
        queue_size=int(queue_size or 0),
        resolved_this_week=int(resolved_this_week or 0),
    )
