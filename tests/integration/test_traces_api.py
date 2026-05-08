"""Integration tests for GET /traces + GET /traces/{trace_id} (Phase 4 EXPL-01 / EXPL-02)."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest


@pytest.fixture(autouse=True)
def _configured_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mirror the pattern from tests/test_feedback_route.py:22-29."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://t:t@db:5432/t")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("VOYAGE_API_KEY", "pa-test")
    sys.modules.pop("tracer_ai.config", None)
    sys.modules.pop("tracer_ai.api.traces", None)
    sys.modules.pop("tracer_ai.tracer.store", None)


# --- Test infrastructure ---------------------------------------------------


class _FakeConn:
    def __init__(
        self,
        trace_row: dict[str, Any] | None = None,
        span_rows: list[dict[str, Any]] | None = None,
        list_rows: list[dict[str, Any]] | None = None,
    ) -> None:
        self.trace_row = trace_row
        self.span_rows = span_rows or []
        self.list_rows = list_rows or []
        self.captured_queries: list[tuple[str, tuple[Any, ...]]] = []

    async def fetchrow(self, query: str, *args: Any) -> Any:
        self.captured_queries.append((query, args))
        return self.trace_row

    async def fetch(self, query: str, *args: Any) -> list[Any]:
        self.captured_queries.append((query, args))
        # Differentiate by SQL fragment: span fetch joins span_payloads.
        if "FROM spans s" in query:
            return self.span_rows
        return self.list_rows


class _FakeAcquireCtx:
    def __init__(self, conn: _FakeConn) -> None:
        self._conn = conn

    async def __aenter__(self) -> _FakeConn:
        return self._conn

    async def __aexit__(self, *exc: Any) -> None:
        return None


class _FakePool:
    def __init__(
        self,
        trace_row: dict[str, Any] | None = None,
        span_rows: list[dict[str, Any]] | None = None,
        list_rows: list[dict[str, Any]] | None = None,
    ) -> None:
        self.conn = _FakeConn(trace_row, span_rows, list_rows)

    def acquire(self, timeout: float | None = None) -> _FakeAcquireCtx:
        return _FakeAcquireCtx(self.conn)


def _build_app(pool: Any) -> Any:
    from fastapi import FastAPI

    from tracer_ai import __version__
    from tracer_ai.api import traces
    from tracer_ai.tracer.writer import NoopTraceWriter

    app = FastAPI(title="tracer-ai-test", version=__version__)
    app.state.db_pool = pool
    # The route handler reads app.state.trace_writer (PostgresTraceStore takes
    # (pool, writer) for the TRCR-05 write_span pass-through). Tests use the
    # NoopTraceWriter -- write_span is never exercised by the read-side tests.
    app.state.trace_writer = NoopTraceWriter()
    app.include_router(traces.router)
    return app


def _trace_id() -> UUID:
    return uuid4()


# --- Tests -----------------------------------------------------------------


def test_list_traces_returns_200_with_empty_items() -> None:
    from fastapi.testclient import TestClient

    pool = _FakePool(list_rows=[])
    app = _build_app(pool)
    client = TestClient(app)
    resp = client.get("/traces")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["next_cursor"] is None


def test_list_traces_returns_items_when_db_has_rows() -> None:
    from fastapi.testclient import TestClient

    rows = [
        {
            "id": _trace_id(),
            "started_at": datetime.now(UTC),
            "query_text": "How do I auth?",
            "latency_ms": 2810,
            "estimated_cost_usd": 0.00432,
            "faithfulness": 0.91,
            "feedback_rating": 1,
        }
    ]
    pool = _FakePool(list_rows=rows)
    app = _build_app(pool)
    client = TestClient(app)
    resp = client.get("/traces")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["query_text"] == "How do I auth?"
    assert item["latency_ms"] == 2810
    assert item["faithfulness"] == 0.91
    assert item["feedback_rating"] == 1


def test_list_traces_sql_contains_in_flight_filter() -> None:
    """Verify the WHERE latency_ms IS NOT NULL clause is in the executed SQL (T-04-04-09)."""
    from fastapi.testclient import TestClient

    pool = _FakePool(list_rows=[])
    app = _build_app(pool)
    client = TestClient(app)
    client.get("/traces")
    captured_sql = pool.conn.captured_queries[0][0]
    assert "WHERE latency_ms IS NOT NULL" in captured_sql


def test_list_traces_rejects_invalid_cursor_with_400() -> None:
    from fastapi.testclient import TestClient

    pool = _FakePool(list_rows=[])
    app = _build_app(pool)
    client = TestClient(app)
    resp = client.get("/traces?cursor=NOT_BASE64@@@")
    assert resp.status_code == 400
    body = resp.json()
    assert body["detail"]["error_code"] == "INVALID_REQUEST"


def test_list_traces_rejects_invalid_min_faithfulness_with_422() -> None:
    from fastapi.testclient import TestClient

    pool = _FakePool(list_rows=[])
    app = _build_app(pool)
    client = TestClient(app)
    resp = client.get("/traces?min_faithfulness=2.0")  # > 1.0
    assert resp.status_code == 422


def test_list_traces_rejects_invalid_feedback_value_with_422() -> None:
    from fastapi.testclient import TestClient

    pool = _FakePool(list_rows=[])
    app = _build_app(pool)
    client = TestClient(app)
    resp = client.get("/traces?feedback=invalid")
    assert resp.status_code == 422


def test_list_traces_rejects_invalid_limit_with_422() -> None:
    from fastapi.testclient import TestClient

    pool = _FakePool(list_rows=[])
    app = _build_app(pool)
    client = TestClient(app)
    resp = client.get("/traces?limit=300")  # > 200
    assert resp.status_code == 422


def test_get_trace_returns_404_when_missing() -> None:
    from fastapi.testclient import TestClient

    pool = _FakePool(trace_row=None)
    app = _build_app(pool)
    client = TestClient(app)
    tid = _trace_id()
    resp = client.get(f"/traces/{tid}")
    assert resp.status_code == 404
    body = resp.json()
    assert body["detail"]["error_code"] == "TRACE_NOT_FOUND"


def test_get_trace_returns_400_on_malformed_uuid() -> None:
    from fastapi.testclient import TestClient

    pool = _FakePool()
    app = _build_app(pool)
    client = TestClient(app)
    resp = client.get("/traces/not-a-uuid")
    assert resp.status_code == 400
    body = resp.json()
    assert body["detail"]["error_code"] == "INVALID_REQUEST"


def test_get_trace_returns_full_tree_when_present() -> None:
    from fastapi.testclient import TestClient

    tid = _trace_id()
    span_a_id = _trace_id()
    span_b_id = _trace_id()
    started = datetime.now(UTC)
    trace_row: dict[str, Any] = {
        "id": tid,
        "started_at": started,
        "query_text": "test",
        "latency_ms": 1500,
        "estimated_cost_usd": 0.001,
        "faithfulness": None,
        "feedback_rating": None,
    }
    span_rows: list[dict[str, Any]] = [
        {
            "id": span_a_id,
            "parent_span_id": None,
            "name": "rag.request",
            "started_at": started,
            "ended_at": started,
            "attrs": {"gen_ai.operation.name": "chat"},
            "payload": None,
        },
        {
            "id": span_b_id,
            "parent_span_id": span_a_id,
            "name": "rag.retrieve",
            "started_at": started,
            "ended_at": started,
            "attrs": {"gen_ai.operation.name": "retrieval"},
            "payload": {"retrieved_chunks": [{"score": 0.9}]},
        },
    ]
    pool = _FakePool(trace_row=trace_row, span_rows=span_rows)
    app = _build_app(pool)
    client = TestClient(app)
    resp = client.get(f"/traces/{tid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["trace"]["query_text"] == "test"
    assert len(body["spans"]) == 2
    assert body["spans"][0]["name"] == "rag.request"
    assert body["spans"][1]["name"] == "rag.retrieve"
    assert str(span_b_id) in body["payloads"]
    assert body["payloads"][str(span_b_id)]["payload"] == {"retrieved_chunks": [{"score": 0.9}]}


# ---------------------------------------------------------------------------
# Phase 5 Plan 05 -- max_faithfulness + sort_by (FBCK-03 / FBCK-06)
# ---------------------------------------------------------------------------


def test_list_traces_max_faithfulness_filters_to_below_threshold() -> None:
    """EX1: max_faithfulness=0.5 returns only rows with faithfulness < 0.5.

    Rows with faithfulness >= 0.5 are excluded. Rows with NULL faithfulness
    are EXCLUDED (FBCK-03 semantic: judge has not yet scored -> not
    "judge-flagged").
    """
    from fastapi.testclient import TestClient

    pool = _FakePool(list_rows=[])
    app = _build_app(pool)
    client = TestClient(app)
    resp = client.get("/traces?max_faithfulness=0.5")
    assert resp.status_code == 200
    # Verify the SQL contains the exclusion-of-null clause for max_faithfulness.
    captured_sql = pool.conn.captured_queries[0][0]
    assert "faithfulness IS NOT NULL AND faithfulness <" in captured_sql
    # Verify the bind value 0.5 was passed.
    captured_args = pool.conn.captured_queries[0][1]
    assert 0.5 in captured_args


def test_list_traces_max_faithfulness_above_one_returns_422() -> None:
    """EX2: max_faithfulness=1.5 fails validation."""
    from fastapi.testclient import TestClient

    pool = _FakePool(list_rows=[])
    app = _build_app(pool)
    client = TestClient(app)
    resp = client.get("/traces?max_faithfulness=1.5")
    assert resp.status_code == 422


def test_list_traces_max_faithfulness_negative_returns_422() -> None:
    """EX3: max_faithfulness=-0.1 fails validation."""
    from fastapi.testclient import TestClient

    pool = _FakePool(list_rows=[])
    app = _build_app(pool)
    client = TestClient(app)
    resp = client.get("/traces?max_faithfulness=-0.1")
    assert resp.status_code == 422


def test_list_traces_sort_by_faithfulness_asc_orders_lowest_first() -> None:
    """EX4: sort_by=faithfulness_asc -> ORDER BY faithfulness ASC NULLS LAST."""
    from fastapi.testclient import TestClient

    pool = _FakePool(list_rows=[])
    app = _build_app(pool)
    client = TestClient(app)
    resp = client.get("/traces?sort_by=faithfulness_asc")
    assert resp.status_code == 200
    captured_sql = pool.conn.captured_queries[0][0]
    assert "ORDER BY faithfulness ASC NULLS LAST" in captured_sql


def test_list_traces_sort_by_default_preserves_phase4_order() -> None:
    """EX5: sort_by omitted -> Phase 4 default ORDER BY started_at DESC, id DESC."""
    from fastapi.testclient import TestClient

    pool = _FakePool(list_rows=[])
    app = _build_app(pool)
    client = TestClient(app)
    resp = client.get("/traces")
    assert resp.status_code == 200
    captured_sql = pool.conn.captured_queries[0][0]
    assert "ORDER BY started_at DESC, id DESC" in captured_sql
    # Negative: ASC clause must NOT appear in default mode.
    assert "ORDER BY faithfulness ASC NULLS LAST" not in captured_sql


def test_list_traces_sort_by_invalid_value_returns_422() -> None:
    """EX6: sort_by=invalid_value fails Literal validation."""
    from fastapi.testclient import TestClient

    pool = _FakePool(list_rows=[])
    app = _build_app(pool)
    client = TestClient(app)
    resp = client.get("/traces?sort_by=invalid_value")
    assert resp.status_code == 422


def test_list_traces_sort_by_created_at_desc_explicit() -> None:
    """EX5b: sort_by=created_at_desc explicit also preserves default."""
    from fastapi.testclient import TestClient

    pool = _FakePool(list_rows=[])
    app = _build_app(pool)
    client = TestClient(app)
    resp = client.get("/traces?sort_by=created_at_desc")
    assert resp.status_code == 200
    captured_sql = pool.conn.captured_queries[0][0]
    assert "ORDER BY started_at DESC, id DESC" in captured_sql


def test_list_traces_combined_feedback_down_with_faithfulness_asc() -> None:
    """EX7: feedback=down AND sort_by=faithfulness_asc compose -- FBCK-03/06 pattern."""
    from fastapi.testclient import TestClient

    rows = [
        {
            "id": _trace_id(),
            "started_at": datetime.now(UTC),
            "query_text": "Bad answer 1",
            "latency_ms": 1500,
            "estimated_cost_usd": 0.001,
            "faithfulness": 0.21,
            "feedback_rating": -1,
        },
        {
            "id": _trace_id(),
            "started_at": datetime.now(UTC),
            "query_text": "Bad answer 2",
            "latency_ms": 1700,
            "estimated_cost_usd": 0.002,
            "faithfulness": 0.45,
            "feedback_rating": -1,
        },
    ]
    pool = _FakePool(list_rows=rows)
    app = _build_app(pool)
    client = TestClient(app)
    resp = client.get("/traces?feedback=down&sort_by=faithfulness_asc")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 2
    # Confirm SQL has BOTH the feedback predicate and the new ORDER BY.
    captured_sql = pool.conn.captured_queries[0][0]
    assert "feedback_rating" in captured_sql
    assert "ORDER BY faithfulness ASC NULLS LAST" in captured_sql


def test_list_traces_cursor_pagination_compatible_with_faithfulness_asc() -> None:
    """EX8: Cursor pagination still works with sort_by=faithfulness_asc.

    v1 limitation (documented in plan + store.py): the cursor encodes only
    (started_at, id), so pagination boundaries follow started_at not
    faithfulness even for the asc-sort variant. The cursor format stays
    compatible (no decode error). For small datasets (<1000 judge-flagged
    traces) this is acceptable.
    """
    from fastapi.testclient import TestClient

    # Seed limit+1 rows so the store generates a next_cursor.
    rows = []
    for i in range(3):
        rows.append(
            {
                "id": _trace_id(),
                "started_at": datetime.now(UTC),
                "query_text": f"q{i}",
                "latency_ms": 1500 + i,
                "estimated_cost_usd": 0.001,
                "faithfulness": 0.1 + i * 0.1,
                "feedback_rating": None,
            }
        )
    pool = _FakePool(list_rows=rows)
    app = _build_app(pool)
    client = TestClient(app)
    resp = client.get("/traces?sort_by=faithfulness_asc&limit=2")
    assert resp.status_code == 200
    body = resp.json()
    # 3 rows, limit=2 -> we get 2 items + a non-None next_cursor.
    assert len(body["items"]) == 2
    assert body["next_cursor"] is not None
    # The cursor should round-trip on a follow-up request without 400.
    pool2 = _FakePool(list_rows=[])
    app2 = _build_app(pool2)
    client2 = TestClient(app2)
    resp2 = client2.get(f"/traces?sort_by=faithfulness_asc&limit=2&cursor={body['next_cursor']}")
    assert resp2.status_code == 200
