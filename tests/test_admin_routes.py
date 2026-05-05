"""Tests for tracer_ai/api/admin.py (Phase 3 Plan 07 / ADMN-01..04).

CI-enforced witnesses:
  1. GET /admin/corpus -> 200 + CorpusState shape with chunking_config merged in.
  2. POST /admin/ingest {"source": "claude-docs"} -> 202 + ingest_job_id (UUID).
  3. Concurrent POST /admin/ingest while a job is running -> 409.
  4. GET /admin/ingest/{nonexistent-uuid} -> 404.
  5. GET /admin/ingest/{job_id} -> 200 + IngestStatus shape (status, progress, etc).
  6. PATCH /admin/chunking-config {"chunk_size": 600, "overlap": 50} -> 200 + echoed.
  7. PATCH /admin/chunking-config {"chunk_size": 50, "overlap": 0} -> 422 (out of bounds).
  8. POST /admin/ingest {"urls": ["not-a-url"]} -> 422 (URL validator from Plan 01).

Test isolation: each test resets ``tracer_ai.api.admin._jobs`` and
``_active_job_id`` via the autouse ``_reset_admin_state`` fixture so tests
don't leak job state across each other.
"""

from __future__ import annotations

import sys
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
    sys.modules.pop("tracer_ai.api.admin", None)


@pytest.fixture(autouse=True)
def _reset_admin_state() -> Any:
    """Wipe module-level admin job state before AND after each test.

    The admin module keeps in-memory ``_jobs`` and ``_active_job_id`` globals
    (per the plan's in-memory-only v1 contract). Tests must not leak job
    state across each other.
    """
    yield
    # Post-test cleanup. Import after env is set; the module may not be
    # imported yet (tests that never touch admin.py).
    try:
        from tracer_ai.api import admin

        admin._jobs.clear()
        admin._active_job_id = None
        # Reset chunking config to its defaults so PATCH tests don't leak.
        from tracer_ai.config import settings

        admin._chunking_config = {
            "chunk_size": settings.chunking_default_size,
            "overlap": settings.chunking_default_overlap,
        }
    except ImportError:
        pass


# --- Test infrastructure ---------------------------------------------------


class _FakeRow(dict[str, Any]):
    """asyncpg row-like dict supporting ``row["key"]`` access."""


class _FakeConn:
    """asyncpg.Connection stand-in returning canned aggregate + per-doc rows."""

    async def fetchrow(self, query: str, *args: Any) -> _FakeRow:
        # The list_corpus aggregate query.
        return _FakeRow(
            doc_count=2,
            chunk_count=14,
            last_indexed_at=datetime.now(UTC),
            embedding_model="voyage-code-3",
            embedding_model_version="voyage-code-3@2025-09",
        )

    async def fetch(self, query: str, *args: Any) -> list[_FakeRow]:
        # The list_corpus per-doc grouping query.
        return [
            _FakeRow(
                id="claude-docs/auth",
                doc_section="auth",
                source_url="https://docs.anthropic.com/en/api/auth",
                chunk_count=8,
                ingested_at=datetime.now(UTC),
            ),
            _FakeRow(
                id="claude-docs/messages",
                doc_section="messages",
                source_url="https://docs.anthropic.com/en/api/messages",
                chunk_count=6,
                ingested_at=datetime.now(UTC),
            ),
        ]


class _FakeAcquireCtx:
    async def __aenter__(self) -> _FakeConn:
        return _FakeConn()

    async def __aexit__(self, *exc: Any) -> None:
        return None


class _FakePool:
    """asyncpg.Pool stand-in returning canned list_corpus rows."""

    def acquire(self, timeout: float = 1.0) -> _FakeAcquireCtx:
        return _FakeAcquireCtx()


def _build_app(pool: Any | None = None) -> Any:
    """Build a minimal FastAPI app that registers the /admin router with a fake pool."""
    from fastapi import FastAPI

    from tracer_ai import __version__
    from tracer_ai.api import admin

    app = FastAPI(title="tracer-ai-test", version=__version__)
    app.state.db_pool = pool if pool is not None else _FakePool()
    app.include_router(admin.router)
    return app


# --- Tests ------------------------------------------------------------------


def test_get_corpus_returns_state_with_chunking_config() -> None:
    """GET /admin/corpus returns the CorpusState shape with chunking_config."""
    from fastapi.testclient import TestClient

    app = _build_app()
    client = TestClient(app)
    resp = client.get("/admin/corpus")
    assert resp.status_code == 200
    body = resp.json()
    # Required CorpusState keys:
    for key in (
        "doc_count",
        "chunk_count",
        "embedding_model",
        "embedding_model_version",
        "last_indexed_at",
        "docs",
        "chunking_config",
    ):
        assert key in body, f"missing key {key!r} in response {body!r}"
    assert body["doc_count"] == 2
    assert body["chunk_count"] == 14
    assert body["embedding_model"] == "voyage-code-3"
    # chunking_config is the merged value -- defaults from settings.
    assert body["chunking_config"]["chunk_size"] == 900
    assert body["chunking_config"]["overlap"] == 100
    assert isinstance(body["docs"], list)
    assert len(body["docs"]) == 2


