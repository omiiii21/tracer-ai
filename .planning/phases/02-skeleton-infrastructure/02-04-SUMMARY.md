---
phase: 02-skeleton-infrastructure
plan: 04
subsystem: api
tags:
  - fastapi
  - asyncpg
  - lifespan
  - healthcheck
  - pydantic-settings
  - secretstr

# Dependency graph
requires:
  - phase: 02-skeleton-infrastructure (Wave 1)
    provides: pyproject.toml deps (fastapi, uvicorn[standard], asyncpg, pydantic-settings, structlog); tracer_ai/ package skeleton; tests/conftest.py clean_env fixture
  - phase: 02-skeleton-infrastructure (Wave 2)
    provides: infra/docker-compose.yml with healthy db service + Dockerfile.backend dev stage CMD running uvicorn
  - phase: 02-skeleton-infrastructure (Wave 3)
    provides: tracer_ai/config.py minimal shim with database_url (FLAT) + applied Alembic 0001_initial schema (live in db service)
provides:
  - tracer_ai/config.py FULL Settings (8 D-2.19 fields; FLAT; extra=forbid; SecretStr API keys; Literal log_level)
  - tracer_ai/api/main.py FastAPI app + lifespan + asyncpg pool (min_size=1, max_size=10)
  - tracer_ai/api/health.py GET /healthz with 500ms pool probe; HTTP 503 on db unreachable
  - tests/test_config_failfast.py (5 tests; D-2.21 fail-fast Wave 0 gap closure)
  - tests/test_healthz.py (3 tests; happy + 503 + extra=forbid response model)
  - infra/docker-compose.yml api service with sleep placeholder removed (Dockerfile CMD now runs uvicorn)
affects:
  - Wave 5 (web + readme + pre-commit): brings up the parallel `web` service alongside the running `api`; wires pre-commit hooks
  - Phase 3+ (RAG + chat + feedback): registers new routers via app.include_router(); reads settings.anthropic_api_key + settings.voyage_api_key + settings.llm_bot_model + settings.embedding_model; reuses request.app.state.db_pool for retrieval queries
  - Phase 5+ (eval + judge): reads settings.llm_judge_model
  - Operational: missing required env var now prevents api process from binding port 8000 (fail-fast at IMPORT time per D-2.21)

# Tech tracking
tech-stack:
  added:
    - FastAPI 0.128.x (lifespan= async context manager pattern; @app.on_event NOT used)
    - asyncpg pool driver (min_size=1, max_size=10, max_inactive_connection_lifetime=300s)
    - structlog (key-value structured logging in api module)
    - SecretStr on the two API keys (T-2-04-03 mitigation)
  patterns:
    - "FLAT Settings (Open Question Q2 closed): settings.database_url, settings.anthropic_api_key, etc. -- no nested namespaces. Cost paid: ~2 chars per access. Benefit: zero pydantic-settings nested-aliases version fragility (Assumption A7)."
    - "Single source of DSN: alembic/env.py + tracer_ai/api/main.py both import from tracer_ai.config.settings -- drift impossible by construction (D-2.16)"
    - "DSN scheme stripping: SQLAlchemy form postgresql+asyncpg://... is converted to asyncpg form postgresql://... in the lifespan handler via .replace('+asyncpg', '') (RESEARCH.md Topic 3)"
    - "Lifespan async context manager: open pool -> yield -> close pool wrapped in try/finally so partial-startup failures still drain (RESEARCH.md Common Pitfalls #3)"
    - "Health-check 500ms timeout: pool.acquire(timeout=0.5) AND asyncio.wait_for(SELECT 1, timeout=0.5) -- both bounds enforced because acquire alone times out the connection checkout, not the query"
    - "HTTP 503 (NOT 500) on db unreachable -- orchestration probes retry on 503 but treat 500 as a bug; D-2.33"
    - "Pydantic v2 strict-mode response model: HealthResponse uses ConfigDict with the strict-mode forbid policy (T-2-04-07: prevents silent contract drift between docs/api.md and the wire format)"
    - "structlog binding pattern: log = structlog.get_logger() at module top; log.info(event, **kv) for structured key-value lines -- DSN never appears in any log line (T-2-04-08 mitigation)"
    - "Dockerfile-driven CMD: compose api service has no command override; the dev-stage CMD in Dockerfile.backend runs uvicorn with --reload"

