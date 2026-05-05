"""CORP-04: lifespan refuses to bind on embedding-model mismatch.

Three behavioral assertions:
  1. Mismatch raises -- ``settings.embedding_model`` differs from the latest
     ``chunks.embedding_model`` row -> ``CorpusEmbeddingMismatchError`` raises
     before yield, pool is closed.
  2. Empty corpus warns -- ``chunks`` is empty -> structured warning
     ``corpus.empty`` is logged, lifespan yields without error.
  3. Match passes -- chunks row matches settings -> structured info
     ``corpus.embedding_model_ok`` is logged, lifespan yields cleanly.

Mocks ``asyncpg.create_pool`` to avoid needing a live Postgres in unit tests.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from structlog.testing import capture_logs

# --- Test infrastructure ---------------------------------------------------


@pytest.fixture
def configured_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Provide the Settings env vars the lifespan needs."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://t:t@db:5432/t")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("VOYAGE_API_KEY", "pa-test")
    monkeypatch.setenv("EMBEDDING_MODEL", "voyage-code-3")
    sys.modules.pop("tracer_ai.config", None)
    sys.modules.pop("tracer_ai.api.lifespan", None)
    yield
    sys.modules.pop("tracer_ai.api.lifespan", None)


def _make_fake_pool(fetchrow_result: Any) -> Any:
    """Return a fake asyncpg pool whose ``acquire().fetchrow`` yields ``fetchrow_result``.

    Supports both ``async with pool.acquire(...) as conn:`` and ``await pool.close()``.
    Records that ``close`` was called for assertion in the mismatch path.
    """

    class _FakeConn:
        async def fetchrow(self, query: str, *args: Any) -> Any:
            return fetchrow_result

    class _FakeAcquireCtx:
        async def __aenter__(self) -> _FakeConn:
            return _FakeConn()

        async def __aexit__(self, *exc: Any) -> None:
            return None

    class _FakePool:
        def __init__(self) -> None:
            self.closed = False

        def acquire(self, timeout: float = 1.0) -> _FakeAcquireCtx:
            return _FakeAcquireCtx()

        async def close(self) -> None:
            self.closed = True

    return _FakePool()


def _patch_create_pool(monkeypatch: pytest.MonkeyPatch, fake_pool: Any) -> None:
    """Patch ``asyncpg.create_pool`` to return the supplied fake pool.

    Patches in BOTH the asyncpg module namespace AND the lifespan module's
    bound reference (lifespan.py does ``import asyncpg`` then calls
    ``asyncpg.create_pool(...)``, so monkeypatching the asyncpg module attr
    is sufficient).
    """
    import asyncpg

    async def _fake_create_pool(*args: Any, **kwargs: Any) -> Any:
        return fake_pool

    monkeypatch.setattr(asyncpg, "create_pool", _fake_create_pool)


# --- Test 1: mismatch raises ----------------------------------------------


@pytest.mark.asyncio
async def test_lifespan_raises_on_embedding_model_mismatch(
    configured_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Settings has voyage-code-3; chunks row says 'other' -> CorpusEmbeddingMismatchError."""
    fake_pool = _make_fake_pool({"embedding_model": "other", "embedding_model_version": "v1"})
    _patch_create_pool(monkeypatch, fake_pool)

    lifespan_mod = importlib.import_module("tracer_ai.api.lifespan")
    from tracer_ai.errors import CorpusEmbeddingMismatchError

    app = FastAPI()
    with pytest.raises(CorpusEmbeddingMismatchError) as exc_info:
        async with lifespan_mod.lifespan(app):
            pass  # pragma: no cover -- yield should never be reached

    msg = str(exc_info.value)
    assert "voyage-code-3" in msg
    assert "other" in msg
    # Pool must be closed BEFORE re-raising so we don't leak a connection pool.
    assert fake_pool.closed is True


# --- Test 2: empty corpus warns -------------------------------------------


@pytest.mark.asyncio
async def test_lifespan_warns_when_corpus_empty(
    configured_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No chunks row -> structured warning ``corpus.empty``; lifespan yields."""
    fake_pool = _make_fake_pool(None)
    _patch_create_pool(monkeypatch, fake_pool)

    lifespan_mod = importlib.import_module("tracer_ai.api.lifespan")

    app = FastAPI()
    yielded = False
    with capture_logs() as logs:
        async with lifespan_mod.lifespan(app):
            yielded = True

    assert yielded is True
    events = [e.get("event") for e in logs]
    assert "corpus.empty" in events, f"Expected corpus.empty warning, got: {events}"
    # Pool was opened on startup and closed on shutdown.
    assert fake_pool.closed is True


# --- Test 3: match passes -------------------------------------------------


@pytest.mark.asyncio
async def test_lifespan_passes_when_embedding_model_matches(
    configured_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Settings says voyage-code-3; chunks row says voyage-code-3 -> no error."""
    fake_pool = _make_fake_pool(
        {"embedding_model": "voyage-code-3", "embedding_model_version": "voyage-code-3@2025-09"}
    )
    _patch_create_pool(monkeypatch, fake_pool)

    lifespan_mod = importlib.import_module("tracer_ai.api.lifespan")

    app = FastAPI()
    yielded = False
    with capture_logs() as logs:
        async with lifespan_mod.lifespan(app):
            yielded = True

    assert yielded is True
    events = [e.get("event") for e in logs]
    assert (
        "corpus.embedding_model_ok" in events
    ), f"Expected corpus.embedding_model_ok info log, got: {events}"
    assert fake_pool.closed is True


# --- Test 4: identity-check failure (DB unreachable) downgrades to warning -


@pytest.mark.asyncio
async def test_lifespan_downgrades_db_error_to_warning(
    configured_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the chunks SELECT raises asyncpg.PostgresError, lifespan logs and continues.

    Rationale: the CORP-04 check is a startup safety net, not a hard
    dependency on the chunks table being reachable. A transient DB issue
    must not block the api from serving /healthz.
    """
    import asyncpg

    class _BrokenConn:
        async def fetchrow(self, query: str, *args: Any) -> Any:
            raise asyncpg.PostgresError("simulated outage")

    class _BrokenAcquireCtx:
        async def __aenter__(self) -> _BrokenConn:
            return _BrokenConn()

        async def __aexit__(self, *exc: Any) -> None:
            return None

    class _BrokenPool:
        def __init__(self) -> None:
            self.closed = False

        def acquire(self, timeout: float = 1.0) -> _BrokenAcquireCtx:
            return _BrokenAcquireCtx()

        async def close(self) -> None:
            self.closed = True

    broken_pool = _BrokenPool()

    async def _fake_create_pool(*args: Any, **kwargs: Any) -> Any:
        return broken_pool

    monkeypatch.setattr(asyncpg, "create_pool", _fake_create_pool)

    lifespan_mod = importlib.import_module("tracer_ai.api.lifespan")

    app = FastAPI()
    yielded = False
    with capture_logs() as logs:
        async with lifespan_mod.lifespan(app):
            yielded = True

    assert yielded is True
    events = [e.get("event") for e in logs]
    assert "corpus.identity_check_failed" in events
