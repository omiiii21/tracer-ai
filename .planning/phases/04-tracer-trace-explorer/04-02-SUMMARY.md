---
phase: 04-tracer-trace-explorer
plan: 02
subsystem: tracer
tags: [phase-4, queue, async, backpressure, drop-oldest, asyncio, structlog, rate-limited-log]

# Dependency graph
requires:
  - phase: 04-tracer-trace-explorer
    plan: 01
    provides: Span Pydantic model with payload field; Pipeline.db_pool kwarg with up-front INSERT INTO traces (D-4.01); 0002 traces_denorm migration
provides:
  - tracer_ai/tracer/exporters/queue.py — BoundedDropOldestQueue with locked D-4.06 API (put/get/qsize)
  - drop-oldest-under-saturation invariant (D-4.05) — async-safe, deterministic under concurrent producers
  - rate-limited tracer.queue_saturated structured log (D-4.08) — at most once per 1s window; counter resets per period
  - tests/unit/tracer/__init__.py + tests/unit/tracer/test_queue.py — 9 async unit tests covering the full D-4.06 contract + D-4.08 rate-limit
affects: [04-03]

# Tech tracking
tech-stack:
  added: []  # No new runtime dependencies; structlog + asyncio + collections.deque already in stack
  patterns:
    - "collections.deque + asyncio.Lock + asyncio.Event composite pattern — deterministic ordering under concurrent producers; eliminates put_nowait+except+get_nowait race window of asyncio.Queue"
    - "_not_empty.clear() under lock AFTER confirming deque is empty — load-bearing correctness invariant; releasing lock before clearing event would race a put() into setting it"
    - "get() loops on spurious wake — re-await event under lock if deque is empty after acquire (defensive against future producers that touch the event without appending)"
    - "Rate-limited structured log via time.monotonic() drift comparison — emits log + resets counter atomically when window opens; counter accumulates silently while window closed"
    - "Unit-test patch via unittest.mock.patch on module-level log instance — module-imported singletons are patchable by full dotted path: tracer_ai.tracer.exporters.queue.log"
    - "Direct private-attribute test for deterministic invariants — accessing q._dropped_count to verify reset is acceptable for unit-test of internal correctness invariants (alternative is patching time.monotonic which is more fragile)"

key-files:
  created:
    - tracer_ai/tracer/exporters/queue.py
    - tests/unit/tracer/__init__.py
    - tests/unit/tracer/test_queue.py
  modified: []

key-decisions:
  - "BoundedDropOldestQueue API matches D-4.06 verbatim: __init__(maxsize), async put(item)->bool, async get()->Any, qsize()->int. The plan's <interfaces> block was a hard contract — every signature, every return-type, every Optional matched"
  - "Rate-limited saturation log fires at most once per 1s window; counter resets per period (D-4.08). First drop in cold queue (last_log_at=0.0) ALWAYS fires immediately because now - 0.0 >= 1.0; subsequent drops within 1s accumulate into _dropped_count silently"
  - "qsize() is a lock-free read snapshot — len(deque) is atomic in CPython; no contention penalty on the consumer's monitoring path"
  - "Test count: 9 (>= 8 required by plan acceptance criteria); plan's 8 explicit cases + 1 added (FIFO ordering) per the plan's own action block which lists 9 tests"
  - "test_log_counter_resets_after_emission accesses q._dropped_count directly — chosen over patching time.monotonic per plan note: 'this is acceptable for unit tests of the queue's invariants (the alternative is patching time.monotonic which is more fragile)'"

patterns-established:
  - "Async queue with both producer rate-limit logging AND drop-oldest backpressure — applicable to any future async pipeline component that must never block the request path (e.g., Phase 5 EVAL-04 BackgroundTasks judge dispatch may reuse this for capacity control)"
  - "Module-level log singleton patching pattern via patch('module.path.log') — same idiom used here is reusable for any future module that emits structured logs and needs to be unit-tested without log noise (or with assertion on call args)"
  - "@pytest.mark.asyncio + asyncio.create_task + asyncio.wait_for with bounded timeout = standard async pytest cadence in this repo (mirrors tests/test_writer_protocol.py); no monkeypatch fixture needed for env-isolated modules like queue.py"

requirements-completed: [TRCR-06]

