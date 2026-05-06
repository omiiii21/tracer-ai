"""Tests for tracer_ai/api/feedback.py (Phase 3 Plan 06 / CHAT-04).

CI-enforced witnesses:
  1. POST /feedback with valid body (rating=1) -> 201 + {id, created_at}.
  2. POST /feedback with rating=0 -> 422 (Literal[-1, 1] rejects).
  3. POST /feedback with rating=-1 + comment -> 201; FakePool records the
     comment value passed through to the INSERT.
  4. POST /feedback with extra_field -> 422 (extra="forbid" rejects).
  5. SQL contains "INSERT INTO feedback" (cross-layer integrity check).
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
    def __init__(self, recorder: list[tuple[str, tuple[Any, ...]]]) -> None:
        self._recorder = recorder

    async def fetchrow(self, query: str, *args: Any) -> _FakeRow:
        self._recorder.append((query, args))
        return _FakeRow(id=uuid4(), created_at=datetime.now(UTC))

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
    def __init__(self, recorder: list[tuple[str, tuple[Any, ...]]]) -> None:
        self._recorder = recorder

    async def __aenter__(self) -> _FakeConn:
        return _FakeConn(self._recorder)

    async def __aexit__(self, *exc: Any) -> None:
        return None


class _FakePool:
    """asyncpg.Pool stand-in that records every fetchrow call."""

    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[Any, ...]]] = []

    def acquire(self, timeout: float = 1.0) -> _FakeAcquireCtx:
        return _FakeAcquireCtx(self.executed)


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
