"""Tests for tracer_ai/api/feedback.py (Phase 3 Plan 06 / CHAT-04 + Phase 5 FBCK-04).

CI-enforced witnesses (Phase 3 / 4 — POST /feedback regression):
  1. POST /feedback with valid body (rating=1) -> 201 + {id, created_at}.
  2. POST /feedback with rating=0 -> 422 (Literal[-1, 1] rejects).
  3. POST /feedback with rating=-1 + comment -> 201; FakePool records the
     comment value passed through to the INSERT.
  4. POST /feedback with extra_field -> 422 (extra="forbid" rejects).
  5. SQL contains "INSERT INTO feedback" (cross-layer integrity check).

Phase 5 FBCK-04 — PATCH /feedback/{trace_id}/resolved:
  PA1. PATCH happy path: fake fetch returns one updated row -> 200 + rows_updated=1.
  PA2. PATCH with no matching row -> 200 + rows_updated=0 (idempotent; never 404).
  PA3. PATCH /feedback/not-a-uuid/resolved -> 422 (UUID path-param validation).
  PA4. structlog "feedback_resolved" event emitted with trace_id + rows_updated.
  PA5. FeedbackResolveResponse rejects extra fields (extra='forbid' regression).
"""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest


@pytest.fixture(autouse=True)
def _configured_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide minimal env so settings imports cleanly inside tests."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://t:t@db:5432/t")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("VOYAGE_API_KEY", "pa-test")
    sys.modules.pop("tracer_ai.config", None)
    sys.modules.pop("tracer_ai.api.feedback", None)


# --- Test infrastructure ---------------------------------------------------


class _FakeRow(dict[str, Any]):
    """asyncpg row-like dict supporting ``row["key"]`` access."""


class _FakeConn:
    def __init__(
        self,
        recorder: list[tuple[str, tuple[Any, ...]]],
        next_fetch_rows: list[_FakeRow] | None = None,
    ) -> None:
        self._recorder = recorder
        self._next_fetch_rows = next_fetch_rows if next_fetch_rows is not None else []

    async def fetchrow(self, query: str, *args: Any) -> _FakeRow:
        self._recorder.append((query, args))
        return _FakeRow(id=uuid4(), created_at=datetime.now(UTC))

    async def fetch(self, query: str, *args: Any) -> list[_FakeRow]:
        """Phase 5 FBCK-04: PATCH /feedback/{trace_id}/resolved uses
        ``conn.fetch(... RETURNING id, resolved_at)``. Returns the canned
        ``next_fetch_rows`` list so happy-path / idempotent / orphan-trace
        cases can be steered explicitly per-test.
        """
        self._recorder.append((query, args))
        return list(self._next_fetch_rows)

    async def execute(self, query: str, *args: Any) -> None:
        """Record execute calls so the Phase 4 UPDATE traces SET feedback_rating
        is verifiable from the FakePool recorder.
        """
        self._recorder.append((query, args))

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        """No-op async transaction context manager mirroring asyncpg.Connection.transaction()
        well enough for tests that don't need real rollback semantics. Phase 4 D-4.03
        wraps the feedback INSERT + UPDATE traces in a single transaction; without this
        method the existing Phase 3 tests would AttributeError once feedback.py
        adopts ``async with conn.transaction()``.
        """
        yield


class _FakeAcquireCtx:
    def __init__(
        self,
        recorder: list[tuple[str, tuple[Any, ...]]],
        next_fetch_rows: list[_FakeRow] | None = None,
    ) -> None:
        self._recorder = recorder
        self._next_fetch_rows = next_fetch_rows

    async def __aenter__(self) -> _FakeConn:
        return _FakeConn(self._recorder, self._next_fetch_rows)

    async def __aexit__(self, *exc: Any) -> None:
        return None


class _FakePool:
    """asyncpg.Pool stand-in that records every fetchrow / fetch / execute call.

    ``next_fetch_rows`` is the canned return value for ``conn.fetch(...)`` —
    used by the Phase 5 PATCH /feedback/{trace_id}/resolved tests to steer
    happy-path / idempotent / orphan-trace branches.
    """

    def __init__(self, next_fetch_rows: list[_FakeRow] | None = None) -> None:
        self.executed: list[tuple[str, tuple[Any, ...]]] = []
        self.next_fetch_rows = next_fetch_rows if next_fetch_rows is not None else []

    def acquire(self, timeout: float = 1.0) -> _FakeAcquireCtx:
        return _FakeAcquireCtx(self.executed, self.next_fetch_rows)


