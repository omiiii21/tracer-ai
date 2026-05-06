---
phase: 04-tracer-trace-explorer
plan: 01
subsystem: database
tags: [phase-4, alembic, migration, postgres, partitioned-tables, asyncpg, pydantic-v2, span-model, payload, traces-denorm]

# Dependency graph
requires:
  - phase: 02-skeleton-infrastructure
    provides: alembic 0001_initial.py traces/spans/span_payloads schema; asyncpg pool + lifespan pattern
  - phase: 03-rag-pipeline-chat-ui-corpus-admin
    provides: Pipeline 4-span emission with try/finally cancellation safety; Span Pydantic model + TraceWriter Protocol
provides:
  - traces table denormalized scalar columns (latency_ms, faithfulness, feedback_rating, estimated_cost_usd)
  - traces_feedback_rating_chk CHECK constraint
  - traces_faithfulness_idx + traces_feedback_rating_idx
  - 2026-08 spans partition (extends 0001's 2026-05/06/07 coverage)
  - Span.payload field replacing Span.payload_id
  - Pipeline.db_pool kwarg with up-front INSERT INTO traces + child-span payloads + latency_ms/estimated_cost_usd UPDATEs
affects: [04-02, 04-03, 04-04, 04-05, 04-06]

# Tech tracking
tech-stack:
  added: []  # No new runtime dependencies; asyncpg already in pyproject.toml
  patterns:
    - "Additive-reversible Alembic migration via op.execute(sa.text(...)) raw SQL with IF NOT EXISTS / IF EXISTS guards"
    - "Pydantic v2 field swap (payload_id -> payload) with extra='forbid' rejecting the legacy field"
    - "Pipeline closure capture pattern: trace_id and self._db_pool captured by closure into _llm_text_iter; _emit_root receives trace_id as argument"
    - "FakePool / FakeConn / FakeAcquireCtx recorder fixture pattern (mirrors tests/test_feedback_route.py) for asserting SQL operations + arg consistency"

key-files:
  created:
    - alembic/versions/0002_traces_denorm.py
  modified:
    - tracer_ai/tracer/writer.py
    - tracer_ai/rag/pipeline.py
    - tests/test_writer_protocol.py
    - tests/test_pipeline.py

key-decisions:
  - "0002 migration adds 4 columns (latency_ms, faithfulness, feedback_rating, estimated_cost_usd) — RESEARCH §Open Questions #1 surfaced that docs/api.md TraceListItem requires estimated_cost_usd not in plain D-4.02 list"
  - "feedback_rating CHECK constraint mirrors docs/api.md FeedbackRequest.rating Literal[-1, 1] — cross-layer integrity per established pattern"
  - "2026-08 spans partition added in this revision (Pitfall 4) to prevent partition-routing errors during current-date integration tests"
  - "Pipeline up-front INSERT INTO traces uses query[:4000] truncation (matches docs/api.md ChatRequest max_length=4000 — T-04-01-01 mitigation) and ON CONFLICT (id) DO NOTHING (T-04-01-07 idempotent guard)"
  - "estimated_cost_usd UPDATE lives inside _llm_text_iter finally — closure-captures trace_id and self._db_pool from _orchestrate scope; preserves async-cancellation safety (Pitfall 7.8 / T-03-05-04)"
  - "Span.payload accepts dict[str, Any] | None — D-4.11 explicitly rejects discriminated-union typed payloads"

patterns-established:
  - "Closure capture verification pattern: integration test asserts INSERT and BOTH UPDATEs fire AND trace_id arg matches across all 3 — guards against accidental re-uuid4() in different scopes"
  - "Migration reversibility drill: upgrade -> downgrade -1 -> upgrade verifies forward-roll cleanliness on every schema change"
  - "Pre-commit ruff-format may reformat newly-written files — re-stage and commit; never use --no-verify"

requirements-completed: [TRCR-01, TRCR-09, TRCR-10]

# Metrics
duration: ~25min
completed: 2026-05-06
---

# Phase 04 Plan 01: Schema Denorm + Span.payload + Pipeline Wiring Summary

**Alembic 0002 adds 4 denormalized columns + 2026-08 spans partition; Span.payload_id swapped for Span.payload; pipeline now lands traces row up-front, payloads on 3 child spans, and latency_ms + estimated_cost_usd UPDATEs after the LLM final event — keystone enabling Plan 2/3/4/5/6.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-05-06 (Phase 04 Plan 01 execution start)
- **Completed:** 2026-05-06
- **Tasks:** 3 (all autonomous; one TDD)
- **Files modified:** 4 (1 created, 4 modified)

## Accomplishments

- 0002 alembic revision with 4 ADD COLUMN IF NOT EXISTS, 2 indexes, CHECK constraint, and 2026-08 partition; full reversibility drill (upgrade -> downgrade -> upgrade) clean
- Span Pydantic model atomically swapped (payload_id removed; payload added) — extra='forbid' now rejects the legacy field; mypy --strict + ruff clean
- Pipeline accepts db_pool kwarg; when set, every chat request lands a traces row before embed_batch and finalizes latency_ms/ended_at/estimated_cost_usd via UPDATEs after the LLM final event
- All 3 child spans carry payload= per docs/trace-schema.md; root rag.request span carries payload=None explicitly (D-4.11)
- New integration test asserts ALL 3 SQL ops fire AND trace_id is consistent across them — proves the closure capture for trace_id works inside both _llm_text_iter and _emit_root

## Task Commits

Each task was committed atomically:

1. **Task 1: alembic 0002_traces_denorm** — `289e21d` (feat)
2. **Task 2: Span.payload field swap (TDD)** — `9175a20` (feat — combines RED/GREEN since the change is a single Pydantic field swap with two new positive tests + one negative test)
3. **Task 3: Pipeline modifications + tests** — `a3d2c72` (feat — TDD-style: tests added alongside implementation since both belong to a single closure-capture verification gate)

_Note: Task 2 and Task 3 are marked tdd="true" in the plan; both follow a combined RED+GREEN style because the test additions verify field-swap (positive: payload accepted; negative: payload_id rejected) and pipeline integration (positive: 3 SQL ops fire) which each form one logical gate._

## Files Created/Modified

- **Created:** `alembic/versions/0002_traces_denorm.py` — Alembic revision adding 4 traces columns + 2 indexes + CHECK constraint + 2026-08 spans partition. Reversible.
- **Modified:** `tracer_ai/tracer/writer.py` — Removed `payload_id: UUID | None`; added `payload: dict[str, Any] | None = None` (D-4.11/D-4.13). TraceWriter Protocol + Noop/Stdout adapters untouched.
- **Modified:** `tracer_ai/rag/pipeline.py` — Added `import asyncpg`; added `db_pool: asyncpg.Pool | None = None` kwarg + `self._db_pool` attribute; up-front INSERT INTO traces in `_orchestrate` before embed_batch; payload= on rag.retrieve / rag.prompt_assemble / rag.llm_call Span constructors; payload=None explicit on root rag.request span; UPDATE traces SET latency_ms, ended_at after writer.emit in `_emit_root`; UPDATE traces SET estimated_cost_usd inside `_llm_text_iter` finally.
- **Modified:** `tests/test_writer_protocol.py` — Updated `_valid_span()` fixture to use `payload=None`; added `test_span_rejects_legacy_payload_id_field` (negative — extra='forbid' rejects removed field), `test_span_accepts_payload_dict` (positive round-trip), `test_span_payload_defaults_to_none` (default None).
- **Modified:** `tests/test_pipeline.py` — Added `_FakePool` / `_FakeConn` / `_FakeAcquireCtx` recorder fixtures (mirrors test_feedback_route.py pattern); added `db_pool` kwarg to `_build_pipeline`; added `test_pipeline_with_db_pool_inserts_traces_row` (asserts ALL 3 SQL ops fire AND trace_id arg consistent across them); added `test_pipeline_emits_payload_on_child_spans` (asserts payload contents per docs/trace-schema.md and root payload=None).

## Migration Drill Output

`docker compose run --rm migrate alembic upgrade head` (last lines):
```
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade 0001 -> 0002, add latency_ms, faithfulness, feedback_rating, estimated_cost_usd to traces.
```

`docker compose run --rm migrate alembic downgrade -1` (last lines):
```
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running downgrade 0002 -> 0001, add latency_ms, faithfulness, feedback_rating, estimated_cost_usd to traces.
```

`docker compose exec db psql -U tracer -d tracer_ai -c "\d traces"` (post-upgrade — abridged):
```
                             Table "public.traces"
       Column       |           Type           | Nullable
--------------------+--------------------------+----------
 id                 | uuid                     | not null
 started_at         | timestamp with time zone | not null
 ended_at           | timestamp with time zone |
 query_text         | text                     | not null
 root_span_id       | uuid                     | not null
 latency_ms         | integer                  |
 faithfulness       | real                     |
 feedback_rating    | smallint                 |
 estimated_cost_usd | real                     |
Indexes:
    "traces_pkey" PRIMARY KEY, btree (id)
    "traces_faithfulness_idx" btree (faithfulness)
    "traces_feedback_rating_idx" btree (feedback_rating)
    "traces_started_at_idx" btree (started_at DESC)
Check constraints:
    "traces_feedback_rating_chk" CHECK (feedback_rating IS NULL OR (feedback_rating = ANY (ARRAY['-1'::integer, 1])))
```

## Test Suite Output

`pytest tests/test_writer_protocol.py tests/test_pipeline.py -x -q` — 18 tests pass:
```
..................                                                       [100%]
```

New tests added:
- `tests/test_writer_protocol.py::test_span_rejects_legacy_payload_id_field` — payload_id raises ValidationError under extra='forbid'
- `tests/test_writer_protocol.py::test_span_accepts_payload_dict` — payload dict round-trips
- `tests/test_writer_protocol.py::test_span_payload_defaults_to_none` — omitting payload yields None
- `tests/test_pipeline.py::test_pipeline_with_db_pool_inserts_traces_row` — asserts INSERT INTO traces, UPDATE traces SET latency_ms, UPDATE traces SET estimated_cost_usd ALL fire on a complete cycle AND trace_id arg matches across all 3 (closure-capture verification)
- `tests/test_pipeline.py::test_pipeline_emits_payload_on_child_spans` — asserts payload contents per docs/trace-schema.md; root rag.request payload is None

## 0001 Untouched Confirmation

`git diff alembic/versions/0001_initial.py` produces zero lines — D-2.17 enforced.

## Decisions Made

- **Pre-commit ruff-format may rewrite newly-authored files.** Two commits (Task 1 and Task 3) initially failed because ruff-format reformatted the new files (line-length collapsing + structural reformatting). Re-staging and re-committing resolved cleanly. No use of `--no-verify`.
- **Test for legacy payload_id rejection intentionally references `payload_id`.** The plan listed `grep -c "payload_id" tests/test_writer_protocol.py returns 0` as an acceptance criterion, but the same plan's `<action>` block explicitly says "ensure one test passes `payload_id=uuid4()` and asserts `pydantic.ValidationError` is raised". The action wins (it documents the bug class to prevent regression) — see Deviations.
- **Closure-capture verification is a load-bearing test.** The new `test_pipeline_with_db_pool_inserts_traces_row` not only asserts each SQL op fires, but also that the trace_id argument matches across INSERT, UPDATE latency, and UPDATE cost — a single uuid4()-in-wrong-scope bug would cause silent FK drift on insert and orphan rows on UPDATE.

## Deviations from Plan

### Deviation 1 (Rule 4-equivalent — internal plan inconsistency, resolved by intent)

**Negative test for `payload_id` field references the field name to verify rejection.**
- **Found during:** Task 2 (Span field swap)
- **Issue:** Plan's `<action>` block requires a test that constructs `Span(..., payload_id=uuid4())` and asserts ValidationError. Plan's `<acceptance_criteria>` block requires `grep -c "payload_id" tests/test_writer_protocol.py` to return 0. These two requirements are mutually exclusive: the regression test can only exist if it references `payload_id`.
- **Resolution:** Honored the action block (added `test_span_rejects_legacy_payload_id_field` referencing `payload_id` in 3 places). The acceptance grep counts 3, not 0. The intent — the source `tracer_ai/tracer/writer.py` has 0 references to `payload_id` (verified) — is fully satisfied.
- **Files modified:** tests/test_writer_protocol.py
- **Verification:** `grep -c "payload_id" tracer_ai/tracer/writer.py` returns 0 (source clean); test asserts `pydantic.ValidationError` is raised on `payload_id=uuid4()`.
- **Committed in:** 9175a20 (Task 2 commit)

### Deviation 2 (Rule 3 — Blocking; tooling)

**docker compose path uses `infra/docker-compose.yml` not the project root.**
- **Found during:** Task 1 verify block (running `docker compose run --rm migrate alembic upgrade head`)
- **Issue:** The plan's `<verify>` block uses `docker compose run --rm migrate ...` without -f flag, but the compose file lives at `infra/docker-compose.yml`. The literal command fails with "no configuration file provided".
- **Fix:** Used `docker compose -f infra/docker-compose.yml run --rm migrate ...` for all migration verification. The verify block's intent (forward-roll-after-downgrade is clean) is satisfied verbatim.
- **Files modified:** none (tooling-only)
- **Verification:** Up/down/up cycle clean; `\d traces` shows all 4 new columns + indexes + CHECK constraint
- **Committed in:** N/A (no source change)

### Deviation 3 (Rule 3 — Blocking; tooling)

**Tests live outside the migrate container's mounted volumes.**
- **Found during:** Task 2 verify block
- **Issue:** The migrate container only mounts `tracer_ai/`, `alembic/`, `alembic.ini`, `pyproject.toml`, `uv.lock` — NOT `tests/`. Running `pytest tests/...` inside the migrate container fails with "file or directory not found".
- **Fix:** Added a one-shot `-v` mount for `tests/` (and for Task 3's import-cycle guard, also `infra/`). The mount uses double-slash `//c/...` to satisfy MSYS path translation on Windows.
- **Files modified:** none (tooling-only)
- **Verification:** All 18 tests pass; mypy --strict clean; ruff clean.
- **Committed in:** N/A

---

**Total deviations:** 3 (1 plan-internal-inconsistency resolved by intent; 2 tooling-blocking).
**Impact on plan:** Zero scope creep. All deviations are surface adjustments (path-flag, mount, single grep-vs-action conflict).

## Issues Encountered

- Two pre-commit ruff-format failures (Task 1 and Task 3 commits) — re-staged after the auto-format and committed cleanly on retry. No `--no-verify` used.
- pre-commit pytest run took several minutes the first time due to testmon rebuild; subsequent runs were fast.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- **Plan 04-02 (BoundedDropOldestQueue)** unblocked. The Span model + Pipeline are ready; queue is the next standalone unit.
- **Plan 04-03 (PostgresTraceWriter consumer task)** unblocked once Plan 02 ships — writer can call `INSERT INTO span_payloads` because Span.payload is the canonical payload field.
- **Plan 04-04 (read API endpoints)** unblocked — `traces.latency_ms / faithfulness / feedback_rating / estimated_cost_usd` columns exist in the schema; `TraceListItem` Pydantic shape from docs/api.md is contract-aligned.
- **Plan 04-05 (frontend Dashboard + waterfall)** can run in parallel with 04-04 once Plan 03 ships (per D-4.24).

## Self-Check: PASSED

Verified at execution end:

- File `alembic/versions/0002_traces_denorm.py` exists ✓
- File `tracer_ai/tracer/writer.py` modified (payload field present, payload_id removed) ✓
- File `tracer_ai/rag/pipeline.py` modified (asyncpg import, db_pool kwarg, INSERT INTO traces, UPDATE latency_ms, UPDATE estimated_cost_usd, 4 payload= sites) ✓
- File `tests/test_writer_protocol.py` modified (3 new tests, fixture updated) ✓
- File `tests/test_pipeline.py` modified (FakePool, 2 new tests, _build_pipeline kwarg) ✓
- Commit `289e21d` exists ✓
- Commit `9175a20` exists ✓
- Commit `a3d2c72` exists ✓
- 0001_initial.py byte-identical (`git diff` produces 0 lines) ✓

---
*Phase: 04-tracer-trace-explorer*
*Completed: 2026-05-06*