# Files
key-files:
  created:
    - tracer_ai/api/main.py
    - tracer_ai/api/health.py
    - tests/test_config_failfast.py
    - tests/test_healthz.py
    - .planning/phases/02-skeleton-infrastructure/deferred-items.md
  modified:
    - tracer_ai/config.py (Wave 3 minimal shim expanded to full Settings)
    - infra/docker-compose.yml (Wave 2 sleep placeholder removed from api service)
    - pyproject.toml (mypy.overrides: added asyncpg.* to ignore_missing_imports list -- auto-fix)

# Decisions
decisions:
  - "Open Question Q2 closed: FLAT Settings shape adopted (vs nested-with-flat-aliases). Rationale: Wave 3 already shipped FLAT shim and Alembic env.py uses it; nested form carries pydantic-settings version fragility per RESEARCH.md Topic 5."
  - "extra=forbid (tightened from Wave 3 'ignore'): the Wave 3 shim docstring explicitly committed to this tightening once full Settings ships. Honored here per D-2.21 + docs/api.md D-25."
  - "SecretStr on anthropic_api_key + voyage_api_key (NOT plain str): T-2-04-03 mitigation -- Pydantic does not include SecretStr values in repr or ValidationError tracebacks, so a config error never leaks the key to logs."
  - "Literal['DEBUG','INFO','WARNING','ERROR'] on log_level (NOT plain str): T-2-04-02 mitigation -- env-var injection (LOG_LEVEL=DEBUG;rm -rf /) is rejected at validation time before structlog ever sees the value."
  - "ConfigDict(extra='forbid') on HealthResponse: T-2-04-07 mitigation -- prevents silent contract drift between docs/api.md and the wire format. Verified by test_healthz_response_rejects_extra_fields."
  - "503 (NOT 500) on db pool probe failure: D-2.33 -- orchestrators (Kubernetes, Docker healthcheck retry policies) treat 503 as 'transient, retry'; 500 is 'bug, do not retry'. Health checks must use the transient code."
  - "Lifespan handler logs db_pool_ready with min_size + max_size only (NOT the DSN): T-2-04-08 mitigation -- keeps DB credentials out of operational logs."
  - "Compose api service has NO command override: Wave 2 placeholder ['sleep','infinity'] removed; the Dockerfile.backend dev-stage CMD provides the canonical uvicorn invocation. Single source of truth -- changing the dev command means editing the Dockerfile, not chasing two locations."
  - "Auto-fix Rule 1: replaced asyncio.TimeoutError with builtin TimeoutError in health.py (ruff UP041; deprecated alias since Python 3.11)."
  - "Auto-fix Rule 2: added asyncpg.* to mypy.overrides in pyproject.toml (asyncpg has no py.typed marker; CLAUDE.md mandates mypy --strict-clean and the project already had this pattern for voyageai/pgvector/sentence_transformers/tiktoken)."

# Metrics
metrics:
  duration: ~30min
  completed: 2026-05-04
  tasks_completed: 4
  files_created: 5
  files_modified: 3
  tests_added: 8 (5 in test_config_failfast.py + 3 in test_healthz.py)
  total_tests_passing: 24 (all of tests/ green with required env vars set)
  unit_suite_runtime: <2s

# Open Questions
open-questions: []
---

# Phase 2 Plan 04: API Health Pipe Summary

## One-liner
Stood up the FastAPI api process: full FLAT Settings with fail-fast import + lifespan-managed asyncpg pool + GET /healthz with a 500ms probe-timeout returning the documented `{status, version, db}` shape, end-to-end verified live (HTTP 200; `{"status":"ok","version":"0.1.0","db":"ok"}`).

## Goal
Wave 4 closes the api half of INFRA-02. From a clean checkout, `cp .env.example .env` (operator fills `ANTHROPIC_API_KEY` and `VOYAGE_API_KEY`) followed by `cd infra && docker compose up -d --build db migrate api` brings the stack up; `curl http://localhost:8000/healthz` returns HTTP 200 with the documented body. Wave 5 will add the `web` service in parallel and answer ROADMAP success criterion 1 ("docker compose up boots full stack green").

