"""GET /traces + GET /traces/{trace_id} -- trace explorer read endpoints (EXPL-01 / EXPL-02).

Both endpoints depend on `tracer_ai.tracer.store.PostgresTraceStore` (TRCR-05).
The store returns plain `dict[str, Any]` rows so the module-deps DAG (D-2.27)
stays clean; this route module is responsible for constructing the Pydantic
response models from those dicts.

T-04-04-01..09 mitigations:
  - All filter params validated by Pydantic Query (Literal["up","down"],
    ge=0.0/le=1.0 on min_faithfulness, ge=1/le=200 on limit, ge=0 on
    max_latency_ms) -- malformed inputs get 422 before any SQL runs.
  - Cursor decoding wrapped in try/except -> 400 INVALID_REQUEST envelope.
  - trace_id parsed as UUID in the route handler -> 400 INVALID_REQUEST on
    malformed; 404 TRACE_NOT_FOUND on no-match (no internal-state leak).
  - In-flight traces excluded from list (`WHERE latency_ms IS NOT NULL` in
    the store SQL); detail endpoint coalesces in-flight values to 0.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID, uuid4

import asyncpg
import structlog
from fastapi import APIRouter, HTTPException, Query, Request, status

from tracer_ai.api.schemas import (
    ErrorResponse,
    SpanInResponse,
    SpanPayloadResponse,
    TraceDetailResponse,
    TraceListItem,
    TraceListResponse,
)
from tracer_ai.tracer.store import (
    PostgresTraceStore,
    TraceListFilters,
)

log = structlog.get_logger()
router = APIRouter()


def _err(error_code: str, message: str) -> dict[str, object]:
    """Build the docs/api.md ErrorResponse envelope as a dict for HTTPException.detail."""
    return ErrorResponse(
        error_code=error_code,
        message=message,
        details=[],
        request_id=uuid4(),
    ).model_dump(mode="json")


@router.get("/traces", response_model=TraceListResponse)
async def list_traces(
    request: Request,
    query: Annotated[
        str | None,
        Query(description="ILIKE substring on traces.query_text"),
    ] = None,
    since: Annotated[datetime | None, Query()] = None,
    until: Annotated[datetime | None, Query()] = None,
    feedback: Annotated[Literal["up", "down"] | None, Query()] = None,
    min_faithfulness: Annotated[float | None, Query(ge=0.0, le=1.0)] = None,
    max_latency_ms: Annotated[int | None, Query(ge=0)] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> TraceListResponse:
    """List traces with filters + cursor pagination (docs/api.md §4)."""
    pool: asyncpg.Pool = request.app.state.db_pool
    # PostgresTraceStore takes (pool, writer) per TRCR-05 -- writer is set on
    # app.state by the lifespan (Plan 3). Required for the write_span method.
    writer = request.app.state.trace_writer
    store = PostgresTraceStore(pool, writer)
    filters = TraceListFilters(
        query=query,
        since=since,
        until=until,
        feedback=feedback,
        min_faithfulness=min_faithfulness,
        max_latency_ms=max_latency_ms,
    )
    try:
        items_dict, next_cursor = await store.list_traces(
            filters=filters, cursor=cursor, limit=limit
        )
    except ValueError as exc:
        # Bad cursor -- surface as 400 INVALID_REQUEST per docs/api.md.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_err("INVALID_REQUEST", str(exc)),
        ) from exc

    # Construct Pydantic response models from the dict rows (canonical per
    # Plan 04-04 Task 2 -- store layer cannot import api.schemas).
    typed_items = [TraceListItem(**row) for row in items_dict]
    return TraceListResponse(items=typed_items, next_cursor=next_cursor)


@router.get("/traces/{trace_id}", response_model=TraceDetailResponse)
async def get_trace(trace_id: str, request: Request) -> TraceDetailResponse:
    """Full trace tree (docs/api.md §5)."""
    try:
        trace_uuid = UUID(trace_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_err("INVALID_REQUEST", "trace_id must be a UUID"),
        ) from exc

    pool: asyncpg.Pool = request.app.state.db_pool
    writer = request.app.state.trace_writer
    store = PostgresTraceStore(pool, writer)
    result = await store.get_trace(trace_uuid)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_err("TRACE_NOT_FOUND", f"trace {trace_id} not found"),
        )
    # store.get_trace returns dict[str, Any] | None shaped as
    # {"trace": {...}, "spans": [...], "payloads": {...}}. Construct Pydantic
    # response models from the dict (canonical per Plan 04-04 Task 2).
    return TraceDetailResponse(
        trace=TraceListItem(**result["trace"]),
        spans=[SpanInResponse(**s) for s in result["spans"]],
        payloads={
            span_id: SpanPayloadResponse(**payload)
            for span_id, payload in result["payloads"].items()
        },
    )
