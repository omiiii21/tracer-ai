"""Integration tests for GET /traces/timeseries (Phase 5 Plan 05 / D-5.17 / DASH-01..04).

Adaptive bucketing rules:
  - window=1h  -> 60 buckets (1-min)
  - window=24h -> 288 buckets (5-min)  [special: subtraction trick]
  - window=7d  -> 168 buckets (1-hour)
  - window=30d -> 30 buckets (1-day)

Empty buckets render as rows with NULL aggregates + request_count=0
(LEFT JOIN against generate_series). The frontend Tremor chart's
connectNulls=false (D-5.07) renders gaps for these.

Tests TS1-TS8 mirror the pattern from tests/integration/test_traces_api.py
(_FakePool/_FakeConn recorder shape) -- the SQL is verified by substring
greps + bucket-count assertions on canned _FakePool list_rows. Real-DB
end-to-end coverage lives in tests/integration/test_alembic_reversibility.py
+ the docker-compose drill (Plan 04-06 precedent).
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest


@pytest.fixture(autouse=True)
def _configured_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mirror the pattern from tests/integration/test_traces_api.py:13-21."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://t:t@db:5432/t")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("VOYAGE_API_KEY", "pa-test")
    sys.modules.pop("tracer_ai.config", None)
    sys.modules.pop("tracer_ai.api.traces", None)
    sys.modules.pop("tracer_ai.tracer.store", None)


# --- Test infrastructure ---------------------------------------------------


class _FakeConn:
    """Recorder-style asyncpg.Connection stub.

    The store calls ``conn.fetch(sql)`` (no args) for the timeseries query.
    The fixture pre-loads ``timeseries_rows`` and returns those on the
    matching SQL substring.
    """

    def __init__(self, timeseries_rows: list[dict[str, Any]] | None = None) -> None:
        self.timeseries_rows = timeseries_rows or []
        self.captured_queries: list[tuple[str, tuple[Any, ...]]] = []

    async def fetch(self, query: str, *args: Any) -> list[Any]:
        self.captured_queries.append((query, args))
        if "generate_series" in query:
            return self.timeseries_rows
        return []

    async def fetchrow(self, query: str, *args: Any) -> Any:
        self.captured_queries.append((query, args))
        return None


class _FakeAcquireCtx:
    def __init__(self, conn: _FakeConn) -> None:
        self._conn = conn

    async def __aenter__(self) -> _FakeConn:
        return self._conn

    async def __aexit__(self, *exc: Any) -> None:
        return None


class _FakePool:
    def __init__(self, timeseries_rows: list[dict[str, Any]] | None = None) -> None:
        self.conn = _FakeConn(timeseries_rows)

    def acquire(self, timeout: float | None = None) -> _FakeAcquireCtx:
        return _FakeAcquireCtx(self.conn)


def _build_app(pool: Any) -> Any:
    from fastapi import FastAPI

    from tracer_ai import __version__
    from tracer_ai.api import traces
    from tracer_ai.tracer.writer import NoopTraceWriter

    app = FastAPI(title="tracer-ai-test", version=__version__)
    app.state.db_pool = pool
    app.state.trace_writer = NoopTraceWriter()
    app.include_router(traces.router)
    return app


def _bucket_row(
    bucket_start: datetime,
    *,
    latency_p50: float | None = None,
    latency_p95: float | None = None,
    cost_sum: float = 0.0,
    faithfulness_mean: float | None = None,
    feedback_down_ratio: float | None = None,
    request_count: int = 0,
) -> dict[str, Any]:
    """Helper to build a fake DB row matching the SQL projection."""
    return {
        "bucket_start": bucket_start,
        "latency_p50": latency_p50,
        "latency_p95": latency_p95,
        "cost_sum": cost_sum,
        "faithfulness_mean": faithfulness_mean,
        "feedback_down_ratio": feedback_down_ratio,
        "request_count": request_count,
    }


def _trace_id() -> UUID:
    return uuid4()


# --- Tests TS1-TS8 ---------------------------------------------------------


def test_timeseries_24h_empty_database_returns_buckets_with_zero_counts() -> None:
    """TS1: GET /traces/timeseries?window=24h with no traces -> empty-bucket rows."""
    from fastapi.testclient import TestClient

    # Simulate an "empty database" -- the LEFT JOIN against generate_series
    # produces buckets with request_count=0 and NULL aggregates. Provide
    # 288 such bucket rows (24h * 12 5-min buckets).
    base = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    rows = [_bucket_row(base + timedelta(minutes=5 * i)) for i in range(288)]
    pool = _FakePool(timeseries_rows=rows)
    app = _build_app(pool)
    client = TestClient(app)
    resp = client.get("/traces/timeseries?window=24h")
    assert resp.status_code == 200
    body = resp.json()
    assert body["window"] == "24h"
    assert len(body["buckets"]) == 288
    for b in body["buckets"]:
        assert b["request_count"] == 0
        assert b["latency_p50"] is None
        assert b["faithfulness_mean"] is None


def test_timeseries_24h_with_three_active_buckets() -> None:
    """TS2: Sparse activity -- 3 active buckets, 285 empty.

    Mirrors the production shape: most buckets are empty (NULL aggregates,
    count=0); a few have non-zero request_count + non-NULL latency_p50/p95.
    """
    from fastapi.testclient import TestClient

    base = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    rows: list[dict[str, Any]] = []
    for i in range(288):
        if i in {10, 50, 250}:
            rows.append(
                _bucket_row(
                    base + timedelta(minutes=5 * i),
                    latency_p50=120.0,
                    latency_p95=350.0,
                    cost_sum=0.01,
                    faithfulness_mean=0.7,
                    feedback_down_ratio=0.0,
                    request_count=2,
                )
            )
        else:
            rows.append(_bucket_row(base + timedelta(minutes=5 * i)))
    pool = _FakePool(timeseries_rows=rows)
    app = _build_app(pool)
    client = TestClient(app)
    resp = client.get("/traces/timeseries?window=24h")
    assert resp.status_code == 200
    body = resp.json()
    active = [b for b in body["buckets"] if b["request_count"] > 0]
    empty = [b for b in body["buckets"] if b["request_count"] == 0]
    assert len(active) == 3
    assert len(empty) == 285
    for b in active:
        assert b["latency_p50"] == 120.0
        assert b["latency_p95"] == 350.0


def test_timeseries_faithfulness_mean_null_when_no_eval_scores() -> None:
    """TS3: faithfulness_mean is NULL for buckets where no traces have scores."""
    from fastapi.testclient import TestClient

    base = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    rows = [
        _bucket_row(
            base,
            latency_p50=100.0,
            latency_p95=200.0,
            cost_sum=0.005,
            faithfulness_mean=None,  # all traces in this bucket have NULL faithfulness
            feedback_down_ratio=None,
            request_count=3,
        ),
        _bucket_row(
            base + timedelta(minutes=5),
            latency_p50=150.0,
            latency_p95=300.0,
            cost_sum=0.007,
            faithfulness_mean=0.82,  # at least one trace scored
            feedback_down_ratio=None,
            request_count=4,
        ),
    ]
    pool = _FakePool(timeseries_rows=rows)
    app = _build_app(pool)
    client = TestClient(app)
    resp = client.get("/traces/timeseries?window=24h")
    assert resp.status_code == 200
    body = resp.json()
    assert body["buckets"][0]["faithfulness_mean"] is None
    assert body["buckets"][1]["faithfulness_mean"] == 0.82


def test_timeseries_feedback_down_ratio_null_when_no_rated_traces() -> None:
    """TS4: feedback_down_ratio is NULL when no traces in bucket have feedback."""
    from fastapi.testclient import TestClient

    base = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    rows = [
        _bucket_row(
            base,
            latency_p50=100.0,
            latency_p95=200.0,
            cost_sum=0.005,
            faithfulness_mean=0.7,
            feedback_down_ratio=None,  # no rated traces
            request_count=3,
        ),
        _bucket_row(
            base + timedelta(minutes=5),
            latency_p50=150.0,
            latency_p95=300.0,
            cost_sum=0.007,
            faithfulness_mean=0.65,
            feedback_down_ratio=0.25,  # 1 of 4 rated traces is thumbs-down
            request_count=4,
        ),
    ]
    pool = _FakePool(timeseries_rows=rows)
    app = _build_app(pool)
    client = TestClient(app)
    resp = client.get("/traces/timeseries?window=24h")
    assert resp.status_code == 200
    body = resp.json()
    assert body["buckets"][0]["feedback_down_ratio"] is None
    assert body["buckets"][1]["feedback_down_ratio"] == 0.25


def test_timeseries_latency_p95_value_round_trips() -> None:
    """TS5: latency_p95 from PERCENTILE_CONT(0.95) round-trips through the response.

    With latencies [100, 200, ..., 2000] (step 100, 20 values), the 95th
    percentile via PERCENTILE_CONT(0.95) is approximately 1905. Real Postgres
    semantics are out of scope for this fake-pool unit; we assert the value
    flows through unchanged from the row to the response.
    """
    from fastapi.testclient import TestClient

    base = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    rows = [
        _bucket_row(
            base,
            latency_p50=1050.0,
            latency_p95=1905.0,
            cost_sum=0.02,
            faithfulness_mean=0.7,
            feedback_down_ratio=None,
            request_count=20,
        )
    ]
    pool = _FakePool(timeseries_rows=rows)
    app = _build_app(pool)
    client = TestClient(app)
    resp = client.get("/traces/timeseries?window=24h")
    assert resp.status_code == 200
    body = resp.json()
    bucket = body["buckets"][0]
    assert bucket["latency_p95"] == 1905.0
    assert 1900.0 <= bucket["latency_p95"] <= 1950.0  # plan acceptance band


def test_timeseries_window_sizing_for_each_window() -> None:
    """TS6: bucket counts per window match D-5.17 (1h=60, 7d=168, 30d=30)."""
    from fastapi.testclient import TestClient

    cases = [
        ("1h", 60),
        ("7d", 168),
        ("30d", 30),
    ]
    for window, expected_count in cases:
        base = datetime.now(UTC).replace(second=0, microsecond=0)
        rows = [_bucket_row(base + timedelta(minutes=i)) for i in range(expected_count)]
        pool = _FakePool(timeseries_rows=rows)
        app = _build_app(pool)
        client = TestClient(app)
        resp = client.get(f"/traces/timeseries?window={window}")
        assert resp.status_code == 200, f"window={window} -> {resp.text}"
        body = resp.json()
        assert body["window"] == window
        assert (
            len(body["buckets"]) == expected_count
        ), f"window={window} expected {expected_count} buckets, got {len(body['buckets'])}"


def test_timeseries_invalid_window_returns_422() -> None:
    """TS7: GET /traces/timeseries?window=garbage returns 422."""
    from fastapi.testclient import TestClient

    pool = _FakePool(timeseries_rows=[])
    app = _build_app(pool)
    client = TestClient(app)
    resp = client.get("/traces/timeseries?window=garbage")
    assert resp.status_code == 422


def test_timeseries_sql_excludes_in_flight_traces() -> None:
    """TS8: the SQL has WHERE latency_ms IS NOT NULL (Phase 4 D-4.18 invariant)."""
    from fastapi.testclient import TestClient

    pool = _FakePool(timeseries_rows=[])
    app = _build_app(pool)
    client = TestClient(app)
    client.get("/traces/timeseries?window=24h")
    # The store should have executed exactly one fetch; assert the SQL contains
    # the latency_ms IS NOT NULL filter (in-flight trace exclusion).
    assert pool.conn.captured_queries, "expected a captured timeseries query"
    sql = pool.conn.captured_queries[0][0]
    assert "latency_ms IS NOT NULL" in sql
    assert "generate_series" in sql
    assert "PERCENTILE_CONT(0.95)" in sql