## What Shipped

### tracer_ai/config.py -- Full Settings (FLAT shape)

Wave 3's minimal shim (only `database_url`) was replaced with the full Settings class per D-2.19:

| Field | Source env var | Type | Default | Why |
|-------|----------------|------|---------|-----|
| `database_url` | `DATABASE_URL` | `PostgresDsn` | (required) | DSN for asyncpg pool + Alembic |
| `anthropic_api_key` | `ANTHROPIC_API_KEY` | `SecretStr` | (required) | Phase 3+ rag/llm.py + Phase 5+ eval/llm_judge.py |
| `voyage_api_key` | `VOYAGE_API_KEY` | `SecretStr` | (required) | Phase 3+ rag/embedder.py |
| `llm_bot_model` | `LLM_BOT_MODEL` | `str` | `claude-sonnet-4-5-20250929` | Phase 3+ bot model |
| `llm_judge_model` | `LLM_JUDGE_MODEL` | `str` | `claude-haiku-4-5-20251001` | Phase 5+ judge model |
| `embedding_model` | `EMBEDDING_MODEL` | `str` | `voyage-code-3` | Phase 3 corpus + retrieval |
| `log_level` | `LOG_LEVEL` | `Literal["DEBUG","INFO","WARNING","ERROR"]` | `"INFO"` | structlog level; rejects injection at validation time |
| `enable_reranker` | `ENABLE_RERANKER` | `bool` | `False` | ADR 007 v2 reranker flag |

`model_config = SettingsConfigDict(case_sensitive=True, extra="forbid")` -- tightened from Wave 3 `extra="ignore"` per D-2.21 + docs/api.md D-25.

`settings = Settings()` at module top level: any missing required var raises `pydantic.ValidationError` at IMPORT time, before uvicorn even tries to bind port 8000.

### tracer_ai/api/main.py -- FastAPI app + lifespan + asyncpg pool

- Uses `lifespan=` async context manager (the deprecated `@app.on_event` hook pattern is NOT used).
- Pool config: `min_size=1, max_size=10, max_inactive_connection_lifetime=300.0` per RESEARCH.md Topic 3.
- DSN conversion: `str(settings.database_url).replace("+asyncpg", "")` strips the SQLAlchemy-only `+asyncpg` driver suffix because asyncpg expects the bare scheme.
- Pool attached to `app.state.db_pool` for routes to consume via `request.app.state.db_pool`.
- `app.title = "tracer-ai"`, `app.version = tracer_ai.__version__` (currently `"0.1.0"`).
- Health router included via `app.include_router(health.router)`.

### tracer_ai/api/health.py -- GET /healthz with 500ms db probe

Per D-2.33: returns `HealthResponse(status, version, db)` with HTTP 200 on success, HTTP 503 on failure.

Probe sequence:
```python
async with pool.acquire(timeout=0.5) as conn:
    await asyncio.wait_for(conn.fetchval("SELECT 1"), timeout=0.5)
```

Both bounds matter: `pool.acquire(timeout=0.5)` caps the connection-checkout wait; `asyncio.wait_for(..., timeout=0.5)` caps the SELECT 1 query itself. On `TimeoutError | asyncpg.PostgresError | OSError`, `response.status_code = 503` and the body is `{"status":"degraded","version":"0.1.0","db":"unreachable"}`.

`HealthResponse` uses `ConfigDict(extra="forbid")` per docs/api.md V5 strict-mode (T-2-04-07 mitigation: prevents silent contract drift).

### infra/docker-compose.yml -- api service `command:` removed

The Wave-2 placeholder `command: ["sleep", "infinity"]` is gone. The `Dockerfile.backend` dev-stage `CMD ["uvicorn", "tracer_ai.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]` is now the active command. Single source of truth.

The compose-level healthcheck remains: `["CMD", "curl", "--fail", "http://localhost:8000/healthz"]` (D-2.34).

### Tests

