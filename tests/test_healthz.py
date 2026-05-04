"""Smoke test for GET /healthz contract (D-2.33).

Uses a stub pool to exercise the route without a real Postgres. End-to-end
real-pool verification happens in Task 4 (docker compose up + curl).
"""
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tracer_ai import __version__
from tracer_ai.api import health


class _FakeConn:
    async def fetchval(self, query: str, *args: Any) -> int:
        assert query == "SELECT 1"
        return 1


class _FakeAcquireCtx:
    async def __aenter__(self) -> _FakeConn:
        return _FakeConn()

    async def __aexit__(self, *exc: Any) -> None:
        return None


class _FakePool:
    """Minimal stand-in for asyncpg.Pool -- supports `async with pool.acquire(timeout=...)`."""

    def acquire(self, timeout: float = 1.0) -> _FakeAcquireCtx:
        return _FakeAcquireCtx()


@pytest.fixture
def app_with_fake_pool() -> FastAPI:
    """Mount a tiny FastAPI app that registers the /healthz router with a fake pool."""
    app = FastAPI(title="tracer-ai-test", version=__version__)
    app.state.db_pool = _FakePool()
    app.include_router(health.router)
    return app


def test_healthz_returns_ok_with_version_and_db_status(app_with_fake_pool: FastAPI) -> None:
    """Happy path: db reachable -> 200 + ok + version + db=ok."""
    client = TestClient(app_with_fake_pool)
    resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"status": "ok", "version": __version__, "db": "ok"}


def test_healthz_returns_503_when_pool_raises(app_with_fake_pool: FastAPI) -> None:
    """Db unreachable -> 503 + degraded + db=unreachable."""
    import asyncpg

    class _BrokenAcquireCtx:
        async def __aenter__(self) -> _FakeConn:
            raise asyncpg.PostgresError("simulated outage")

        async def __aexit__(self, *exc: Any) -> None:
            return None

    class _BrokenPool:
        def acquire(self, timeout: float = 1.0) -> _BrokenAcquireCtx:
            return _BrokenAcquireCtx()

    app_with_fake_pool.state.db_pool = _BrokenPool()
    client = TestClient(app_with_fake_pool)
    resp = client.get("/healthz")
    assert resp.status_code == 503
    body = resp.json()
    assert body == {"status": "degraded", "version": __version__, "db": "unreachable"}


def test_healthz_response_rejects_extra_fields() -> None:
    """HealthResponse uses extra='forbid' per docs/api.md D-25."""
    from pydantic import ValidationError

    from tracer_ai.api.health import HealthResponse

    payload: dict[str, Any] = {
        "status": "ok",
        "version": "x",
        "db": "ok",
        "unknown_field": "value",
    }
    with pytest.raises(ValidationError):
        HealthResponse(**payload)