# Metrics
duration: ~10min
completed: 2026-05-06
---

# Phase 04 Plan 02: BoundedDropOldestQueue + Saturation Logging Summary

**Custom bounded async queue (`tracer_ai/tracer/exporters/queue.py`, 83 LOC) wraps `collections.deque` with `asyncio.Lock` + `asyncio.Event`, drops the oldest item under saturation (D-4.05/06/07), and rate-limits the `tracer.queue_saturated` structured log to once-per-1s (D-4.08); 9 async unit tests verify the locked D-4.06 API + concurrent-producer determinism + rate-limit invariant.**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-05-06
- **Completed:** 2026-05-06
- **Tasks:** 2 (both autonomous; both `tdd="true"` — RED+GREEN combined into single commits because the plan provided verbatim implementation; queue.py was implemented + verified by Task 1's automated checks before tests in Task 2)
- **Files created:** 3 (1 source, 2 test)
- **Files modified:** 0

## Accomplishments

- `BoundedDropOldestQueue` exports the locked D-4.06 API verbatim: `__init__(maxsize)`, `async put(item) -> bool`, `async get() -> Any`, `qsize() -> int`.
- Drop-oldest invariant verified deterministically under 5 concurrent producers at capacity (T-04-02-03 mitigation acceptance test passes).
- Rate-limited saturation log fires at most once per 1s window; counter resets per log period; structured event name is exactly `tracer.queue_saturated` (T-04-02-02 mitigation acceptance test passes).
- `get()` awaits when empty and unblocks immediately when `put()` runs (no polling); test verifies the `_not_empty.clear()` invariant by asserting subsequent `get()` after drain blocks via `asyncio.wait_for(timeout=0.1)` raising `TimeoutError`.
- mypy `--strict` and ruff clean on both files; pre-commit hooks all green on both commits (no `--no-verify`).
- Module DAG enforcement guard passes — queue.py imports only `asyncio`, `time`, `collections`, `typing`, `structlog`; no `api/` or `rag/` imports (TRCR-05 layering preserved).

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement BoundedDropOldestQueue with rate-limited saturation logging** — `2258839` (feat) — adds `tracer_ai/tracer/exporters/queue.py` (83 LOC).
2. **Task 2: Unit tests for BoundedDropOldestQueue covering drop-oldest, ordering, get-awaits, qsize, and rate-limited log** — `3fd37b6` (test) — adds `tests/unit/tracer/__init__.py` (empty package marker) + `tests/unit/tracer/test_queue.py` (148 LOC, 9 test cases).

## Files Created/Modified

- **Created:** `tracer_ai/tracer/exporters/queue.py` — `BoundedDropOldestQueue` class implementing D-4.06 locked API. Drop-oldest under saturation (D-4.05); rate-limited saturation log (D-4.08); `_not_empty.clear()` correctness invariant under lock after empty-check; `get()` loops on spurious wake. 83 LOC total (target was ~50 LOC; the +33 LOC is from module + class docstrings cited at acceptance — pure documentation overhead, no implementation drift).
- **Created:** `tests/unit/tracer/__init__.py` — Empty package marker for `pytest --collect-only` package discovery.
- **Created:** `tests/unit/tracer/test_queue.py` — 9 `@pytest.mark.asyncio` test cases:
  - `test_put_returns_true_when_queue_has_space` — happy-path put returns True
  - `test_put_drops_oldest_and_returns_false_when_full` — drop-oldest invariant + return-value contract; drains and verifies the surviving items are the newer ones
  - `test_get_awaits_until_item_available` — get() blocks until producer puts (no polling); `asyncio.wait_for(timeout=1.0)` confirms unblock latency is bounded
  - `test_qsize_reports_current_depth` — qsize accuracy across put/get
  - `test_concurrent_producers_at_capacity_drop_oldest_deterministically` — 5 concurrent producers at capacity all return False; surviving 3 items are all from the `new_*` set (T-04-02-03 acceptance)
  - `test_get_clears_not_empty_event_when_deque_emptied` — `_not_empty.clear()` correctness; subsequent get() blocks via TimeoutError
  - `test_saturation_log_fires_at_most_once_per_second` — D-4.08 rate-limit; 3 drops within 1s window produce exactly 1 warning call (T-04-02-02 acceptance)
  - `test_log_counter_resets_after_emission` — after a log emit, `_dropped_count` resets to 0; verified by setting `_last_log_at` 2s in the past to force the window open
  - `test_fifo_ordering_preserved_across_puts_and_gets` — FIFO invariant on a non-saturated queue

## Test Suite Output

```
$ uv run pytest tests/unit/tracer/test_queue.py -x -v
============================= test session starts =============================
platform win32 -- Python 3.12.4, pytest-8.4.2, pluggy-1.6.0
configfile: pyproject.toml
plugins: anyio-4.13.0, langsmith-0.8.0, asyncio-0.26.0, testmon-2.2.0
asyncio: mode=Mode.AUTO, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 9 items

tests\unit\tracer\test_queue.py .........                                [100%]

============================== 9 passed in 0.47s ==============================
```

Test runtime (slowest-10):
```
0.11s call     tests/unit/tracer/test_queue.py::test_get_clears_not_empty_event_when_deque_emptied
0.06s call     tests/unit/tracer/test_queue.py::test_get_awaits_until_item_available
(8 durations < 0.005s hidden.)
9 passed in 0.36s
```

## LOC Count

```
$ wc -l tracer_ai/tracer/exporters/queue.py tests/unit/tracer/test_queue.py
  83 tracer_ai/tracer/exporters/queue.py    (target ~50; overrun is pure docstring)
 148 tests/unit/tracer/test_queue.py
 231 total
```

The queue source LOC is 83 — slightly above the plan's ~50 target. The +33 LOC overrun is entirely documentation:
- Module docstring (lines 1-15): 15 lines
- Class docstring (lines 38-46): 9 lines
- Method docstrings (lines 49-50, 73-74, 81-82): ~8 lines

The implementation body itself (`__init__` + `put` + `get` + `qsize`) is ~30 LOC, on-target. No dead code; no implementation drift.

## Verification Gate Output

All 5 overall verification gates from the plan's `<verification>` block:

1. `pytest tests/unit/tracer/test_queue.py -x -v` — exits 0 with 9 tests passing (>= 8 required) ✓
2. `mypy --strict tracer_ai/tracer/exporters/queue.py tests/unit/tracer/test_queue.py` — Success: no issues found ✓
3. `ruff check tracer_ai/tracer/exporters/queue.py tests/unit/tracer/test_queue.py` — All checks passed ✓
4. `python -c "from tracer_ai.tracer.exporters.queue import BoundedDropOldestQueue; print(BoundedDropOldestQueue.__doc__)"` — exits 0; prints "Bounded queue that drops the OLDEST item when full (D-4.05/D-4.06/D-4.07)..." ✓
5. `python infra/scripts/import_cycle_guard.py` — exits 0; "OK: tracer_ai module DAG check clean (4 layers)." ✓

(Note: the plan referenced `infra/import_cycle_guard.py`; the actual script lives at `infra/scripts/import_cycle_guard.py` — same script, full path used. This matches the established Phase 2 path; the plan's path is shorthand. See Deviation 1 below.)

## Threat Mitigation Acceptance

Per the plan's `<threat_model>` STRIDE table, every mitigation has a passing acceptance test:

| Threat ID | Mitigation | Acceptance Test | Status |
|-----------|------------|-----------------|--------|
| T-04-02-02 (Log flooding from per-event saturation logs) | Rate-limited log (D-4.08): at most once per 1s window | `test_saturation_log_fires_at_most_once_per_second` | PASS |
| T-04-02-03 (Race between concurrent put() under saturation) | `asyncio.Lock` serializes mutations; deterministic drop-oldest | `test_concurrent_producers_at_capacity_drop_oldest_deterministically` | PASS |
| T-04-02-04 (Sensitive payload contents logged in saturation event) | Log only emits `dropped`, `window`, `queue_depth` — NOT item content | grep verifies log statement does NOT include item content | PASS |

T-04-02-01 (Burst trace writes saturating queue) — disposition is `mitigate` via the drop-oldest design itself; no acceptance test is required (this is the design intent verified by the entire suite).

## Decisions Made

- **Both tasks committed in RED+GREEN-combined form rather than separate RED-fail / GREEN-pass commits.** The plan provides the queue implementation verbatim from PATTERNS.md, so a RED gate (commit a failing test before implementation) would have required temporarily creating an empty stub file, committing failing tests, then re-committing the implementation. The plan's own structure (Task 1 = source, Task 2 = tests) embeds this decision: Task 1 verifies via grep + import-only checks (which an empty stub couldn't pass); Task 2 verifies via pytest. The committed sequence (Task 1 source → Task 2 tests) follows the plan's task order and produces a green pre-commit on every commit.
- **9 tests instead of 8.** The plan's `<acceptance_criteria>` requires `>= 8` tests; the action block lists 9 (including `test_fifo_ordering_preserved_across_puts_and_gets`). Implemented all 9 — FIFO ordering is a load-bearing invariant worth its own test even on the non-saturated path.
- **`test_log_counter_resets_after_emission` accesses `q._dropped_count` directly.** The plan explicitly endorses this in its action block: "We test the internal `_dropped_count` and `_last_log_at` attributes directly... this is acceptable for unit tests of the queue's invariants (the alternative is patching `time.monotonic` which is more fragile)." Honored verbatim.

## Deviations from Plan

### Deviation 1 (Rule 3 — Blocking; tooling)

**Import cycle guard script lives at `infra/scripts/import_cycle_guard.py`, not `infra/import_cycle_guard.py` referenced by the plan's `<verification>` block.**
- **Found during:** Final verification gate run (step 5)
- **Issue:** The plan's verification block runs `python infra/import_cycle_guard.py`, but the actual script path is `infra/scripts/import_cycle_guard.py` (the canonical Phase 2 location).
- **Fix:** Used `python infra/scripts/import_cycle_guard.py` for the verification gate. Same script, same exit-code semantics; only the path differs.
- **Files modified:** none (tooling-only)
- **Verification:** Script exits 0 with output "OK: tracer_ai module DAG check clean (4 layers)."

### Deviation 2 (Documentation overhead — not a true deviation, but disclosed for SUMMARY accuracy)

**queue.py is 83 LOC, target was ~50 LOC.**
- **Found during:** Final LOC count
- **Issue:** Module docstring (15 lines) + class docstring (9 lines) + method docstrings (~8 lines) account for the +33 LOC over target.
- **Resolution:** No code change needed. Implementation body is ~30 LOC (4 methods); docstrings are pure documentation per CLAUDE.md "meaningful docstrings on public functions only" — these are public-facing and meaningful (cite the D-4.05/06/07/08 decisions they encode).
- **Files modified:** none

---

**Total deviations:** 2 (1 tooling-blocking; 1 LOC-overhead disclosure).
**Impact on plan:** Zero scope creep. Both deviations are surface-level disclosures.

## Issues Encountered

- None. Both pre-commit runs passed first-try (no ruff-format reformatting; no `--no-verify` used).

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- **Plan 04-03 (PostgresTraceWriter + SpanConsumer + lifespan integration)** unblocked. The queue module is ready for `PostgresTraceWriter(queue=BoundedDropOldestQueue(maxsize=1000))` instantiation. Lifespan handler can wrap consumer.run() in an `asyncio.create_task`. SpanConsumer can call `await self._queue.get()` in its loop and `self._queue.qsize()` in its drain check.
- **Plan 04-04 (read API endpoints `GET /traces` + `GET /traces/{trace_id}`)** runs after Plan 04-03 — independent of queue mechanics; consumes the same asyncpg pool.
- **Plan 04-05 (frontend Dashboard + SpanWaterfall + TraceDetail)** can run in parallel with Plan 04-04 once Plan 04-03 ships (per D-4.24).

## Self-Check: PASSED

Verified at execution end:

- File `tracer_ai/tracer/exporters/queue.py` exists ✓
- File `tests/unit/tracer/__init__.py` exists ✓
- File `tests/unit/tracer/test_queue.py` exists ✓
- Commit `2258839` exists ✓
- Commit `3fd37b6` exists ✓
- 9 tests pass; mypy --strict + ruff clean ✓
- Module DAG enforcement clean (4 layers) ✓
- Pre-commit all-green on both commits ✓

---
*Phase: 04-tracer-trace-explorer*
*Completed: 2026-05-06*
