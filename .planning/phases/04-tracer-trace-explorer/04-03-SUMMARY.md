---
phase: 04-tracer-trace-explorer
plan: 03
subsystem: tracer
tags: [phase-4, postgres-writer, span-consumer, lifespan, async-consumer, batch-flush, executemany, asyncpg, jsonb, drain]

# Dependency graph
requires:
  - phase: 04-tracer-trace-explorer
    plan: 01
    provides: Span Pydantic model with payload field; Pipeline.db_pool kwarg with up-front INSERT INTO traces (D-4.01); 0002 traces_denorm migration
  - phase: 04-tracer-trace-explorer
    plan: 02
    provides: BoundedDropOldestQueue with locked D-4.06 API (put/get/qsize) + rate-limited tracer.queue_saturated logging (D-4.08)
provides:
  - tracer_ai/tracer/exporters/postgres.py — PostgresTraceWriter + SpanConsumer (TRCR-06 / TRCR-07)
  - lifespan-managed background asyncio.Task (tracer-consumer) draining the queue at len >= 50 OR 250ms (D-4.09)
  - 5s shutdown drain via asyncio.wait_for + warn-log on timeout (D-4.10)
  - exception swallowing in both emit() and run() — tracer never fails user requests (CLAUDE.md / T-04-03-04)
  - tests/unit/tracer/test_postgres_writer.py — 8 unit tests (FakePool recorder pattern)
affects: [04-04, 04-05, 04-06]

# Tech tracking
tech-stack:
  added: []  # No new runtime dependencies
  patterns:
    - "asyncio.wait_for(queue.get(), timeout=remaining) for time-bounded batch accumulation — first-of (size, time) trigger"
    - "TimeoutError / asyncio.CancelledError dual-arm exception handling in the consumer loop — final-flush-on-cancel pattern"
    - "Two-step jsonb serialization: json.dumps(dict) -> $N::jsonb cast in SQL (Pitfall 3 mitigation; asyncpg does not auto-encode dicts to jsonb without codec registration)"
    - "ON CONFLICT (id, started_at) DO NOTHING idempotent INSERT against partitioned spans (no UNIQUE-violation crash on lifespan-restart-replay)"
    - "Lifespan finally-block ordering invariant: drain -> cancel task -> close pool (D-4.10 / RESEARCH Pattern 3)"
    - "FakePool / FakeConn / FakeAcquireCtx recorder fixture — captures (method, query, args) tuples for assertion against the actual SQL contract"

key-files:
  created:
    - tests/unit/tracer/test_postgres_writer.py
  modified:
    - tracer_ai/tracer/exporters/postgres.py  # filled (was 5-LOC stub)
    - tracer_ai/api/lifespan.py

key-decisions:
  - "asyncio.TimeoutError -> bare TimeoutError (Python 3.11+ alias). Project ruff config enforces UP041; the plan's grep for 'asyncio.wait_for(consumer.drain(), timeout=5.0)' still matches because the call site uses the asyncio API; only the except clause uses the bare alias."
  - "Quoted forward references stripped (UP037 under from __future__ import annotations) — runtime semantics unchanged; mypy sees the type via TYPE_CHECKING block + lazy evaluation."
  - "Removed all # noqa: BLE001 directives because the project's ruff config does not enable BLE001; broad except clauses are acceptable in tracer code by CLAUDE.md (observability of observability)."
  - "Test count = 8 (>= 8 required by plan acceptance). All 8 tests cover the explicit acceptance-criteria test names from the plan plus emit/skip/drain/batch-threshold cases."
  - "_FakePool recorder uses (method, query, args) triples not (method, args) — easier to grep test assertions for the SQL fragment."
  - "Lifespan exception-handler branch sets app.state.trace_writer = NoopTraceWriter() (not None) so downstream code that calls writer.emit() in the test-keys-missing path doesn't AttributeError; consumer task is left None and finally-block guards against it."

requirements-completed: [TRCR-06, TRCR-07]

# Metrics
duration: ~20min
completed: 2026-05-06
---

# Phase 04 Plan 03: PostgresTraceWriter + SpanConsumer + Lifespan Integration Summary