def test_post_ingest_returns_202_with_job_id() -> None:
    """POST /admin/ingest {source: claude-docs} -> 202 + IngestResponse."""
    from fastapi.testclient import TestClient

    from tracer_ai.api import admin

    # Monkeypatch the ingest job runner so it doesn't actually try to embed.
    async def _noop_run(job_id: Any, **kwargs: Any) -> None:
        admin._jobs[job_id]["status"] = "succeeded"

    admin._run_ingest_job = _noop_run  # type: ignore[assignment]

    app = _build_app()
    client = TestClient(app)
    resp = client.post("/admin/ingest", json={"source": "claude-docs"})
    assert resp.status_code == 202
    body = resp.json()
    assert "ingest_job_id" in body
    UUID(body["ingest_job_id"])  # parses
    assert body["status"] == "queued"


def test_concurrent_ingest_returns_409() -> None:
    """Second POST /admin/ingest while one is running -> 409."""
    from fastapi.testclient import TestClient

    from tracer_ai.api import admin

    # Pre-set _active_job_id to simulate an already-running job.
    admin._active_job_id = uuid4()
    admin._jobs[admin._active_job_id] = {
        "status": "running",
        "started_at": datetime.now(UTC),
        "finished_at": None,
        "docs_processed": 1,
        "docs_total": 5,
        "chunks_written": 3,
        "progress": 0.2,
        "error": None,
    }

    app = _build_app()
    client = TestClient(app)
    resp = client.post("/admin/ingest", json={"source": "claude-docs"})
    assert resp.status_code == 409


def test_get_ingest_status_404_for_unknown_id() -> None:
    """GET /admin/ingest/{nonexistent-uuid} -> 404."""
    from fastapi.testclient import TestClient

    app = _build_app()
    client = TestClient(app)
    resp = client.get(f"/admin/ingest/{uuid4()}")
    assert resp.status_code == 404


def test_get_ingest_status_returns_state() -> None:
    """GET /admin/ingest/{job_id} returns IngestStatus with progress in [0, 1]."""
    from fastapi.testclient import TestClient

    from tracer_ai.api import admin

    job_id = uuid4()
    admin._jobs[job_id] = {
        "status": "running",
        "started_at": datetime.now(UTC),
        "finished_at": None,
        "docs_processed": 2,
        "docs_total": 4,
        "chunks_written": 6,
        "progress": 0.5,
        "error": None,
    }

    app = _build_app()
    client = TestClient(app)
    resp = client.get(f"/admin/ingest/{job_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "running"
    assert body["docs_processed"] == 2
    assert body["docs_total"] == 4
    assert body["chunks_written"] == 6
    assert 0.0 <= body["progress"] <= 1.0
    assert body["error"] is None


def test_patch_chunking_config_valid() -> None:
    """PATCH /admin/chunking-config with valid bounds -> 200 + echoed config."""
    from fastapi.testclient import TestClient

    app = _build_app()
    client = TestClient(app)
    resp = client.patch(
        "/admin/chunking-config",
        json={"chunk_size": 600, "overlap": 50},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"chunk_size": 600, "overlap": 50}


def test_patch_chunking_config_too_small() -> None:
    """PATCH /admin/chunking-config with chunk_size=50 -> 422 (ge=100)."""
    from fastapi.testclient import TestClient

    app = _build_app()
    client = TestClient(app)
    resp = client.patch(
        "/admin/chunking-config",
        json={"chunk_size": 50, "overlap": 0},
    )
    assert resp.status_code == 422


def test_post_ingest_invalid_url() -> None:
    """POST /admin/ingest {urls: [not-a-url]} -> 422 (URL validator from Plan 01)."""
    from fastapi.testclient import TestClient

    app = _build_app()
    client = TestClient(app)
    resp = client.post(
        "/admin/ingest",
        json={"urls": ["not-a-url"]},
    )
    assert resp.status_code == 422


def test_post_ingest_with_valid_urls() -> None:
    """POST /admin/ingest with valid URL list -> 202 + ingest_job_id."""
    from fastapi.testclient import TestClient

    from tracer_ai.api import admin

    async def _noop_run(job_id: Any, **kwargs: Any) -> None:
        admin._jobs[job_id]["status"] = "succeeded"

    admin._run_ingest_job = _noop_run  # type: ignore[assignment]

    app = _build_app()
    client = TestClient(app)
    resp = client.post(
        "/admin/ingest",
        json={"urls": ["https://docs.anthropic.com/en/api/auth"]},
    )
    assert resp.status_code == 202
    body = resp.json()
    UUID(body["ingest_job_id"])
    assert body["status"] == "queued"
