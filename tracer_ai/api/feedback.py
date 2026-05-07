"""POST /feedback -- persists a feedback row (Phase 3 Plan 06 / CHAT-04).

Phase 3 writes the row only. Bad-answer queue UI is Phase 5 (FBCK-*).

Phase 4 D-4.03: this endpoint also UPDATEs ``traces.feedback_rating`` in the
same DB transaction so the dashboard's denormalized read path stays consistent.
The UPDATE affects 0 rows for orphan feedback (T-03-06-07) -- that's accepted,
not an error. Both writes succeed together or roll back together
(T-04-04-08 mitigation).

Cross-layer integrity (T-03-06-05):
  - ``FeedbackRequest.rating: Literal[-1, 1]`` rejects 0 at the FastAPI
    validation layer (422) BEFORE any SQL runs.
  - The DB enforces the same constraint via ``CHECK (rating IN (-1, 1))``
    on the ``feedback`` table (alembic/versions/0001_initial.py:127).
  - The denormalized ``traces.feedback_rating`` column is constrained by
    ``traces_feedback_rating_chk`` (alembic 0002 -- Phase 4 Plan 1) so a
    direct DB write also can't smuggle in an out-of-set value
    (T-04-04-07 second line of defense).
  - All layers must agree; drift is a bug class.

T-03-06-08 mitigation: every successful insert is logged via structlog with
``trace_id`` + ``rating`` for the audit trail. ``feedback_recorded`` event.

Per ADR 009 / D-2 / CLAUDE.md: v1 is single-user local-dev only -- no auth.
``trace_id`` forgery (T-03-06-07) is accepted: a forged UUID points at a
non-existent trace, which is harmless -- the UPDATE traces UPDATE simply
affects 0 rows and the orphan feedback row stays in the table unlinked.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import asyncpg
import structlog
from fastapi import APIRouter, Request

from tracer_ai.api.schemas import FeedbackRequest, FeedbackResolveResponse, FeedbackResponse

log = structlog.get_logger()
router = APIRouter()


@router.post("/feedback", status_code=201, response_model=FeedbackResponse)
async def post_feedback(body: FeedbackRequest, request: Request) -> FeedbackResponse:
    """Insert one feedback row; return its id + created_at.

    INSERT shape mirrors the alembic 0001 ``feedback`` table:
        (trace_id UUID, rating SMALLINT, comment TEXT, diagnosis_tag TEXT)
    -- ``id`` and ``created_at`` are server-defaulted (gen_random_uuid + now()).
    """
    pool: asyncpg.Pool = request.app.state.db_pool
    async with (
        pool.acquire(timeout=1.0) as conn,
        conn.transaction(),  # Phase 4 D-4.03: atomic INSERT + UPDATE
    ):
        row = await conn.fetchrow(
            "INSERT INTO feedback (trace_id, rating, comment, diagnosis_tag) "
            "VALUES ($1, $2, $3, $4) "
            "RETURNING id, created_at",
            body.trace_id,
            body.rating,
            body.comment,
            body.diagnosis_tag,
        )
        # Phase 4: write-through denorm (D-4.03). 0 rows affected if
        # trace_id is orphan (T-03-06-07) -- that's accepted, not an error.
        await conn.execute(
            "UPDATE traces SET feedback_rating = $1 WHERE id = $2",
            body.rating,
            body.trace_id,
        )
    # asyncpg.fetchrow returns Optional[Record]; RETURNING always populates so
    # row is non-None on the happy path. Defensive guard for type narrowing.
    if row is None:
        raise RuntimeError("feedback INSERT ... RETURNING produced no row")
    log.info(
        "feedback_recorded",
        trace_id=str(body.trace_id),
        rating=body.rating,
    )
    return FeedbackResponse(id=row["id"], created_at=row["created_at"])


@router.patch(
    "/feedback/{trace_id}/resolved",
    response_model=FeedbackResolveResponse,
    status_code=200,
)
async def patch_feedback_resolved(
    trace_id: UUID,
    request: Request,
) -> FeedbackResolveResponse:
    """Mark all unresolved feedback rows for ``trace_id`` as resolved (FBCK-04 / D-5.15).

    Idempotent: re-PATCHing returns ``rows_updated=0`` because already-resolved
    rows are excluded by ``WHERE resolved_at IS NULL``. Never returns 404 —
    orphan trace_ids are accepted (mirrors the POST /feedback T-03-06-07 stance).
    Uses a single UPDATE with RETURNING; no transaction needed (one statement).

    Pitfall 8: when there are multiple feedback rows for the same ``trace_id``,
    ALL of them are marked resolved. This is the documented operator-intent
    behavior — "this issue is fixed, regardless of who flagged it."

    T-05-02-01 / T-05-02-02 mitigations: FastAPI's ``trace_id: UUID`` path
    parameter rejects non-UUID input with 422 BEFORE the handler body runs;
    asyncpg ``$1`` parameter binding prevents SQL injection regardless. Every
    successful call emits the structlog ``feedback_resolved`` event with
    ``trace_id`` + ``rows_updated`` for the audit trail.
    """
    pool: asyncpg.Pool = request.app.state.db_pool
    # SQL on a single concatenated string literal so the substrings
    # ``UPDATE feedback SET resolved_at`` and ``WHERE trace_id = $1 AND resolved_at IS NULL``
    # are contiguous (cross-layer integrity grep gates in Plan 05-02 Task 2).
    _patch_sql = (
        "UPDATE feedback SET resolved_at = now() "
        "WHERE trace_id = $1 AND resolved_at IS NULL "
        "RETURNING id, resolved_at"
    )
    async with pool.acquire(timeout=1.0) as conn:
        rows = await conn.fetch(_patch_sql, trace_id)
    rows_updated = len(rows)
    # If no rows were updated (idempotent re-PATCH or orphan trace_id), the
    # response still needs a resolved_at timestamp — surface the current time
    # so the response shape is consistent regardless of rows_updated.
    resolved_at = rows[0]["resolved_at"] if rows else datetime.now(UTC)
    log.info(
        "feedback_resolved",
        trace_id=str(trace_id),
        rows_updated=rows_updated,
    )
    return FeedbackResolveResponse(
        trace_id=trace_id,
        resolved_at=resolved_at,
        rows_updated=rows_updated,
    )