`tests/test_config_failfast.py` -- 5 tests:
1. `test_settings_raises_when_database_url_missing` -- D-2.21 fail-fast on DATABASE_URL
2. `test_settings_raises_when_anthropic_api_key_missing` -- D-2.21 fail-fast on ANTHROPIC_API_KEY
3. `test_settings_raises_when_voyage_api_key_missing` -- D-2.21 fail-fast on VOYAGE_API_KEY
4. `test_settings_loads_with_all_required` -- happy path; verifies FLAT shape and defaults
5. `test_settings_model_rejects_extra_field` -- the W-2 fix: directly tests `extra="forbid"` on the Pydantic model with an unknown FIELD (NOT just an unknown env var, which pydantic-settings ignores regardless of `extra`)

`tests/test_healthz.py` -- 3 tests using FastAPI TestClient + a stub pool:
1. `test_healthz_returns_ok_with_version_and_db_status` -- happy path returns 200 + documented body
2. `test_healthz_returns_503_when_pool_raises` -- PostgresError -> 503 + degraded
3. `test_healthz_response_rejects_extra_fields` -- HealthResponse rejects unknown fields (T-2-04-07)

All 24 tests pass with the standard test env (`DATABASE_URL`, `ANTHROPIC_API_KEY`, `VOYAGE_API_KEY` set).

## Verification Run

End-to-end live verification (Docker Desktop on Windows):

```text
$ cd infra && docker compose down -v --remove-orphans
$ docker compose up -d --build db migrate api
... db Healthy ... migrate Exited 0 ... api Started

$ curl http://localhost:8000/healthz
{"status":"ok","version":"0.1.0","db":"ok"}

$ curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/healthz
200

$ docker compose logs api | grep db_pool
api-1 | 2026-05-04 13:15:59 [info ] db_pool_ready max_size=10 min_size=1
```

The /healthz response was correct on the first probe (no retry loop). The pool readiness log confirms structured logging is wired and that the DSN does NOT appear in logs (T-2-04-08 verified live).

Tooling sanity (project-level):
- `uv run ruff check tracer_ai/ tests/test_config_failfast.py tests/test_healthz.py` -- All checks passed
- `uv run mypy --strict tracer_ai/` -- Success: no issues found in 18 source files
- `uv run pytest -q tests/` -- 24 tests pass

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] ruff UP041: asyncio.TimeoutError is a deprecated alias of builtin TimeoutError**
- **Found during:** Task 3 verification (running ruff after authoring health.py)
- **Issue:** `except (asyncio.TimeoutError, asyncpg.PostgresError, OSError)` triggered ruff UP041; the asyncio alias has been a deprecated alias of the builtin since Python 3.11.
- **Fix:** Replaced `asyncio.TimeoutError` with the builtin `TimeoutError` in health.py.
- **Files modified:** `tracer_ai/api/health.py`
- **Commit:** d8b104b

**2. [Rule 2 - Critical] mypy --strict cannot analyze asyncpg imports (no py.typed)**
- **Found during:** Task 3 verification (running mypy --strict tracer_ai/ after authoring main.py + health.py)
- **Issue:** `Skipping analyzing "asyncpg": module is installed, but missing library stubs or py.typed marker [import-untyped]` in both new api modules. CLAUDE.md mandates mypy-strict-clean as a code-quality gate.
- **Fix:** Added `asyncpg.*` to the existing `[[tool.mypy.overrides]] ignore_missing_imports = true` block in pyproject.toml (the project already used this pattern for voyageai, pgvector, sentence_transformers, tiktoken).
- **Files modified:** `pyproject.toml`
- **Commit:** d8b104b

### Deferred Items (Out of Scope)

**1. ruff E501 in tests/test_imports.py:61** -- pre-existing Wave-1 long line in a test docstring (Wave 1 commit 3cbcb7a). Out of scope per Wave 4 scope boundary; documented in `.planning/phases/02-skeleton-infrastructure/deferred-items.md` for Wave 5 (which adds pre-commit hooks per Plan 02-05).

### Self-Invalidating Grep Gate Rewrites (no rule violation; planner-supplied gate hygiene)