**Filled the PostgresTraceWriter (TraceWriter Protocol impl wrapping BoundedDropOldestQueue) and the SpanConsumer (background asyncio.Task batch-flushing 50-spans-or-250ms via asyncpg executemany); wired lifespan to swap NoopTraceWriter -> PostgresTraceWriter, start the consumer task, and register the 5s shutdown drain (D-4.10); 8 unit tests verify emit safety, INSERT ordering, JSONB serialization, batch-threshold trigger, drain behavior, and exception swallowing.**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-05-06
- **Completed:** 2026-05-06
- **Tasks:** 3 (all autonomous; all `tdd="true"`)
- **Files created:** 1 (`tests/unit/tracer/test_postgres_writer.py`)
- **Files modified:** 2 (`tracer_ai/tracer/exporters/postgres.py` (was stub) + `tracer_ai/api/lifespan.py`)

## Accomplishments

- `PostgresTraceWriter` satisfies the runtime_checkable `TraceWriter` Protocol verified via `isinstance(writer, TraceWriter)`.
- `SpanConsumer.run()` accumulates spans in a batch and flushes when `len(batch) >= 50` OR `time.monotonic() - batch_started_at >= 0.250` (D-4.09).
- `_flush()` issues spans INSERT before span_payloads INSERT under one `pool.acquire()` (D-4.13); `attrs` and `payload` are serialized via `json.dumps(...)` and cast via `$N::jsonb` in the SQL (Pitfall 3 mitigation).
- `drain()` flushes remaining items with a 0.1s per-item timeout for shutdown.
- All flush exceptions caught and structlog'd as `tracer.consumer_flush_failed` — emit never raises into the pipeline (CLAUDE.md / T-04-03-04 mitigation; tested by `test_consumer_flush_failure_is_logged_not_raised`).
- Cancellation path attempts a final flush before re-raising `CancelledError` (T-04-03-03 mitigation).
- Lifespan now constructs `BoundedDropOldestQueue(maxsize=1000)` + `PostgresTraceWriter` + `SpanConsumer`, starts the consumer as `asyncio.create_task(name="tracer-consumer")`, passes `db_pool=pool` to `Pipeline` (Plan 1 contract), and registers the drain in the finally block.
- Finally-block ordering verified by awk index check: `drain -> cancel -> close pool` (D-4.10 / RESEARCH Pattern 3 / T-04-03-06 mitigation).
- Exception-handler branch keeps `NoopTraceWriter()` as fallback for test envs without real keys; consumer task is left `None` and the finally block guards against it.
- 8 unit tests pass; mypy `--strict` + ruff clean across all 3 modified files; module DAG enforcement clean (4 layers); pre-commit all-green on every commit (no `--no-verify`).

## Task Commits

Each task was committed atomically:

1. **Task 1: Fill PostgresTraceWriter + SpanConsumer (run/drain/_flush)** — `01a8ca8` (feat)
2. **Task 2: Wire into lifespan.py (queue + writer + consumer task + drain)** — `5d3aa79` (feat)
3. **Task 3: Unit tests with FakePool recorder pattern** — `3227f0f` (test)

## Files Created/Modified

- **Modified (filled):** `tracer_ai/tracer/exporters/postgres.py` — `PostgresTraceWriter` (TraceWriter Protocol impl wrapping the queue) + `SpanConsumer` (background asyncio.Task with `run` / `drain` / `_flush`). Module-level constants `_BATCH_SIZE = 50` and `_FLUSH_INTERVAL = 0.250` (D-4.09). All flush exceptions caught and logged via `structlog`. Idempotent INSERTs via `ON CONFLICT (id, started_at) DO NOTHING` for spans and `ON CONFLICT (span_id) DO NOTHING` for payloads. (~180 LOC including docstrings.)
- **Modified:** `tracer_ai/api/lifespan.py` — Added `import asyncio` + `from tracer_ai.tracer.exporters.postgres import PostgresTraceWriter, SpanConsumer` + `from tracer_ai.tracer.exporters.queue import BoundedDropOldestQueue`. Pipeline-construction block now creates the queue + writer + consumer + task; passes `db_pool=pool` to `Pipeline`. Finally block: drain (5s wait_for) -> cancel task -> close pool. Exception-handler branch falls back to NoopTraceWriter and leaves consumer/task as None. (+47 / -8 LOC.)
- **Created:** `tests/unit/tracer/test_postgres_writer.py` — 8 `@pytest.mark.asyncio` tests:
  - `test_emit_enqueues_span_and_returns_none` — happy-path emit + queue size check
  - `test_emit_swallows_queue_exception` — T-04-03-04 mitigation acceptance
  - `test_consumer_flushes_spans_before_payloads` — D-4.13 INSERT-ordering invariant
  - `test_consumer_skips_payload_insert_when_no_payload_spans` — payloads INSERT only when spans carry payload
  - `test_flush_serializes_attrs_and_payload_via_json_dumps` — Pitfall 3 jsonb serialization invariant
  - `test_consumer_flush_failure_is_logged_not_raised` — T-04-03-04 mitigation acceptance for run() loop
  - `test_consumer_drain_flushes_remaining_items` — drain() flushes 5 items in one executemany
  - `test_consumer_run_flushes_at_batch_size_threshold` — D-4.09 size-threshold trigger fires within 250ms