def _build_app(pool: Any) -> Any:
    from fastapi import FastAPI

    from tracer_ai import __version__
    from tracer_ai.api import feedback

    app = FastAPI(title="tracer-ai-test", version=__version__)
    app.state.db_pool = pool
    app.include_router(feedback.router)
    return app


# --- Tests ------------------------------------------------------------------


def test_post_feedback_writes_row_and_returns_201() -> None:
    """Happy path: rating=1, returns 201 with id (UUID) + created_at."""
    from fastapi.testclient import TestClient

    pool = _FakePool()
    app = _build_app(pool)
    client = TestClient(app)
    trace_id = str(uuid4())
    resp = client.post(
        "/feedback",
        json={"trace_id": trace_id, "rating": 1},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "id" in body
    UUID(body["id"])  # parses cleanly
    assert "created_at" in body
    # FakePool recorded the INSERT + the Phase 4 D-4.03 denorm UPDATE traces
    # (atomic in one transaction).
    assert len(pool.executed) == 2
    sql, _args = pool.executed[0]
    assert "INSERT INTO feedback" in sql
    update_sql, _update_args = pool.executed[1]
    assert "UPDATE traces SET feedback_rating" in update_sql


def test_post_feedback_rejects_rating_zero() -> None:
    """rating=0 fails Literal[-1, 1] -> 422."""
    from fastapi.testclient import TestClient

    pool = _FakePool()
    app = _build_app(pool)
    client = TestClient(app)
    resp = client.post(
        "/feedback",
        json={"trace_id": str(uuid4()), "rating": 0},
    )
    assert resp.status_code == 422
    # Validation rejected before reaching the DB.
    assert pool.executed == []


def test_post_feedback_records_comment() -> None:
    """rating=-1 + comment: FakePool sees the comment in the INSERT args."""
    from fastapi.testclient import TestClient

    pool = _FakePool()
    app = _build_app(pool)
    client = TestClient(app)
    resp = client.post(
        "/feedback",
        json={
            "trace_id": str(uuid4()),
            "rating": -1,
            "comment": "bad answer",
        },
    )
    assert resp.status_code == 201
    # INSERT feedback + UPDATE traces (Phase 4 D-4.03) -> 2 ops.
    assert len(pool.executed) == 2
    _sql, args = pool.executed[0]
    # args = (trace_id, rating, comment, diagnosis_tag); match the comment.
    assert "bad answer" in args


def test_post_feedback_rejects_extra_field() -> None:
    """extra_field violates extra='forbid' -> 422."""
    from fastapi.testclient import TestClient

    pool = _FakePool()
    app = _build_app(pool)
    client = TestClient(app)
    resp = client.post(
        "/feedback",
        json={
            "trace_id": str(uuid4()),
            "rating": 1,
            "extra_field": "x",
        },
    )
    assert resp.status_code == 422
    assert pool.executed == []


def test_post_feedback_sql_targets_feedback_table() -> None:
    """The INSERT SQL targets the feedback table (cross-layer integrity)."""
    from fastapi.testclient import TestClient

    pool = _FakePool()
    app = _build_app(pool)
    client = TestClient(app)
    resp = client.post(
        "/feedback",
        json={"trace_id": str(uuid4()), "rating": 1},
    )
    assert resp.status_code == 201
    sql, _args = pool.executed[0]
    assert "INSERT INTO feedback" in sql
    # Mirrors alembic 0001 columns: trace_id, rating, comment, diagnosis_tag.
    for col in ("trace_id", "rating", "comment", "diagnosis_tag"):
        assert col in sql


# ---------------------------------------------------------------------------
# Phase 5 FBCK-04: PATCH /feedback/{trace_id}/resolved (D-5.15)
# ---------------------------------------------------------------------------


def test_patch_feedback_resolved_happy_path_returns_rows_updated_one() -> None:
    """PA1: fake fetch returns 1 row -> 200 + rows_updated=1 + matching trace_id."""
    from fastapi.testclient import TestClient

    trace_id = uuid4()
    resolved_at = datetime.now(UTC)
    pool = _FakePool(
        next_fetch_rows=[_FakeRow(id=uuid4(), resolved_at=resolved_at)],
    )
    app = _build_app(pool)
    client = TestClient(app)
    resp = client.patch(f"/feedback/{trace_id}/resolved")
    assert resp.status_code == 200
    body = resp.json()
    assert body["rows_updated"] == 1
    assert body["trace_id"] == str(trace_id)
    # resolved_at is the timestamp from RETURNING (the fake's canned value).
    # Round-trip through JSON, so compare ISO 8601 prefix on the seconds.
    assert body["resolved_at"].startswith(resolved_at.isoformat()[:19])
    # SQL UPDATE was issued exactly once
    assert len(pool.executed) == 1
    sql, args = pool.executed[0]
    assert "UPDATE feedback" in sql
    assert "WHERE trace_id = $1 AND resolved_at IS NULL" in sql
    assert args == (trace_id,)


def test_patch_feedback_resolved_idempotent_returns_zero_rows() -> None:
    """PA2: fake fetch returns 0 rows (already-resolved or orphan) -> 200 + rows_updated=0."""
    from fastapi.testclient import TestClient

    trace_id = uuid4()
    pool = _FakePool(next_fetch_rows=[])  # no matching unresolved row
    app = _build_app(pool)
    client = TestClient(app)
    resp = client.patch(f"/feedback/{trace_id}/resolved")
    # Never 404 — orphan / already-resolved trace_ids are accepted.
    assert resp.status_code == 200
    body = resp.json()
    assert body["rows_updated"] == 0
    assert body["trace_id"] == str(trace_id)
    # resolved_at is still populated (handler falls back to datetime.now(UTC)
    # when there are no rows to draw the timestamp from).
    assert body.get("resolved_at")


def test_patch_feedback_resolved_rejects_non_uuid_path_param_with_422() -> None:
    """PA3: PATCH /feedback/not-a-uuid/resolved -> 422 (FastAPI UUID validation)."""
    from fastapi.testclient import TestClient

    pool = _FakePool()
    app = _build_app(pool)
    client = TestClient(app)
    resp = client.patch("/feedback/not-a-uuid/resolved")
    assert resp.status_code == 422
    # Validation rejected before reaching the DB.
    assert pool.executed == []


def test_patch_feedback_resolved_emits_structlog_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PA4: structlog ``feedback_resolved`` event with trace_id + rows_updated.

    Capture by monkeypatching ``feedback.log.info`` to record kwargs. T-05-02-02
    repudiation mitigation evidence — every PATCH call leaves an audit trail.
    """
    from fastapi.testclient import TestClient

    from tracer_ai.api import feedback as feedback_mod

    captured: list[tuple[str, dict[str, Any]]] = []

    def _fake_info(event: str, **kwargs: Any) -> None:
        captured.append((event, kwargs))

    monkeypatch.setattr(feedback_mod.log, "info", _fake_info)

    trace_id = uuid4()
    pool = _FakePool(
        next_fetch_rows=[_FakeRow(id=uuid4(), resolved_at=datetime.now(UTC))],
    )
    app = _build_app(pool)
    client = TestClient(app)
    resp = client.patch(f"/feedback/{trace_id}/resolved")
    assert resp.status_code == 200
    # Find the feedback_resolved event among captured log events.
    resolved_events = [(e, kw) for e, kw in captured if e == "feedback_resolved"]
    assert len(resolved_events) == 1
    _event, kwargs = resolved_events[0]
    assert kwargs.get("trace_id") == str(trace_id)
    assert kwargs.get("rows_updated") == 1


def test_feedback_resolve_response_rejects_extra_field() -> None:
    """PA5: FeedbackResolveResponse honors extra='forbid' (regression for D-2.39)."""
    from pydantic import ValidationError

    from tracer_ai.api.schemas import FeedbackResolveResponse

    with pytest.raises(ValidationError):
        FeedbackResolveResponse(
            trace_id=uuid4(),
            resolved_at=datetime.now(UTC),
            rows_updated=1,
            extra="x",  # type: ignore[call-arg]
        )
