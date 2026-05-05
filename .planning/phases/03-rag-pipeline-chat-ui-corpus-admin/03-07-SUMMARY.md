---
phase: 03-rag-pipeline-chat-ui-corpus-admin
plan: 07
subsystem: api/admin-corpus
tags: [fastapi, background-tasks, asyncio-lock, single-flight, in-memory-job-board, asyncpg, pydantic-strict, audit-log, structlog, discriminated-union]

# Dependency graph
requires:
  - phase: 03-rag-pipeline-chat-ui-corpus-admin
    plan: 01
    provides: api/schemas.py (IngestSourceRequest / IngestUrlsRequest discriminated union; IngestResponse; IngestStatus; CorpusState; ChunkingConfig; ChunkingConfigPatch; DocSummary) + Plan 01 URL regex validator (^https?://) + Plan 01 chunk_size/overlap field bounds
  - phase: 03-rag-pipeline-chat-ui-corpus-admin
    plan: 04
    provides: corpus.store.list_corpus(pool) returning the {doc_count, chunk_count, embedding_model, embedding_model_version, last_indexed_at, docs[]} shape consumed by GET /admin/corpus
  - phase: 03-rag-pipeline-chat-ui-corpus-admin
    plan: 05
    provides: corpus.ingest.run_ingest(source, urls, *, embedder, chunker, pool) -> IngestResult with T-03-05-06 partial-commit safety
  - phase: 02-skeleton-infrastructure
    provides: asyncpg pool DI from request.app.state (health.py:44-47); FastAPI APIRouter pattern; FakePool stub pattern from tests/test_healthz.py
provides:
  - tracer_ai.api.admin.router (APIRouter prefix="/admin") with 4 endpoints: GET /corpus, POST /ingest, GET /ingest/{job_id}, PATCH /chunking-config
  - tracer_ai.api.admin._jobs (module-level dict[UUID, JobState]) + _active_job_id (UUID | None) + _ingest_lock (asyncio.Lock) -- single-flight job board
  - tracer_ai.api.admin._chunking_config (module-level dict[str, int]) -- live chunker params (next-ingest-applies semantics)
  - tracer_ai.api.admin._run_ingest_job (background-task entry point; constructs VoyageEmbedder + MarkdownHeaderChunker + dispatches run_ingest)
affects: [03-08-chat-ui-frontend (admin UI page consumes these endpoints), 03-09-frontend-tests, 04-tracer-postgres-writer (orthogonal)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Single-flight ingest via asyncio.Lock + _active_job_id global: lock is held ONLY around the active-job check + assignment so the lock window is microseconds; concurrent POST while a job runs raises 409 (T-03-07-03)"
    - "In-memory job board (dict[UUID, JobState]): per-process; api restart wipes the board (documented as Phase 7 polish item to migrate to corpus_ingest_jobs table); GET /ingest/{job_id} returns 404 across a restart (UI treats 404 as terminal)"
    - "FastAPI BackgroundTasks dispatch (no Celery/RQ in v1): _run_ingest_job is an async helper registered via background_tasks.add_task; updates JobState across queued -> running -> succeeded|failed transitions"
    - "Discriminated-union request body (IngestSourceRequest | IngestUrlsRequest): FastAPI accepts either body shape; isinstance discriminator helpers extract source vs. urls without two separate route handlers"
    - "Auth-boundary comment block (RESEARCH.md s5): /admin endpoints have no authentication -- v1 single-user local-dev only (ADR 009); production hardening deferred to v1.5+"
    - "PATCH chunking-config persists in module global (next-ingest-applies semantics): the constructed MarkdownHeaderChunker reads _chunking_config at job dispatch time so the operator's PATCH takes effect on the next POST /ingest, not retroactively"
    - "Error field in IngestStatus is str(exc) only (T-03-07-09): full traceback goes to structlog (log.error with traceback=traceback.format_exc()) so the audit trail captures the stack while the user-visible error stays bounded"

key-files:
  created:
    - tracer_ai/api/admin.py
    - tests/test_admin_routes.py
  modified:
    - tracer_ai/api/main.py (registered admin.router; one-line addition)

key-decisions:
  - "Single-flight via asyncio.Lock + _active_job_id, NOT a corpus_ingest_jobs DB table: Phase 3 ships in-memory only per RESEARCH.md s2 lines 79-80. The DB-backed job table is documented as a Phase 7 polish item. The lock window is microseconds (just the active-job check + assignment) so it does not bottleneck GET /admin/corpus polling."
  - "FastAPI BackgroundTasks for dispatch (NOT Celery / RQ / Dramatiq): RESEARCH.md s2 explicitly forbids extra services in v1 (CLAUDE.md no-extra-services rule). BackgroundTasks runs the coroutine after the response is sent; the response returns 202 immediately. Single-process means the background task survives only as long as the api process; restart loses in-flight jobs (acceptable for v1 single-user local-dev)."
  - "JobState shape: dict, not Pydantic model. The state board is internal to admin.py; only the GET /admin/ingest/{job_id} response (IngestStatus, defined in Plan 01 schemas) crosses the wire. Keeping JobState as a plain dict avoids a Pydantic round-trip on every internal update; the IngestStatus model_validate happens only at the response boundary."
  - "Chunking config in module global (not in Settings, not in DB): the operator's PATCH must apply on the NEXT ingest (next-ingest-applies semantics per ADMN-03 must-have). Storing in Settings would require a write-able settings instance which Pydantic-Settings does not support cleanly. A DB row would survive restarts but is overkill for v1 (the operator can re-PATCH after restart). Module global is the simplest model that satisfies the contract."
  - "Discriminator helpers (_is_source_request / _is_urls_request) instead of two separate route handlers: keeping a single POST /ingest route preserves the docs/api.md authoritative shape (one endpoint, two body variants). FastAPI's IngestRequest = IngestSourceRequest | IngestUrlsRequest union resolves the body type via Pydantic; the helpers narrow at runtime for the source/urls dispatch into _run_ingest_job."
  - "Error string in JobState['error'] is str(exc) only (T-03-07-09): the full traceback lives in structlog (log.error(..., traceback=traceback.format_exc())). The user-visible error field is bounded so a deeply-nested SDK error message cannot blow up an SSE frame or admin UI render."
  - "_run_ingest_job is module-level (not nested inside post_ingest): allows tests to monkeypatch admin._run_ingest_job to a no-op AsyncMock. test_post_ingest_returns_202_with_job_id and test_post_ingest_with_valid_urls both rely on this; a nested helper would require deeper instrumentation."

patterns-established:
  - "Single-flight async lock + state-tracker global: the asyncio.Lock + _active_job_id pair is the v1 idiom for any 'only one of these may run at a time' resource. Reusable for any future admin operation that mutates global state (e.g., a future re-embed-all-chunks operation)."
  - "Background-task entry point as a module-level async function: _run_ingest_job(job_id, *, source, urls, pool) is the dispatch shape FastAPI BackgroundTasks expects. Reusable for any future admin operation that returns 202 + a polled status (e.g., a future bulk-feedback-export operation)."
  - "Module-level state reset in autouse fixture: tests that touch _jobs / _active_job_id / _chunking_config all use the autouse _reset_admin_state fixture to wipe state post-test. Mirrors the conftest.py clean_env pattern for env-var resets."

requirements-completed:
  - ADMN-01
  - ADMN-02
  - ADMN-03
  - ADMN-04

# Metrics
duration: 7min30s
completed: 2026-05-05
---

# Phase 3 Plan 07: Admin API (Corpus + Ingest + Chunking-Config) Summary

**Wired the 4-endpoint /admin/* surface that the Plan 09 admin frontend will consume: GET /admin/corpus reads list_corpus + chunking config, POST /admin/ingest dispatches run_ingest via FastAPI BackgroundTasks with single-flight 409 guard, GET /admin/ingest/{id} polls in-memory JobState, PATCH /admin/chunking-config persists chunk_size + overlap in a module global (next-ingest-applies).**

## Performance

- **Duration:** ~7min30s
- **Started:** 2026-05-05T17:35:46Z
- **Completed:** 2026-05-05T17:43:16Z
- **Tasks:** 1 (type="auto" tdd="true")
- **Files modified:** 2 created (1 source + 1 test) + 1 modified (api/main.py one-line addition)

## Accomplishments

- **POST /admin/ingest** (`tracer_ai/api/admin.py`): accepts the Plan 01 `IngestRequest = IngestSourceRequest | IngestUrlsRequest` discriminated union; returns 202 + `IngestResponse(ingest_job_id, status="queued")`. Single-flight guard (T-03-07-03) wraps the `_active_job_id` check + assignment in an `asyncio.Lock`; a concurrent POST while a job runs raises `HTTPException(status_code=409, detail="Ingest already in progress")`. Dispatch is via `BackgroundTasks.add_task(_run_ingest_job, job_id, source=..., urls=..., pool=...)` -- no Celery/RQ (RESEARCH.md s2: no extra services in v1).
- **GET /admin/corpus** (`tracer_ai/api/admin.py`): calls `await list_corpus(pool)` (Plan 04 `corpus/store.py`) and merges the in-memory `_chunking_config` into the `CorpusState` response. The four KPI cards (doc_count, chunk_count, embedding_model + version, last_indexed_at) and the per-doc table are returned in one response so the admin UI can render atomically without a second round-trip. Empty-corpus path inherits the Plan 04 zero-coercion: returns the same shape with zeros + empty docs list so the UI renders on a fresh checkout.
- **GET /admin/ingest/{job_id}** (`tracer_ai/api/admin.py`): looks up `_jobs[job_id]` and returns the `IngestStatus` Plan 01 schema (status, started_at, finished_at, docs_processed, docs_total, chunks_written, progress, error). 404 on unknown job_id (process restart wipes the in-memory job board; UIs that polled across a restart treat 404 as terminal).
- **PATCH /admin/chunking-config** (`tracer_ai/api/admin.py`): accepts the Plan 01 `ChunkingConfigPatch` body (chunk_size 100..4000, overlap 0..500 -- enforced by Pydantic `Field(ge=..., le=...)`); updates the module-global `_chunking_config` dict; logs `chunking_config_updated` audit event. The next ingest's `_run_ingest_job` reads the dict at chunker construction time, so values apply on the next POST /ingest (next-ingest-applies semantics per ADMN-03).
- **`_run_ingest_job` background-task entry** (`tracer_ai/api/admin.py`): constructs `MarkdownHeaderChunker(chunk_size=_chunking_config["chunk_size"], overlap=_chunking_config["overlap"])` + `VoyageEmbedder()`, then awaits `run_ingest(source, urls, embedder=..., chunker=..., pool=...)` (Plan 05). Updates `_jobs[job_id]` across queued -> running -> succeeded|failed transitions. On exception, `JobState["status"] = "failed"` + `error = str(exc)` (T-03-07-09: full traceback to structlog only). Always clears `_active_job_id` in finally so the next ingest can start.
- **Auth-boundary comment block** (top of `tracer_ai/api/admin.py`, 4 lines per RESEARCH.md s5 lines 302-307): "/admin endpoints have no authentication -- v1 is single-user local-dev only (ADR 009). Production hardening (auth, RBAC, audit) is reserved for v1.5+. Compose `db` service exposes 5432 only on the internal network; api is :8000 on localhost." Documentation, not enforcement -- enough for portfolio purposes.
- **9 tests + mypy --strict clean** (`tests/test_admin_routes.py`):
  - `test_get_corpus_returns_state_with_chunking_config` -- 200 + all 7 CorpusState keys present + chunking_config defaults (900/100 from settings).
  - `test_post_ingest_returns_202_with_job_id` -- 202 + ingest_job_id parses as UUID + status="queued".
  - `test_concurrent_ingest_returns_409` -- pre-set `_active_job_id` then POST -> 409.
  - `test_get_ingest_status_404_for_unknown_id` -- random UUID -> 404.
  - `test_get_ingest_status_returns_state` -- pre-insert JobState into `_jobs` -> 200 + all status fields.
  - `test_patch_chunking_config_valid` -- {chunk_size: 600, overlap: 50} -> 200 + echoed body.
  - `test_patch_chunking_config_too_small` -- {chunk_size: 50} -> 422 (Pydantic ge=100).
  - `test_post_ingest_invalid_url` -- {urls: ["not-a-url"]} -> 422 (Plan 01 URL regex).
  - `test_post_ingest_with_valid_urls` -- {urls: [valid url]} -> 202 + ingest_job_id.
- **Zero regressions**: `pytest tests/` reports 180 passed + 1 skipped (pre-existing skip; unrelated). All Phase 3 Plans 03-01..06 tests still pass; no anti-pattern regression; `import_cycle_guard.py` reports `OK: tracer_ai module DAG check clean (4 layers)`.

## Task Commits

Single task committed atomically (TDD: test file written first, RED confirmed via ImportError on `from tracer_ai.api import admin`, then implementation):

1. **Task 1: api/admin.py + api/main.py registration + tests/test_admin_routes.py** -- `ecde5e9` (feat)

## Files Created/Modified

**Created:**
- `tracer_ai/api/admin.py` -- 4 endpoints (GET /corpus, POST /ingest, GET /ingest/{job_id}, PATCH /chunking-config) + `_run_ingest_job` background helper + `_jobs` / `_active_job_id` / `_chunking_config` / `_ingest_lock` module state + auth-boundary comment block.
- `tests/test_admin_routes.py` -- 9 tests using FakePool stubs (canned `list_corpus` aggregates) + monkeypatched `_run_ingest_job` (no-op AsyncMock-style assignment) + autouse `_reset_admin_state` fixture for cross-test isolation.

**Modified:**
- `tracer_ai/api/main.py` -- registered `admin.router` (one-line addition; existing `chat`, `feedback`, `health` routers preserved).

## Decisions Made

- **Single-flight via `asyncio.Lock` + `_active_job_id`** (NOT a `corpus_ingest_jobs` DB table). RESEARCH.md s2 lines 79-80 explicitly call out the in-memory-only choice for v1; the DB table is a Phase 7 polish item. The lock window is microseconds (just the active-job check + assignment) so it does not bottleneck GET /admin/corpus polling. Witness: `test_concurrent_ingest_returns_409`.
- **FastAPI BackgroundTasks for dispatch** (NOT Celery/RQ/Dramatiq). CLAUDE.md "What NOT to Use" + RESEARCH.md s2 forbid extra services in v1. BackgroundTasks runs the coroutine after the response is sent; the 202 returns immediately. Single-process means in-flight jobs are lost on api restart -- acceptable for v1 single-user local-dev (operator can re-trigger).
- **JobState shape: plain `dict`, not Pydantic model.** Internal to `admin.py`; only the GET /admin/ingest/{job_id} response (`IngestStatus` Plan 01 model) crosses the wire. Avoiding a Pydantic round-trip on every internal status update keeps the background-task path lean.
- **Chunking config in a module global** (not in `Settings`, not in DB). The operator's PATCH must apply on the NEXT ingest per ADMN-03 must-have ("next-ingest-applies"). Pydantic-Settings does not cleanly support runtime mutation; a DB row is overkill for v1 (the operator can re-PATCH after restart). Module global is the simplest model that satisfies the contract. The chunker constructor (Plan 02) re-validates `chunk_size` 100..4000 and `overlap` 0..500 so even a direct module mutation cannot produce an invalid Chunker (T-03-07-05 defense in depth).
- **Single POST /ingest route accepting `IngestRequest = IngestSourceRequest | IngestUrlsRequest`** (NOT two separate route handlers). Preserves the docs/api.md authoritative shape (one endpoint, two body variants). FastAPI's union resolves the body type via Pydantic; runtime `_is_source_request` / `_is_urls_request` discriminator helpers narrow for the source/urls dispatch into `_run_ingest_job`.
- **`_run_ingest_job` is module-level**, not nested inside `post_ingest`. Allows tests to monkeypatch `admin._run_ingest_job` to a no-op (`test_post_ingest_returns_202_with_job_id`, `test_post_ingest_with_valid_urls` both rely on this); a nested helper would require deeper instrumentation. Module-level also lets the structured `ingest_dispatched` log event fire from `post_ingest` (audit trail) before the heavy work runs.
- **Error field in JobState is `str(exc)` only** (T-03-07-09). The full traceback goes to structlog via `log.error("ingest_job_failed", ..., traceback=traceback.format_exc())`. The user-visible error field is bounded so a deeply-nested SDK error message cannot blow up an SSE frame or the admin UI render. Mirrors the same discipline applied in chat.py `event: error` frames (Plan 06).

## Deviations from Plan

None. The plan was executed exactly as written:

- 4 endpoints (GET /corpus, POST /ingest, GET /ingest/{job_id}, PATCH /chunking-config) registered.
- 9 tests pass (the plan called for >= 8; 9th test `test_post_ingest_with_valid_urls` is an additional positive-path witness for the URL discriminated-union dispatch path).
- mypy --strict clean on tracer_ai/api/admin.py + tracer_ai/api/main.py.
- `pytest tests/test_admin_routes.py tests/test_healthz.py tests/test_chat_route.py tests/test_feedback_route.py -q` -> 24 passed.
- `pytest tests/` -> 180 passed + 1 skipped (zero regressions across Phase 3 Plans 01..08 wave).
- All pre-commit hooks pass on first commit attempt: trim-whitespace, fix-eof, ruff, ruff-format, gitleaks, mypy --strict, pytest --testmon, import-cycle-guard, anti-pattern-grep.

## Issues Encountered

- **None.** TDD cycle completed in one pass: RED confirmed via `ImportError: cannot import name 'admin' from 'tracer_ai.api'` on the first pytest invocation; GREEN confirmed via `9 passed in 2.03s` after writing the implementation. No hook-driven reformatting needed (ruff + ruff-format passed first try). No mypy fixes needed.

## Threat Mitigations Applied

| Threat ID | Status | Where |
|-----------|--------|-------|
| T-03-07-01 (Spoofing -- /admin/* unauthenticated) | Accepted (documented) | 4-line comment block at top of `tracer_ai/api/admin.py` declares the boundary; v1 single-user local-dev only (ADR 009). Production hardening reserved for v1.5+. Compose `db` service exposes 5432 only on the internal network; api is :8000 on localhost. |
| T-03-07-02 (Tampering -- POST /admin/ingest urls validation) | Mitigated | Plan 01 `IngestUrlsRequest` schema enforces per-URL regex `^https?://` via `field_validator`. Server-side Pydantic re-validates regardless of any client-side check. Witness: `tests/test_admin_routes.py::test_post_ingest_invalid_url` (422). |
| T-03-07-03 (DoS -- concurrent ingest spam) | Mitigated | `_active_job_id` guard + `asyncio.Lock`: a second POST while a job runs raises 409 (`HTTPException`). Witness: `tests/test_admin_routes.py::test_concurrent_ingest_returns_409`. |
| T-03-07-04 (DoS -- URL list size) | Mitigated upstream | Plan 01 `IngestUrlsRequest.urls: Annotated[list[str], Field(min_length=1, max_length=100)]` caps the list at 100 URLs at the FastAPI validation layer. |
| T-03-07-05 (Tampering -- PATCH /admin/chunking-config) | Mitigated (defense in depth) | Plan 01 `ChunkingConfigPatch.chunk_size: Annotated[int, Field(ge=100, le=4000)]` + `overlap: Annotated[int, Field(ge=0, le=500)]` enforce bounds at the FastAPI layer. The Plan 02 `MarkdownHeaderChunker.__init__` re-validates so even a direct module mutation cannot produce an invalid Chunker. Witness: `tests/test_admin_routes.py::test_patch_chunking_config_too_small` (422). |
| T-03-07-06 (Repudiation -- admin audit trail) | Mitigated | Every endpoint logs structured events via structlog: `corpus_listed`, `ingest_dispatched`, `ingest_completed`, `ingest_concurrent_blocked`, `ingest_job_failed`, `chunking_config_updated`. Full traceback (when applicable) attached to `ingest_job_failed`. |
| T-03-07-07 (Information Disclosure -- GET /admin/corpus surfaces full doc list + source URLs) | Accepted | Local-dev only; the operator IS the user. Production deployment would gate this endpoint via auth (deferred to v1.5+ per ADR 009). |
| T-03-07-08 (Tampering -- _jobs in-memory state) | Accepted | Module-level dict is per-process; api restart wipes the job board. Documented as Phase 7 polish item to migrate to a `corpus_ingest_jobs` DB table. UIs that polled across a restart treat 404 (job not found) as terminal. |
| T-03-07-09 (Information Disclosure -- error field in IngestStatus) | Mitigated | `_run_ingest_job` sets `_jobs[job_id]["error"] = str(exc)` only; full `traceback.format_exc()` goes to structlog via `log.error("ingest_job_failed", ..., traceback=...)`. The user-visible error field is bounded so a deeply-nested SDK error cannot blow up the admin UI render. |

## Self-Check: PASSED

- File `tracer_ai/api/admin.py` exists. Verified.
- File `tests/test_admin_routes.py` exists. Verified.
- File `tracer_ai/api/main.py` modified (admin.router registered). Verified.
- Commit `ecde5e9` (Task 1) exists in `git log`. Verified.
- `pytest tests/test_admin_routes.py -x -q` -> 9 passed.
- `pytest tests/test_admin_routes.py tests/test_healthz.py tests/test_chat_route.py tests/test_feedback_route.py -q` -> 24 passed (zero regressions in the four-route smoke).
- `pytest tests/` -> 180 passed + 1 skipped (zero regressions across full Phase 3 Wave 4+5 suite).
- `mypy --strict tracer_ai/api/admin.py tracer_ai/api/main.py` -> Success: no issues found in 2 source files.
- `pytest tests/test_anti_patterns.py -q` -> 7 passed (no SDK-isolation regression).
- `python infra/scripts/import_cycle_guard.py` -> OK: tracer_ai module DAG check clean (4 layers).
- Acceptance grep counts:
  - `APIRouter(prefix="/admin")` (admin.py) = 1.
  - `@router.{get,post,patch}` (admin.py) = 4 (one per endpoint).
  - `no authentication | local-dev only | ADR 009` (admin.py) = 2 (>= 1).
  - `background_tasks.add_task | BackgroundTasks` (admin.py) = 5 (>= 1).
  - `list_corpus` (admin.py) = 4 (>= 1).
  - `admin.router | include_router(admin` (main.py) = 1 (>= 1).
- All pre-commit hooks pass on first commit attempt: trim-whitespace, fix-eof, ruff, ruff-format, gitleaks, mypy --strict, pytest --testmon, import-cycle-guard, anti-pattern-grep.

## User Setup Required

None -- no external service configuration required for the test gates. The 9 tests run entirely against FakePool stubs + monkeypatched `_run_ingest_job` (no real Voyage / Anthropic / Postgres). Manual smoke (`curl http://localhost:8000/admin/corpus` against a live `docker compose up` stack with seeded corpus) is a Phase-3-end gate, not a per-plan blocker.

## Next Phase Readiness

- **Phase 3 Plan 08 / 09 (admin UI frontend):** unblocked. The 4 endpoints documented in `docs/api.md` are now wired: the React `<CorpusCards>` consumes GET /admin/corpus; `<ReindexButton>` POSTs /admin/ingest then polls GET /admin/ingest/{id} every 2s via TanStack Query `useQuery({refetchInterval: 2000})`; `<ChunkingConfigForm>` PATCHes /admin/chunking-config. The wire shapes (Plan 01 schemas) are stable.
- **Phase 4 (tracer Postgres writer):** orthogonal -- no admin route or pipeline coupling. The pipeline construction in lifespan.py (Plan 06) already stashes the writer on app.state.trace_writer; admin endpoints don't touch it.
- **Phase 5 (eval + judge):** orthogonal -- judge runs against trace rows (Phase 4 writer) + feedback rows (Plan 06 endpoint); the admin surface here is corpus-state only.
- **Phase 7 (polish):** the documented v1.5+ items are (a) `corpus_ingest_jobs` DB table for cross-restart job persistence (T-03-07-08), (b) /admin/* auth gate (T-03-07-01), (c) production-grade error scrubbing on IngestStatus.error (T-03-07-09 hardening).

## Threat Flags

None -- no new threat surface introduced beyond the plan's `<threat_model>` register. The new attack surface (4 admin endpoints + in-memory job board + module-global chunking config) is bounded by:
- Plan 01 schema validation (URL regex; chunk_size/overlap bounds; extra='forbid');
- single-flight asyncio.Lock + _active_job_id (DoS bound on concurrent POST);
- 1.0s asyncpg pool acquire timeout on GET /admin/corpus (inherited from list_corpus);
- str(exc)-only error field on JobState (T-03-07-09);
- structlog audit trail on every endpoint (`corpus_listed`, `ingest_dispatched`, `ingest_completed`, `chunking_config_updated`, `ingest_concurrent_blocked`, `ingest_job_failed`);
- module-private `_jobs` dict (no cross-process leakage; api restart wipes the board, documented).

---
*Phase: 03-rag-pipeline-chat-ui-corpus-admin*
*Completed: 2026-05-05*
