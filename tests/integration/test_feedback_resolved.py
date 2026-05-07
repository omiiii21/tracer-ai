"""Integration tests for PATCH /feedback/{trace_id}/resolved (Phase 5 FBCK-04 / D-5.15).

These exercise the full FastAPI route handler against a recording asyncpg-shaped
fake pool — the same pattern the rest of ``tests/integration/`` uses (see
``tests/integration/test_traces_api.py``). The project does not yet ship a
real-asyncpg-pool integration fixture; the live alembic reversibility drill in
``tests/integration/test_alembic_reversibility.py`` covers DB-level behavior
end-to-end. Per Plan 05-02 Task 2 <action> Step 4 — explicitly documented as
the fall-back when no real-pool fixture exists.

CI-enforced witnesses (FBCK-04 / D-5.15 / Pitfall 8 acceptance):
  IA1. Single unresolved feedback row + PATCH -> response 200, rows_updated=1,
       resolved_at non-null, executed SQL contains the expected UPDATE shape.
  IA2. PATCH twice on the same trace_id; second call's fake returns []
       (already-resolved rows excluded by ``WHERE resolved_at IS NULL``) ->
       rows_updated=0; response is 200 (idempotent; never 404).
  IA3. TWO unresolved feedback rows for the same trace_id -> single PATCH
       returns rows_updated=2 (Pitfall 8 acceptance: all-resolve-on-PATCH).
  IA4. Orphan trace_id (no feedback rows in DB) -> response 200,
       rows_updated=0; no 404 (T-03-06-07 precedent extended to PATCH).
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
    """Mirror tests/integration/test_traces_api.py — ensure config imports cleanly."""
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
        next_fetch_rows: list[_FakeRow],
    ) -> None:
        self._recorder = recorder
        self._next_fetch_rows = next_fetch_rows

    async def fetch(self, query: str, *args: Any) -> list[_FakeRow]:
        self._recorder.append((query, args))
        return list(self._next_fetch_rows)

    async def fetchrow(self, query: str, *args: Any) -> _FakeRow:
        self._recorder.append((query, args))
        return _FakeRow(id=uuid4(), created_at=datetime.now(UTC))

    async def execute(self, query: str, *args: Any) -> None:
        self._recorder.append((query, args))

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        yield


class _FakeAcquireCtx:
    def __init__(
        self, recorder: list[tuple[str, tuple[Any, ...]]], next_fetch_rows: list[_FakeRow]
    ) -> None:
        self._recorder = recorder
        self._next_fetch_rows = next_fetch_rows

    async def __aenter__(self) -> _FakeConn:
        return _FakeConn(self._recorder, self._next_fetch_rows)

    async def __aexit__(self, *exc: Any) -> None:
        return None


class _FakePool:
    """asyncpg.Pool stand-in with a steerable ``next_fetch_rows`` queue."""

    def __init__(self, next_fetch_rows: list[_FakeRow] | None = None) -> None:
        self.executed: list[tuple[str, tuple[Any, ...]]] = []
        self.next_fetch_rows = next_fetch_rows if next_fetch_rows is not None else []

    def acquire(self, timeout: float | None = None) -> _FakeAcquireCtx:
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


def test_ia1_single_row_marked_resolved_returns_rows_updated_one() -> None:
    """IA1: insert 1 unresolved feedback row, PATCH, assert rows_updated=1 + resolved_at."""
    from fastapi.testclient import TestClient

    trace_id = uuid4()
    fake_resolved_at = datetime.now(UTC)
    pool = _FakePool(
        next_fetch_rows=[_FakeRow(id=uuid4(), resolved_at=fake_resolved_at)],
    )
    app = _build_app(pool)
    client = TestClient(app)
    resp = client.patch(f"/feedback/{trace_id}/resolved")
    assert resp.status_code == 200
    body = resp.json()
    assert body["rows_updated"] == 1
    assert body["trace_id"] == str(trace_id)
    # resolved_at is the row's TIMESTAMPTZ (non-null after the UPDATE)
    assert body["resolved_at"] is not None and body["resolved_at"] != ""
    # Verify the executed SQL contains the expected UPDATE shape
    assert len(pool.executed) == 1
    sql, args = pool.executed[0]
    assert "UPDATE feedback" in sql
    assert "SET resolved_at = now()" in sql
    assert "WHERE trace_id = $1 AND resolved_at IS NULL" in sql
    assert "RETURNING id, resolved_at" in sql
    assert args == (trace_id,)


def test_ia2_idempotent_repatch_returns_rows_updated_zero() -> None:
    """IA2: PATCH the same trace_id twice; second returns rows_updated=0."""
    from fastapi.testclient import TestClient

    trace_id = uuid4()

    # First PATCH: 1 row updated.
    pool_1 = _FakePool(
        next_fetch_rows=[_FakeRow(id=uuid4(), resolved_at=datetime.now(UTC))],
    )
    app_1 = _build_app(pool_1)
    client_1 = TestClient(app_1)
    resp_1 = client_1.patch(f"/feedback/{trace_id}/resolved")
    assert resp_1.status_code == 200
    assert resp_1.json()["rows_updated"] == 1

    # Second PATCH: the WHERE resolved_at IS NULL clause now excludes the
    # row (already-resolved). Fake returns []. Response is still 200.
    pool_2 = _FakePool(next_fetch_rows=[])
    app_2 = _build_app(pool_2)
    client_2 = TestClient(app_2)
    resp_2 = client_2.patch(f"/feedback/{trace_id}/resolved")
    assert resp_2.status_code == 200
    body_2 = resp_2.json()
    assert body_2["rows_updated"] == 0
    assert body_2["trace_id"] == str(trace_id)
    # Even with rows_updated=0, the response still has resolved_at populated
    # (consistency-of-shape contract).
    assert body_2.get("resolved_at")


def test_ia3_pitfall_8_two_rows_for_same_trace_id_both_resolve() -> None:
    """IA3: TWO unresolved feedback rows for the same trace_id, single PATCH -> rows_updated=2.

    Pitfall 8 acceptance — the contract is "this issue is fixed regardless of
    who flagged it." Both feedback rows MUST be marked resolved in a single
    PATCH; the response reports rows_updated=2.
    """
    from fastapi.testclient import TestClient

    trace_id = uuid4()
    older_id = uuid4()
    newer_id = uuid4()
    older_resolved = datetime.now(UTC)
    newer_resolved = datetime.now(UTC)

    pool = _FakePool(
        next_fetch_rows=[
            _FakeRow(id=older_id, resolved_at=older_resolved),
            _FakeRow(id=newer_id, resolved_at=newer_resolved),
        ],
    )
    app = _build_app(pool)
    client = TestClient(app)
    resp = client.patch(f"/feedback/{trace_id}/resolved")
    assert resp.status_code == 200
    body = resp.json()
    assert body["rows_updated"] == 2, "Pitfall 8: both feedback rows for the trace MUST resolve"
    assert body["trace_id"] == str(trace_id)
    # Verify a single SQL statement was issued (not two separate UPDATEs).
    assert len(pool.executed) == 1
    sql, _args = pool.executed[0]
    assert "UPDATE feedback" in sql


def test_ia4_orphan_trace_id_returns_200_and_zero_rows() -> None:
    """IA4: orphan trace_id (no matching feedback rows in DB) -> 200 + rows_updated=0.

    T-03-06-07 precedent extended: orphan trace_ids are accepted on PATCH the
    same way they are on POST. No 404. The audit log still fires (PA4 covers
    that aspect).
    """
    from fastapi.testclient import TestClient

    orphan_trace_id = uuid4()
    pool = _FakePool(next_fetch_rows=[])  # empty: no feedback rows exist
    app = _build_app(pool)
    client = TestClient(app)
    resp = client.patch(f"/feedback/{orphan_trace_id}/resolved")
    assert resp.status_code == 200, "Orphan trace_id MUST NOT return 404"
    body = resp.json()
    assert body["rows_updated"] == 0
    assert body["trace_id"] == str(orphan_trace_id)
    # Confirm the parsed UUID is well-formed (FastAPI validation passed).
    UUID(body["trace_id"])
