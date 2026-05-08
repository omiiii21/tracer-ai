"""TraceStore Protocol + PostgresTraceStore (Phase 4 TRCR-05 / EXPL-01 / EXPL-02).

Read-side persistence abstraction for traces. The api/traces.py route module
depends on this Protocol; swapping in a different store (e.g., a fixture-based
test store) is one constructor arg.

CRITICAL — module-deps DAG (D-2.27): this module MUST NOT import the API
layer (``tracer_ai/api/*``); doing so would fail import_cycle_guard. All
return shapes are ``dict[str, Any]`` (or
``tuple[list[dict[str, Any]], str | None]``); the route handler in
``api/traces.py`` is responsible for constructing the Pydantic response
models from these dicts. Adding any ``api.schemas`` import to this file is
forbidden.

Per D-4.19: cursor pagination is keyset on ``(started_at, id)`` — base64 JSON
payload.
Per D-4.20: filters compose into a single SQL against ``traces`` (denormalized
scalar columns added by alembic 0002).
Per D-4.21: ``get_trace`` does two queries: (1) traces row, (2) spans LEFT
JOIN span_payloads.

Per TRCR-05 (REQUIREMENTS.md): the Protocol exposes ``get_trace``,
``list_traces``, AND ``write_span``. ``write_span`` on the read-store is a
thin pass-through to an injected ``TraceWriter`` (TRCR-06 owns the durable
write path). This satisfies TRCR-05's literal interface while preserving the
TraceWriter-first separation of concerns.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol, runtime_checkable
from uuid import UUID

import asyncpg
import structlog

# Module-deps DAG (D-2.27): tracer_ai/tracer/ sits BELOW tracer_ai/api/ in the
# layering DAG, so no API-layer imports are allowed here. The route handler
# in api/traces.py constructs Pydantic models from the dict[str, Any] rows we
# return — this file stays Protocol-only on the read path.
from tracer_ai.tracer.writer import Span, TraceWriter

log = structlog.get_logger()


@dataclass(frozen=True)
class TraceListFilters:
    """Filter parameters for ``list_traces`` (docs/api.md §4 TraceListQuery).

    Phase 5 Plan 05 extensions:
      - ``max_faithfulness`` (FBCK-03): when set, rows with
        ``faithfulness IS NOT NULL AND faithfulness < max_faithfulness`` are
        included. Rows with NULL faithfulness are EXCLUDED (judge has not
        yet scored -> not "judge-flagged").
      - ``sort_by`` (FBCK-06): ``"created_at_desc"`` (default; preserves
        Phase 4 ordering) or ``"faithfulness_asc"`` (lowest-first; powers
        the bad-answer queue Judge-flagged tab).
    """

    query: str | None = None
    since: datetime | None = None
    until: datetime | None = None
    feedback: Literal["up", "down"] | None = None
    min_faithfulness: float | None = None
    max_latency_ms: int | None = None
    max_faithfulness: float | None = None
    sort_by: Literal["created_at_desc", "faithfulness_asc"] = "created_at_desc"


def encode_cursor(started_at: datetime, trace_id: UUID) -> str:
    """Encode keyset cursor as base64(JSON) (D-4.19)."""
    payload = {"started_at": started_at.isoformat(), "id": str(trace_id)}
    return base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    """Decode base64(JSON) cursor. Raises ``ValueError`` on malformed input.

    The route handler converts ``ValueError`` to HTTP 400 INVALID_REQUEST
    (T-04-04-02 mitigation).
    """
    try:
        raw = base64.b64decode(cursor.encode("ascii"), validate=True).decode("utf-8")
        payload = json.loads(raw)
        started_at = datetime.fromisoformat(payload["started_at"])
        trace_id = UUID(payload["id"])
    except (ValueError, json.JSONDecodeError, KeyError, TypeError, UnicodeDecodeError) as exc:
        raise ValueError(f"invalid cursor: {exc}") from exc
    return started_at, trace_id


@runtime_checkable
class TraceStore(Protocol):
    """Persistence abstraction for traces (TRCR-05).

    REQUIREMENTS.md TRCR-05 lists three methods: ``get_trace``,
    ``list_traces``, ``write_span``. The read-side methods return
    ``dict[str, Any]`` shapes (NOT Pydantic models) so ``tracer_ai/tracer/``
    stays free of ``tracer_ai/api/`` imports (D-2.27). The route handler in
    ``api/traces.py`` constructs ``TraceListItem`` / ``TraceDetailResponse``
    from these dicts. ``write_span`` is a thin wrapper over ``TraceWriter.emit``
    for TRCR-05 symmetry — the actual durable write path is owned by
    ``TraceWriter`` (TRCR-06).
    """

    async def get_trace(self, trace_id: UUID) -> dict[str, Any] | None: ...

    async def list_traces(
        self,
        *,
        filters: TraceListFilters,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[dict[str, Any]], str | None]: ...

    async def write_span(self, span: Span) -> None: ...


class PostgresTraceStore:
    """asyncpg-backed ``TraceStore`` implementation.

    Constructor takes both the pool (for read queries) and a ``TraceWriter``
    (for the ``write_span`` pass-through that satisfies TRCR-05). Returns
    ``dict[str, Any]`` rows so the ``api/traces.py`` route handler can
    construct Pydantic response models — keeps this module free of API-layer
    imports (D-2.27).
    """

    def __init__(self, pool: asyncpg.Pool, writer: TraceWriter) -> None:
        self._pool = pool
        self._writer = writer

    async def write_span(self, span: Span) -> None:
        """TRCR-05 write-side method: delegate to the injected ``TraceWriter``.

        This is a thin wrapper that exists so ``PostgresTraceStore`` satisfies
        the full ``TraceStore`` Protocol (``get_trace`` + ``list_traces`` +
        ``write_span``). The durable write path lives in ``TraceWriter``
        (Plan 3, ``PostgresTraceWriter``).
        """
        await self._writer.emit(span)

    async def get_trace(self, trace_id: UUID) -> dict[str, Any] | None:
        """Two-query fetch (D-4.21): trace row + spans LEFT JOIN payloads.

        Returns a dict shaped as::

            {
              "trace": {trace_id, started_at, query_text, latency_ms,
                        estimated_cost_usd, faithfulness, feedback_rating},
              "spans": [
                {span_id, parent_span_id, name, started_at, ended_at, attrs},
                ...
              ],
              "payloads": {span_id_str: {"payload": {...}}, ...},
            }

        Returns ``None`` when the ``trace_id`` is not found. The
        ``api/traces.py`` handler wraps this dict into
        ``TraceDetailResponse(**...)``.
        """
        async with self._pool.acquire() as conn:
            trace_row = await conn.fetchrow(
                "SELECT id, started_at, query_text, latency_ms, estimated_cost_usd, "
                "faithfulness, feedback_rating "
                "FROM traces WHERE id = $1::uuid",
                str(trace_id),
            )
            if trace_row is None:
                return None
            span_rows = await conn.fetch(
                "SELECT s.id, s.parent_span_id, s.name, s.started_at, s.ended_at, "
                "s.attrs, sp.payload "
                "FROM spans s "
                "LEFT JOIN span_payloads sp ON sp.span_id = s.id "
                "WHERE s.trace_id = $1::uuid "
                "ORDER BY s.started_at ASC",
                str(trace_id),
            )

        spans: list[dict[str, Any]] = []
        payloads: dict[str, dict[str, Any]] = {}
        for row in span_rows:
            attrs = row["attrs"]
            if isinstance(attrs, str):
                attrs = json.loads(attrs)
            spans.append(
                {
                    "span_id": row["id"],
                    "parent_span_id": row["parent_span_id"],
                    "name": row["name"],
                    "started_at": row["started_at"],
                    "ended_at": row["ended_at"],
                    "attrs": attrs or {},
                }
            )
            payload = row["payload"]
            if payload is not None:
                if isinstance(payload, str):
                    payload = json.loads(payload)
                payloads[str(row["id"])] = {"payload": payload}

        # Coalesce in-flight nulls for detail view (avoid 404 on in-flight trace).
        # The route handler will validate & construct TraceListItem /
        # TraceDetailResponse; latency_ms / estimated_cost_usd are required at
        # the API layer per docs/api.md §4.
        trace_dict: dict[str, Any] = {
            "trace_id": trace_row["id"],
            "started_at": trace_row["started_at"],
            "query_text": trace_row["query_text"],
            "latency_ms": trace_row["latency_ms"] if trace_row["latency_ms"] is not None else 0,
            "estimated_cost_usd": (
                trace_row["estimated_cost_usd"]
                if trace_row["estimated_cost_usd"] is not None
                else 0.0
            ),
            "faithfulness": trace_row["faithfulness"],
            "feedback_rating": trace_row["feedback_rating"],
        }
        return {"trace": trace_dict, "spans": spans, "payloads": payloads}

    async def list_traces(
        self,
        *,
        filters: TraceListFilters,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Cursor-paginated list with filter composition (D-4.19/D-4.20).

        Returns ``(items, next_cursor)`` where ``items`` is a list of
        ``dict[str, Any]`` rows shaped to match ``TraceListItem`` fields. The
        route handler in ``api/traces.py`` constructs
        ``TraceListItem(**row)`` from each dict.
        """
        # Decode cursor if present (raises ValueError on malformed; caller
        # handles 400).
        cursor_started_at: datetime | None = None
        cursor_id: UUID | None = None
        if cursor is not None:
            cursor_started_at, cursor_id = decode_cursor(cursor)

        # Map "up" / "down" -> 1 / -1 to match the DB CHECK constraint values.
        feedback_value: int | None = None
        if filters.feedback == "up":
            feedback_value = 1
        elif filters.feedback == "down":
            feedback_value = -1

        # Build parameterized SQL. We always pass all 10 binds in fixed order.
        # The "$N IS NULL" guard turns each filter on/off without dynamic SQL —
        # avoids the SQL-injection class of bugs (T-04-04-01) and keeps the
        # plan cache stable across filter combinations (Pitfall 5).
        #
        # Phase 5 Plan 05 (FBCK-03): the max_faithfulness predicate is
        # "faithfulness IS NOT NULL AND faithfulness < $9" so rows without a
        # judge score (NULL faithfulness) are EXCLUDED when the filter is on.
        # This is the documented FBCK-03 semantic.
        #
        # Phase 5 Plan 05 (FBCK-06): ORDER BY is composed by Python conditional
        # from a hard-coded set (filters.sort_by is Literal-validated by
        # FastAPI at the route boundary). SQL injection via the new param is
        # impossible.
        base_select = (
            "SELECT id, started_at, query_text, latency_ms, estimated_cost_usd, "
            "faithfulness, feedback_rating "
            "FROM traces "
            "WHERE latency_ms IS NOT NULL "
            "  AND ($1::text IS NULL OR query_text ILIKE '%' || $1 || '%') "
            "  AND ($2::timestamptz IS NULL OR started_at >= $2) "
            "  AND ($3::timestamptz IS NULL OR started_at <= $3) "
            "  AND ($4::int IS NULL OR feedback_rating = $4) "
            "  AND ($5::real IS NULL OR faithfulness >= $5) "
            "  AND ($6::int IS NULL OR latency_ms <= $6) "
            "  AND ($7::timestamptz IS NULL OR (started_at, id) < ($7::timestamptz, $8::uuid)) "
            "  AND ($9::float IS NULL OR "
            "(faithfulness IS NOT NULL AND faithfulness < $9::float)) "
        )
        # Cursor-pagination v1 limitation (documented in plan + threat
        # T-05-05-06): the cursor encodes only (started_at, id). For
        # sort_by=faithfulness_asc, page boundaries follow started_at not
        # faithfulness. Acceptable for small datasets (<1000 judge-flagged
        # traces); Phase 6 may add a faithfulness-aware cursor variant.
        if filters.sort_by == "faithfulness_asc":
            order_by = "ORDER BY faithfulness ASC NULLS LAST, started_at DESC, id DESC"
        else:  # default created_at_desc
            order_by = "ORDER BY started_at DESC, id DESC"
        sql = base_select + order_by + " LIMIT $10::int"
        params: tuple[Any, ...] = (
            filters.query,
            filters.since,
            filters.until,
            feedback_value,
            filters.min_faithfulness,
            filters.max_latency_ms,
            cursor_started_at,
            str(cursor_id) if cursor_id is not None else None,
            filters.max_faithfulness,
            limit + 1,  # fetch one extra to determine if next page exists
        )

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)

        items: list[dict[str, Any]] = []
        for row in rows[:limit]:
            items.append(
                {
                    "trace_id": row["id"],
                    "started_at": row["started_at"],
                    "query_text": row["query_text"],
                    "latency_ms": row["latency_ms"],
                    "estimated_cost_usd": (
                        row["estimated_cost_usd"] if row["estimated_cost_usd"] is not None else 0.0
                    ),
                    "faithfulness": row["faithfulness"],
                    "feedback_rating": row["feedback_rating"],
                }
            )

        next_cursor: str | None = None
        if len(rows) > limit:
            last = items[-1]
            # last is a dict, not a Pydantic model; index by string key.
            next_cursor = encode_cursor(last["started_at"], last["trace_id"])

        return items, next_cursor
