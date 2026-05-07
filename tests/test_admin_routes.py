"""Tests for tracer_ai/api/admin.py (Phase 3 Plan 07 / ADMN-01..04 + Phase 5 Plan 03).

CI-enforced witnesses:
  1. GET /admin/corpus -> 200 + CorpusState shape with chunking_config merged in.
  2. POST /admin/ingest {"source": "claude-docs"} -> 202 + ingest_job_id (UUID).
  3. Concurrent POST /admin/ingest while a job is running -> 409.
  4. GET /admin/ingest/{nonexistent-uuid} -> 404.
  5. GET /admin/ingest/{job_id} -> 200 + IngestStatus shape (status, progress, etc).
  6. PATCH /admin/chunking-config {"chunk_size": 600, "overlap": 50} -> 200 + echoed.
  7. PATCH /admin/chunking-config {"chunk_size": 50, "overlap": 0} -> 422 (out of bounds).
  8. POST /admin/ingest {"urls": ["not-a-url"]} -> 422 (URL validator from Plan 01).

Phase 5 Plan 03 (D-5.13 + FBCK-07):
  EA1. GET /admin/eval-config -> 200 + default Settings
       (threshold=0.6, judge_model, PROMPT_VERSION).
  EA2. monkeypatch settings.bad_answer_faithfulness_threshold=0.55 -> 0.55.
  EA3. monkeypatch settings.calibration_date=tz-aware -> ISO + offset.
  EA4. EvalConfigResponse rejects extra fields (extra='forbid').
  EA5. EvalConfigResponse rejects threshold > 1.0 (Field(ge=0.0, le=1.0)).
  QH1. GET /admin/queue-health empty -> {queue_size: 0, resolved_this_week: 0}.
  QH2. 3 unresolved thumbs-down rows -> queue_size=3.
  QH3. 2 resolved-in-7d + 1 unresolved -> queue_size=1, resolved_this_week=2.
  QH4. Resolved >7 days ago NOT counted in resolved_this_week.
  QH5. QueueHealthResponse rejects extra fields + negative integers.

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
    """asyncpg.Connection stand-in returning canned aggregate + per-doc rows.

    Supports per-instance ``fetchval_queue`` so Phase 5 Plan 03 /admin/queue-health
    tests can inject (queue_size, resolved_this_week) values for the two
    sequential ``conn.fetchval(...)`` calls.
    """

    def __init__(self, fetchval_queue: list[Any] | None = None) -> None:
        # FIFO of canned ``fetchval`` returns; each call pops the head.
        self._fetchval_queue: list[Any] = list(fetchval_queue or [])
        # Recorder so tests can assert SQL substrings.
        self.fetchval_calls: list[tuple[str, tuple[Any, ...]]] = []

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

    async def fetchval(self, query: str, *args: Any) -> Any:
        """Pop next canned value; record the SQL for substring assertions.

        Phase 5 Plan 03: GET /admin/queue-health issues two sequential
        ``conn.fetchval(...)`` calls (queue_size then resolved_this_week).
        Tests pre-load ``_fetchval_queue`` with the two ints.
        """
        self.fetchval_calls.append((query, args))
        if not self._fetchval_queue:
            return 0
        return self._fetchval_queue.pop(0)


class _FakeAcquireCtx:
    def __init__(self, fetchval_queue: list[Any] | None = None) -> None:
        self._fetchval_queue = fetchval_queue
        self.last_conn: _FakeConn | None = None

    async def __aenter__(self) -> _FakeConn:
        self.last_conn = _FakeConn(fetchval_queue=self._fetchval_queue)
        return self.last_conn

    async def __aexit__(self, *exc: Any) -> None:
        return None


class _FakePool:
    """asyncpg.Pool stand-in returning canned list_corpus rows.

    ``fetchval_queue`` (Phase 5 Plan 03): canned values popped in order by
    ``_FakeConn.fetchval`` so /admin/queue-health tests can drive the two
    sequential COUNT queries deterministically.
    """

    def __init__(self, fetchval_queue: list[Any] | None = None) -> None:
        self._fetchval_queue = fetchval_queue
        self.last_acquire: _FakeAcquireCtx | None = None

    def acquire(self, timeout: float = 1.0) -> _FakeAcquireCtx:
        self.last_acquire = _FakeAcquireCtx(fetchval_queue=self._fetchval_queue)
        return self.last_acquire


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


# ---------------------------------------------------------------------------
# Phase 5 Plan 03 — GET /admin/eval-config (D-5.13) tests EA1..EA5
# ---------------------------------------------------------------------------


def test_ea1_get_eval_config_returns_default_settings() -> None:
    """EA1: GET /admin/eval-config returns default Settings + PROMPT_VERSION.

    With Plan 05-01's PROMPT_VERSION importable, the endpoint returns:
      {threshold: 0.6, judge_prompt_version: 'v1.ragas-faithfulness-relevance',
       judge_model: 'claude-haiku-4-5-20251001', calibration_date: null}.
    """
    from fastapi.testclient import TestClient

    app = _build_app()
    client = TestClient(app)
    resp = client.get("/admin/eval-config")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["threshold"] == 0.6
    assert body["judge_prompt_version"] == "v1.ragas-faithfulness-relevance"
    assert body["judge_model"] == "claude-haiku-4-5-20251001"
    assert body["calibration_date"] is None
    # extra='forbid' on response model -- shape must be exactly these 4 keys.
    assert set(body.keys()) == {
        "threshold",
        "judge_prompt_version",
        "judge_model",
        "calibration_date",
    }


def test_ea2_get_eval_config_reflects_threshold_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """EA2: monkeypatch settings.bad_answer_faithfulness_threshold=0.55 -> echoed.

    NOTE: ``_build_app()`` resolves ``from tracer_ai.api import admin`` via the
    cached ``tracer_ai.api`` package attribute, so the ``admin`` module that
    handles the request is the FIRST-IMPORTED one. Patching a freshly-imported
    ``tracer_ai.config.settings`` would miss admin's binding. Instead, patch
    the LIVE admin module's ``settings`` reference (which the route handler
    closes over).
    """
    from fastapi.testclient import TestClient

    # Force admin module load + patch the SAME settings instance the handler uses.
    app = _build_app()
    from tracer_ai.api import admin

    monkeypatch.setattr(admin.settings, "bad_answer_faithfulness_threshold", 0.55)

    client = TestClient(app)
    resp = client.get("/admin/eval-config")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["threshold"] == 0.55


def test_ea3_get_eval_config_serializes_calibration_date_iso8601(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """EA3: tz-aware calibration_date renders as ISO-8601 with offset.

    NOTE on patching: see EA2 docstring -- patch the LIVE admin module's
    ``settings`` reference (the one the handler closes over) so the override
    survives the cached ``tracer_ai.api`` package attribute resolution.
    """
    from fastapi.testclient import TestClient

    app = _build_app()
    from tracer_ai.api import admin

    cal = datetime(2026, 5, 15, 12, 0, 0, tzinfo=UTC)
    monkeypatch.setattr(admin.settings, "calibration_date", cal)

    client = TestClient(app)
    resp = client.get("/admin/eval-config")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Pydantic v2 default ISO-8601 datetime serialization: '2026-05-15T12:00:00Z'
    # OR '2026-05-15T12:00:00+00:00' depending on tz suffix style. Accept either.
    raw = body["calibration_date"]
    assert raw is not None
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    assert parsed == cal


def test_ea4_eval_config_response_rejects_extra_fields() -> None:
    """EA4: EvalConfigResponse rejects extra fields (extra='forbid')."""
    from pydantic import ValidationError

    from tracer_ai.api.schemas import EvalConfigResponse

    with pytest.raises(ValidationError):
        EvalConfigResponse(
            threshold=0.6,
            judge_prompt_version="v1",
            judge_model="m",
            extra="x",  # type: ignore[call-arg]
        )


def test_ea5_eval_config_response_rejects_threshold_above_one() -> None:
    """EA5: EvalConfigResponse rejects threshold > 1.0 (Field(ge=0.0, le=1.0))."""
    from pydantic import ValidationError

    from tracer_ai.api.schemas import EvalConfigResponse

    with pytest.raises(ValidationError):
        EvalConfigResponse(
            threshold=1.5,
            judge_prompt_version="v1",
            judge_model="m",
        )
    # Lower bound also enforced.
    with pytest.raises(ValidationError):
        EvalConfigResponse(
            threshold=-0.1,
            judge_prompt_version="v1",
            judge_model="m",
        )


# ---------------------------------------------------------------------------
# Phase 5 Plan 03 — GET /admin/queue-health (FBCK-07) tests QH1..QH5
# ---------------------------------------------------------------------------


def test_qh1_get_queue_health_empty_returns_zero_zero() -> None:
    """QH1: empty feedback table -> {queue_size: 0, resolved_this_week: 0}."""
    from fastapi.testclient import TestClient

    pool = _FakePool(fetchval_queue=[0, 0])
    app = _build_app(pool=pool)
    client = TestClient(app)
    resp = client.get("/admin/queue-health")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body == {"queue_size": 0, "resolved_this_week": 0}


def test_qh2_get_queue_health_three_unresolved() -> None:
    """QH2: 3 unresolved thumbs-down rows -> queue_size=3."""
    from fastapi.testclient import TestClient

    # First fetchval: queue_size; second: resolved_this_week.
    pool = _FakePool(fetchval_queue=[3, 0])
    app = _build_app(pool=pool)
    client = TestClient(app)
    resp = client.get("/admin/queue-health")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["queue_size"] == 3
    assert body["resolved_this_week"] == 0
    # Verify the SQL substrings the route MUST issue.
    acq = pool.last_acquire
    assert acq is not None and acq.last_conn is not None
    calls = acq.last_conn.fetchval_calls
    assert len(calls) == 2
    queue_sql = calls[0][0]
    resolved_sql = calls[1][0]
    assert "rating = -1" in queue_sql
    assert "resolved_at IS NULL" in queue_sql
    assert "resolved_at >=" in resolved_sql
    assert "7 days" in resolved_sql


def test_qh3_get_queue_health_mixed_resolved_unresolved() -> None:
    """QH3: 2 resolved-in-last-7d + 1 unresolved -> queue_size=1, resolved_this_week=2."""
    from fastapi.testclient import TestClient

    pool = _FakePool(fetchval_queue=[1, 2])
    app = _build_app(pool=pool)
    client = TestClient(app)
    resp = client.get("/admin/queue-health")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["queue_size"] == 1
    assert body["resolved_this_week"] == 2


def test_qh4_resolved_older_than_seven_days_excluded() -> None:
    """QH4: 7-day window predicate verified via SQL string.

    The route's resolved_this_week query MUST predicate on
    ``resolved_at >= NOW() - INTERVAL '7 days'`` so rows older than 7 days
    are excluded by Postgres semantics. Asserting the SQL substring is the
    deterministic equivalent at this fake-pool layer; the live behavior is
    covered by the live alembic + pgvector instance.
    """
    from fastapi.testclient import TestClient

    pool = _FakePool(fetchval_queue=[0, 0])
    app = _build_app(pool=pool)
    client = TestClient(app)
    resp = client.get("/admin/queue-health")
    assert resp.status_code == 200, resp.text
    acq = pool.last_acquire
    assert acq is not None and acq.last_conn is not None
    resolved_sql = acq.last_conn.fetchval_calls[1][0]
    # Predicate excludes rows older than 7 days (Postgres semantics).
    assert "NOW() - INTERVAL '7 days'" in resolved_sql or (
        "NOW()" in resolved_sql and "7 days" in resolved_sql
    )


def test_qh5_queue_health_response_rejects_extra_fields_and_negatives() -> None:
    """QH5: QueueHealthResponse extra='forbid' + Field(ge=0)."""
    from pydantic import ValidationError

    from tracer_ai.api.schemas import QueueHealthResponse

    # Happy path.
    ok = QueueHealthResponse(queue_size=0, resolved_this_week=0)
    assert ok.queue_size == 0
    assert ok.resolved_this_week == 0

    # Reject extra field.
    with pytest.raises(ValidationError):
        QueueHealthResponse(
            queue_size=1,
            resolved_this_week=2,
            extra="x",  # type: ignore[call-arg]
        )

    # Reject negative queue_size.
    with pytest.raises(ValidationError):
        QueueHealthResponse(queue_size=-1, resolved_this_week=0)

    # Reject negative resolved_this_week.
    with pytest.raises(ValidationError):
        QueueHealthResponse(queue_size=0, resolved_this_week=-1)