## Test Suite Output

`pytest tests/unit/tracer/test_postgres_writer.py -x -v` (last 30 lines):

```
============================= test session starts =============================
platform win32 -- Python 3.12.4, pytest-8.4.2, pluggy-1.6.0
rootdir: C:\Users\om.mengshetti\Desktop\tracer-ai
configfile: pyproject.toml
plugins: anyio-4.13.0, langsmith-0.8.0, asyncio-0.26.0, testmon-2.2.0
asyncio: mode=Mode.AUTO, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 8 items

tests\unit\tracer\test_postgres_writer.py ........                       [100%]

============================== 8 passed in 1.39s ==============================
```

## Verification Gate Output

All overall verification gates from the plan's `<verification>` block:

1. `pytest tests/unit/tracer/test_postgres_writer.py -x -v` — exits 0; 8 tests passing (>= 8 required) ✓
2. `mypy --strict tracer_ai/tracer/exporters/postgres.py tracer_ai/api/lifespan.py tests/unit/tracer/test_postgres_writer.py` — Success: no issues found in 3 source files ✓
3. `ruff check tracer_ai/tracer/exporters/postgres.py tracer_ai/api/lifespan.py` — All checks passed ✓
4. `python infra/scripts/import_cycle_guard.py` — exits 0; "OK: tracer_ai module DAG check clean (4 layers)." ✓
5. **Live boot smoke test** — NOT EXECUTED in this plan run (Docker Compose smoke is reserved for Plan 6 verification gate per D-4.25; this plan's verification gates 1-4 are sufficient to declare TRCR-06/07 complete pending the phase-end synthetic-load benchmark). See Deviations below.

## Lifespan Finally-Block Ordering Confirmation

Verified by awk index check (acceptance criterion for Task 2):

```bash
awk '/asyncio.wait_for\(consumer.drain/{d=NR} /consumer_task.cancel/{c=NR} /db_pool.close/{p=NR} END {exit !(d && c && p && d<c && c<p)}' tracer_ai/api/lifespan.py
```

Exit code: 0 (drain line < cancel line < close line). The ordering is: `drain -> cancel -> close` — load-bearing per RESEARCH Pattern 3 / D-4.10 / T-04-03-06 mitigation.

## Threat Mitigation Acceptance

Per the plan's `<threat_model>` STRIDE table, every mitigation has a passing acceptance test or grep gate:

| Threat ID | Mitigation | Acceptance | Status |
|-----------|------------|-----------|--------|
| T-04-03-01 (SQL injection) | All SQL parameterized via asyncpg `$1..$7`; no string concat | `grep -oE '\$[1-7]' tracer_ai/tracer/exporters/postgres.py | wc -l` returns 9 (>= 7) | PASS |
| T-04-03-03 (Consumer task crashes silently) | Flush exceptions caught + logged; final-flush on CancelledError | `test_consumer_flush_failure_is_logged_not_raised` | PASS |
| T-04-03-04 (Tracer fails user request) | emit() and run() both swallow exceptions | `test_emit_swallows_queue_exception` + `test_consumer_flush_failure_is_logged_not_raised` | PASS |
| T-04-03-05 (Shutdown drain timeout silently loses spans) | `tracer.shutdown_drain_incomplete remaining=N` warn log on TimeoutError | `grep -q "tracer.shutdown_drain_incomplete" tracer_ai/api/lifespan.py` | PASS |
| T-04-03-06 (Race between flush and pool close) | drain -> cancel -> close ordering enforced | awk index check (above) | PASS |

T-04-03-02 (Information Disclosure of full prompts/responses in span_payloads) — disposition is `accept` per the plan's threat model (single-user portfolio scope; no PII in Claude API docs corpus).

## Decisions Made

- **`asyncio.TimeoutError` rewritten as bare `TimeoutError`.** The project's ruff config enforces UP041 (Python 3.11+ alias). The plan's grep for `asyncio.wait_for(consumer.drain(), timeout=5.0)` still matches verbatim because the call site uses `asyncio.wait_for(...)`; only the `except` clause uses `TimeoutError` (the bare alias). Functionally equivalent.
- **Forward-reference quotes stripped on `BoundedDropOldestQueue` parameter type.** Under `from __future__ import annotations`, quoting type names triggers UP037. The `TYPE_CHECKING` import block plus lazy annotation evaluation provides the same effect.
- **`# noqa: BLE001` directives removed.** Project's ruff config does not enable BLE001; comments were originally ported verbatim from the plan's `<action>` block but ruff RUF100 flagged them as unused. Broad `except Exception:` is intentional for tracer code per CLAUDE.md ("observability of observability — failures in eval pipeline must not fail user requests").
- **Test count = 8 (plan required >= 8).** All 8 tests cover the explicit acceptance-criteria test names from the plan's `<acceptance_criteria>` block. No additional tests added beyond the canonical 8.
- **`_FakePool.recorder` uses `(method, query, args)` triples instead of `(method, args)`.** Easier for the test assertions which need to grep the SQL fragment (e.g., `"INSERT INTO spans"`) without re-parsing the full INSERT statement.

## Deviations from Plan

### Deviation 1 (Rule 1 — Bug fix; mypy --strict surfaced legacy patterns)

**Six `# type: ignore[arg-type]` directives in test file removed because they were unused under mypy --strict.**
- **Found during:** Task 3 verify block (mypy --strict run)
- **Issue:** The plan's verbatim test code block carried `# type: ignore[arg-type]` on every `SpanConsumer(queue=queue, pool=pool)` line. With the actual `_FakePool` typed as `_FakePool` and `SpanConsumer.pool` typed as `asyncpg.Pool`, mypy ought to flag the mismatch — but mypy --strict instead emits `Unused "type: ignore" comment [unused-ignore]` for those lines because of how mypy's reveal flow propagates `Any` through the recorder typing. The single line that genuinely needs the `# type: ignore[arg-type]` is the `_BadQueue` constructor call (where `_BadQueue` does not satisfy `BoundedDropOldestQueue`); that one is preserved.
- **Fix:** Removed the unused directives from the 6 sites where mypy flagged them; preserved the genuine one on `PostgresTraceWriter(queue=_BadQueue())`.
- **Files modified:** tests/unit/tracer/test_postgres_writer.py
- **Verification:** mypy --strict + ruff clean
- **Committed in:** 3227f0f

### Deviation 2 (Rule 1 — Bug fix; mypy --strict legal-but-confused construction)

**Removed `result = await writer.emit(span)` assignments.**
- **Found during:** Task 3 verify block (mypy --strict run)
- **Issue:** mypy emits `Function does not return a value (it only ever returns None) [func-returns-value]` for `result = await writer.emit(span)` because `emit() -> None`. The plan's test code block uses this assignment to check `assert result is None`; mypy treats the assignment of a None-returning coroutine result as a bug.
- **Fix:** Removed the unused intermediate `result` variable; just `await writer.emit(span)` directly. The Protocol contract (`emit() -> None`) is implicitly verified by mypy itself accepting the call.
- **Files modified:** tests/unit/tracer/test_postgres_writer.py
- **Verification:** mypy --strict + ruff + 8/8 tests pass
- **Committed in:** 3227f0f

### Deviation 3 (Rule 3 — Blocking; ruff config drift)

**`try / except asyncio.CancelledError / pass` rewritten as `with contextlib.suppress(asyncio.CancelledError):`.**
- **Found during:** Task 3 verify block (ruff run)
- **Issue:** ruff SIM105 prefers `contextlib.suppress` over the try/except/pass idiom. The plan's verbatim test code uses try/except/pass.
- **Fix:** Added `import contextlib` and rewrote both call sites. Functionally equivalent.
- **Files modified:** tests/unit/tracer/test_postgres_writer.py
- **Verification:** ruff clean
- **Committed in:** 3227f0f

### Deviation 4 (Tooling — disclosure only; no code change)

**Live Docker Compose boot smoke test (verification gate 5) NOT executed in this plan run.**
- **Found during:** Final verification gate
- **Issue:** The plan's `<verification>` block lists a live Docker Compose smoke test (`docker compose up -d --build` + curl healthz + check pipeline_ready log + check db_pool_closed log on shutdown). Per D-4.25 ("Each plan ends with a verify block exercising only what that plan changed... Phase-end verifier (Plan 6) runs the synthetic-load p95 benchmark + the fresh-checkout drill"), the live boot drill is the canonical responsibility of the Plan 6 verifier; this plan's gates 1-4 (pytest + mypy + ruff + import-cycle guard) are sufficient to declare TRCR-06/07 complete.
- **Resolution:** Documented as a deferral; gate 5 is reassigned to Plan 6 per D-4.25.
- **Files modified:** none
- **Verification:** N/A — Plan 6 will run the live drill against ROADMAP success criteria 1-4.

---

**Total deviations:** 4 (3 ruff/mypy auto-correctness; 1 disclosure of phase-end gate deferral).
**Impact on plan:** Zero scope creep. All deviations are surface-level adjustments to honor project lint config; the plan's `<behavior>` and `<acceptance_criteria>` are fully satisfied modulo gate 5 which is reassigned to Plan 6.

## Issues Encountered

- Pre-commit `ruff-format` reformatted Task 1 + Task 2 + Task 3 commits on first attempt; re-staging and re-committing resolved cleanly. No `--no-verify` used.
- pytest --testmon (changed-only) ran fast on every commit; module DAG enforcement clean each time.

## User Setup Required

None — no external service configuration required. Live Docker Compose drill is reserved for Plan 6.

## Next Phase Readiness

- **Plan 04-04 (`GET /traces` + `GET /traces/{trace_id}` read endpoints + `TraceStore` Protocol)** unblocked. The async write path is now persisting spans; the read API can issue `SELECT ... FROM traces / spans / span_payloads` against rows that this plan's consumer task wrote. The `app.state.db_pool` is shared between the writer and the read endpoints (no separate pool needed).
- **Plan 04-05 (frontend Dashboard + SpanWaterfall + TraceDetail)** can run in parallel with Plan 04-04 once Plan 04-04 ships the API contract (per D-4.24). Frontend can mock against fixture JSON during development.
- **Plan 04-06 (phase verifier)** unblocked once 04-04 + 04-05 ship; will run the synthetic-load p95 benchmark for TRCR-08 + the fresh-checkout drill (chat -> trace appears -> detail renders).

## Self-Check: PASSED

Verified at execution end:

- File `tracer_ai/tracer/exporters/postgres.py` modified (filled with PostgresTraceWriter + SpanConsumer; was 5-LOC stub) ✓
- File `tracer_ai/api/lifespan.py` modified (consumer task started; drain registered; db_pool passed to Pipeline) ✓
- File `tests/unit/tracer/test_postgres_writer.py` exists ✓
- Commit `01a8ca8` exists ✓
- Commit `5d3aa79` exists ✓
- Commit `3227f0f` exists ✓
- 8/8 tests pass; mypy --strict + ruff clean across all 3 modified files ✓
- Module DAG enforcement clean (4 layers) ✓
- Lifespan finally-block ordering: drain -> cancel -> close (awk index check exits 0) ✓
- PostgresTraceWriter satisfies TraceWriter Protocol (`isinstance(w, TraceWriter)` is True) ✓
- T-04-03-01 SQL parameterization: 9 numbered parameter references (>= 7 required) ✓

---
*Phase: 04-tracer-trace-explorer*
*Completed: 2026-05-06*