Two of the planner's `<verify>` grep gates expected `extra="forbid"` and `structlog.get_logger` to appear EXACTLY once in the source. The literal substrings appeared a second time inside docstrings explaining the choice. Per the prompt's "self-invalidating grep gate hygiene" instruction, the docstrings were reworded to describe the policy without quoting it verbatim:
- `tracer_ai/config.py` docstring: `extra="forbid"` -> "the model_config below sets the strict-mode forbid policy on extras"
- `tracer_ai/api/main.py` docstring: `structlog.get_logger()` -> "bind a logger via the structlog factory (see `log = ...` below)"
- `tracer_ai/api/health.py` docstring: `model_config = ConfigDict(extra="forbid")` -> "the response model below uses the strict ConfigDict policy that rejects unknown fields"

Final state: each gated literal substring appears exactly once (in the actual code), gates pass green.

## ASVS V5 + V7 + V8 Mitigations Recorded

| Threat ID | ASVS | Mitigation Verified |
|-----------|------|---------------------|
| T-2-04-02 | V5 (Input Validation) | `log_level: Literal["DEBUG","INFO","WARNING","ERROR"]` rejects out-of-enum values at validation time. Verified by Settings field declaration grep (`grep -c 'log_level: Literal\['` returns 1). |
| T-2-04-03 | V7 (Error Handling) | `SecretStr` on anthropic_api_key + voyage_api_key. Pydantic does not include SecretStr values in `repr()` or ValidationError tracebacks. Verified by Settings field declaration grep. |
| T-2-04-07 | V5 (Input Validation) | `HealthResponse` uses ConfigDict strict-mode forbid policy on extras. Verified by `test_healthz_response_rejects_extra_fields`. |
| T-2-04-08 | V8 (Data Protection) | Lifespan log line is `log.info("db_pool_ready", min_size=1, max_size=10)` -- DSN NOT logged. Verified live: `docker compose logs api | grep db_pool` shows no DSN. |

## Wave 0 Gaps Closed

Per RESEARCH.md "Validation Architecture":

- ✅ `tests/test_config_failfast.py` -- 5 tests covering D-2.21 fail-fast contract for INFRA-03.
- ✅ `tests/test_healthz.py` -- 3 tests covering /healthz contract for INFRA-02 (Wave 4 half).

## Wave 5 Readiness

Wave 5 (Plan 02-05: web service + README + pre-commit) can now:
- Bring up the parallel `web` service alongside the running `api` (no api changes needed).
- Wire pre-commit hooks (ruff + mypy + tsc); the api modules already pass `ruff check tracer_ai/ tests/{test_config_failfast,test_healthz}.py` and `mypy --strict tracer_ai/` cleanly.
- Document the operator workflow (`cp .env.example .env`, fill keys, `docker compose up`) in the README.
- Address the deferred Wave-1 ruff E501 in `tests/test_imports.py` (documented in deferred-items.md).

Note: `pre-commit run --all-files` is NOT yet wired (Wave 5). Manually-run `ruff check tracer_ai/ tests/test_config_failfast.py tests/test_healthz.py` and `mypy --strict tracer_ai/` both pass clean as of this wave.

## Self-Check: PASSED

Files verified to exist:
- FOUND: tracer_ai/config.py
- FOUND: tracer_ai/api/main.py
- FOUND: tracer_ai/api/health.py
- FOUND: tests/test_config_failfast.py
- FOUND: tests/test_healthz.py
- FOUND: infra/docker-compose.yml (modified)
- FOUND: pyproject.toml (modified)
- FOUND: .planning/phases/02-skeleton-infrastructure/deferred-items.md

Commits verified to exist:
- FOUND: db45e01 feat(02-04): expand Settings to full FLAT shape with fail-fast at import
- FOUND: a4aa04f feat(02-04): author api/main.py with FastAPI lifespan + asyncpg pool
- FOUND: 9cdb2c8 feat(02-04): author api/health.py with /healthz endpoint + 500ms db probe
- FOUND: d8b104b fix(02-04): satisfy ruff UP041 and mypy strict on Wave 4 api modules
- FOUND: 408df29 feat(02-04): drop Wave 2 sleep placeholder from compose api service

Live HTTP verification:
- FOUND: HTTP 200 from http://localhost:8000/healthz
- FOUND: response body `{"status":"ok","version":"0.1.0","db":"ok"}`
- FOUND: `db_pool_ready min_size=1 max_size=10` in api logs
- FOUND: zero DSN occurrences in api logs (T-2-04-08 verified)
