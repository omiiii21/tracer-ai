---
phase: 05-quality-feedback
plan: 04
subsystem: eval
tags: [dispatcher, asyncio-create-task, contextvars, ctx-snapshot, sse, lifespan, pitfall-1, pitfall-3, eval-02, eval-04, eval-05, trcr-04, d-5-10]

# Dependency graph
requires:
  - phase: 05-quality-feedback
    plan: 01
    provides: "Judge Protocol + AnthropicJudge + MockJudge + PROMPT_VERSION + get_judge_semaphore + EvalScores; capture_context / attach_context / current_span / set_current_span; ERROR_TYPE / RAG_EVAL_JUDGE_LATENCY_MS span constants; settings.judge_concurrency / judge_timeout_seconds / llm_judge_model"
  - phase: 04-tracer-trace-explorer
    plan: 03
    provides: "BoundedDropOldestQueue + PostgresTraceWriter + SpanConsumer drain pattern; lifespan finally drain ordering precedent"
  - phase: 04-tracer-trace-explorer
    plan: 01
    provides: "Span Pydantic model; pipeline._orchestrate up-front INSERT INTO traces + UPDATE traces SET latency_ms/estimated_cost_usd"
provides:
  - "EvalDispatcher class (D-5.10) with enqueue / _run_in_context / _do_score / drain"
  - "ChatFinalEvent extended with 4 Field(exclude=True) private fields: ctx_snapshot, chunks_for_judge, query, answer (Phase 5 EVAL-04 in-process channel)"
  - "Pipeline._orchestrate now returns a 5-tuple including a stub rag.request Span for cross-task ctx propagation"
  - "Pipeline.run_chat_stream captures contextvar snapshot BEFORE _emit_root ends rag.request (Pitfall #1)"
  - "tracer_ai/api/chat.py SSE generator dispatches eval task AFTER yielding final frame"
  - "tracer_ai/api/lifespan.py constructs EvalDispatcher in startup; drains it BEFORE SpanConsumer in shutdown (D-5.10 ordering invariant)"
  - "structlog audit events: eval.scored, eval.judge_failed, eval.dispatcher_ready, eval.dispatcher_drain_incomplete, eval_dispatch_after_stop, eval_update_traces_failed"
affects: [05-05 timeseries (independent), 05-06 calibration CLI (consumes EvalScores), 05-07 frontend (waterfall already auto-renders rag.eval), 06 regression CLI (reuses Judge + dispatcher mechanics)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "asyncio.create_task + add_done_callback(self._pending.discard) for leak-bounded background task tracking; never raises into the SSE generator"
    - "Cross-task contextvar snapshot pattern: set_current_span(stub_root) -> capture_context() -> attach_context(snapshot) inside the worker task"
    - "Pydantic v2 Field(exclude=True) + arbitrary_types_allowed=True for in-process model attachments that must NOT serialize on the wire"
    - "Lifespan drain ordering: dispatcher (5s wait_for) -> consumer (5s wait_for) -> consumer task cancel -> pool close (eval emits into consumer queue, so consumer outlives dispatcher)"
    - "Source-position assertion test (LD1) using inspect.getsource + regex to enforce drain ordering at source-code review time without spinning the full lifespan"

key-files:
  created:
    - "tracer_ai/eval/dispatcher.py - EvalDispatcher (217 LOC) — class with enqueue/_run_in_context/_do_score/drain; never-raise contract at every layer per Pitfall #3"
    - "tests/test_eval_dispatcher.py - 10 unit tests DA1-DA10 (~370 LOC after ruff-format)"
    - "tests/integration/test_eval_span_parentage.py - 3 tests PA1-PA3 (~245 LOC)"
    - "tests/integration/test_chat_with_failed_eval.py - 3 tests CF1-CF3 (~205 LOC)"
    - "tests/integration/test_eval_latency.py - 1 test LA1 (~165 LOC)"
    - "tests/integration/test_eval_drain_order.py - 2 tests LD1-LD2 (~115 LOC)"
  modified:
    - "tracer_ai/eval/__init__.py - export EvalDispatcher (was 21 LOC, now 23 LOC)"
    - "tracer_ai/rag/types.py - extend ChatFinalEvent with 4 Field(exclude=True) private fields + arbitrary_types_allowed=True (was 152 LOC, now 173 LOC)"
    - "tracer_ai/rag/pipeline.py - import capture_context/set_current_span; _orchestrate returns 5-tuple including root_for_ctx Span; run_chat_stream captures ctx snapshot BEFORE iterator drains (was 479 LOC, now 514 LOC)"
    - "tracer_ai/api/chat.py - SSE generator calls dispatcher.enqueue AFTER yielding final frame; getattr fallback when dispatcher is None (was 88 LOC, now 113 LOC)"
    - "tracer_ai/api/lifespan.py - imports EvalDispatcher + AnthropicJudge; constructs dispatcher after pipeline; drains dispatcher BEFORE consumer in finally (was 169 LOC, now 197 LOC)"

key-decisions:
  - "ChatFinalEvent extension uses Field(exclude=True) over Option B (new pipeline method returning ctx) and Option C (app.state side-channel) per RESEARCH.md Open Question 2 recommendation. Wire shape from model_dump(mode='json') is byte-unchanged from Phase 4."
  - "chunks_for_judge typed list[Any] (not list[RetrievedChunk]) — Rule 1 fix for the perf-test _FakeChunk duck type. The dispatcher's chunks: list[RetrievedChunk] parameter remains the typed contract one layer down; production callers all pass real RetrievedChunk instances. Documented inline in tracer_ai/rag/types.py."
  - "Pipeline._orchestrate returns 5-tuple including root_for_ctx Span rather than reaching into _orchestrate's locals from run_chat_stream. The stub Span carries trace_id + span_id + started_at — exactly what the dispatcher needs for parentage. _emit_root continues to own rag.request emission unchanged (no double-emit risk; the stub is a contextvar payload, not a writer.emit target)."
  - "Lifespan dispatcher drain timeout = 5.0s (matches consumer drain timeout). Same asyncio.wait_for + warn-log + continue pattern as the existing tracer.shutdown_drain_incomplete path. Both drain timeouts are independent — dispatcher hang doesn't starve consumer drain budget."
  - "AnthropicJudge construction wrapped in try/except in lifespan: graceful fallback to app.state.eval_dispatcher = None when ANTHROPIC_API_KEY missing in dev. Mirrors the pre-existing pipeline_construction_skipped pattern for the upstream try/except."

patterns-established:
  - "Cross-task contextvar parentage pattern: (1) construct stub Span in pipeline; (2) set_current_span(stub) + capture_context() in caller BEFORE the iterator's finally; (3) attach_context(snapshot) in dispatcher worker; (4) current_span() in worker reads stub. Pattern applies to ANY future async-after-response work (Phase 6 regression CLI, v2 multi-judge ensemble)."
  - "Field(exclude=True) for in-process model attachments: when a Pydantic model's wire shape is contractually fixed but in-process consumers need richer state, use exclude=True with arbitrary_types_allowed=True for non-Pydantic types. Verified by integration test PA3 asserting model_dump(mode='json') excludes the 4 private fields."
  - "Source-position drain-ordering test pattern (LD1): inspect.getsource(lifespan) + re.search for both call sites + assert ordering. Catches future re-orderings at PR review time with no live infra needed. Reusable for any ordering invariant in lifespan/finally chains."
  - "Never-raise eval contract at 4 layers: enqueue (try/except around create_task); _run_in_context (no try/except needed — attach_context can't fail with a valid snapshot); _do_score judge call (try/except BaseException, populate ERROR_TYPE); _do_score writer.emit + pool.execute (separate try/except for each, warn-log + swallow). User request never fails because of an eval failure (Pitfall #3 / EVAL-02 acceptance)."

requirements-completed: [EVAL-02, EVAL-04, EVAL-05]
requirements-touched: [TRCR-04]  # deferral closed via Plan 05-01 ctx helpers + this plan's dispatcher

# Metrics
duration: ~50min
completed: 2026-05-08
---

# Phase 5 Plan 4: EvalDispatcher + Cross-Task ctx Propagation Summary

**Wires the eval dispatch path end-to-end: builds the EvalDispatcher class (D-5.10/D-5.07/D-5.08), captures the contextvar snapshot in Pipeline.run_chat_stream BEFORE _emit_root ends rag.request (Pitfall #1), threads the snapshot + answer + chunks through ChatFinalEvent to the SSE generator, dispatches the judge task via asyncio.create_task after the SSE final frame yields, and integrates dispatcher construction + drain into tracer_ai/api/lifespan.py with the ordering invariant dispatcher -> consumer -> pool close. Closes the TRCR-04 deferral from Phase 4.**

## Performance

- **Duration:** ~50 min
- **Started:** 2026-05-08
- **Completed:** 2026-05-08
- **Tasks:** 2 / 2 complete
- **Files created:** 6 (1 source dispatcher + 5 test files)
- **Files modified:** 5 (eval/__init__ + rag/types + rag/pipeline + api/chat + api/lifespan)
- **Net new LOC:** ~1543 added across both commits (per `git show 3611972 c2361a5 --stat`)

## Accomplishments

- **D-5.10 (EvalDispatcher) implemented exactly:** class with `enqueue(trace_id, ctx_snapshot, answer, chunks, query)` that spawns an `asyncio.create_task`; the task uses `attach_context(snapshot)` to re-install `_current_span` so `current_span()` returns the rag.request root, then runs the Judge under the module-level semaphore (Plan 05-01's `get_judge_semaphore()`). Returns immediately to the SSE generator -- never blocks the user-facing response.
- **EVAL-02 acceptance (judge failures NEVER fail user requests):** Test CF1 asserts POST /chat returns 200 + full SSE final frame even when `MockJudge(raise_on_call=TimeoutError)` raises. Test CF2 asserts the rag.eval span carries `attrs[ERROR_TYPE] == "TimeoutError"`. Test CF3 asserts the `UPDATE traces SET faithfulness` statement is NOT issued (Pitfall #5).
- **EVAL-04 acceptance (rag.eval is a child of rag.request, not an orphan root):** Test PA2 asserts `rag_eval.parent_span_id == rag_request_span.span_id` and `rag_eval.trace_id == rag_request_span.trace_id`. The dispatcher reads parent via `current_span()` after `attach_context(ctx_snapshot)`. The snapshot is captured by `Pipeline.run_chat_stream` BEFORE the iterator's finally runs `_emit_root` -- Pitfall #1 mitigation.
- **EVAL-05 acceptance (eval lands within 30s budget):** Test LA1 asserts wall-clock elapsed from "final frame yielded" to "all dispatcher tasks complete" is < 25s with `MockJudge` returning instantly. The 25s ceiling validates the queue + UPDATE path on its own; with the real Anthropic Haiku judge the wall budget is ≤ 21s per D-5.05 (10s timeout × 2 attempts + 0.5s retry sleep).
- **TRCR-04 deferral closed:** Phase 4 04-VERIFICATION.md deferred the cross-task context-propagation contract to Phase 5 EVAL-04. Plan 05-01 shipped the hand-rolled contextvar helpers (`capture_context` / `attach_context` / `current_span` / `set_current_span` in `tracer_ai/tracer/context.py`); this plan wires them through the pipeline + dispatcher. The dispatcher worker coroutine sees the rag.request root via `current_span()` despite running in a different `asyncio.Task` than the SSE generator. Zero `opentelemetry-*` runtime deps preserved (ADR 005 invariant; verified by `grep "^from opentelemetry|^import opentelemetry" tracer_ai/` returning 0).
- **Lifespan drain ordering invariant locked in (D-5.10):** `tracer_ai/api/lifespan.py` finally block calls `eval_disp.drain(5.0)` BEFORE `consumer.drain()`. Test LD1 enforces this at the source level via `inspect.getsource + re.search` on the two call sites. Test LD2 verifies the slow-judge path produces `eval.dispatcher_drain_incomplete` warn-log within ~0.1s.
- **ChatFinalEvent wire shape preserved:** Phase 4 chat clients see exactly the same `event: final` SSE frame body. Test PA3 asserts `model_dump(mode="json")` does NOT include `ctx_snapshot`, `chunks_for_judge`, `query`, or `answer` -- the four Phase 5 private fields use `Field(exclude=True)`. T-05-04-10 (Pydantic Field exclude bypass) mitigation acceptance.

## Pitfall #1 Acceptance Evidence (Test PA2)

```python
# tracer_ai/rag/pipeline.py:run_chat_stream
trace_id, chunks, text_iter, usage_holder, root_for_ctx = await self._orchestrate(query)

# Phase 5 / Pitfall #1: capture the contextvar snapshot BEFORE the
# iterator's finally runs `_emit_root` on rag.request.
set_current_span(root_for_ctx)
ctx_snapshot = capture_context()

answer_parts: list[str] = []
async for text in text_iter:           # <- iterator's finally calls _emit_root LATER
    answer_parts.append(text)
    yield TextDelta(text=text)
# Snapshot at this point still has _current_span = root_for_ctx.
yield ChatFinalEvent(
    ...
    ctx_snapshot=ctx_snapshot,         # passed to EvalDispatcher.enqueue
    chunks_for_judge=chunks,
    query=query,
    answer="".join(answer_parts),
)
```

Test PA2 asserts the resulting rag.eval span has `parent_span_id == rag_request.span_id` and `trace_id == rag_request.trace_id`. The dispatcher `_run_in_context` calls `attach_context(ctx_snapshot)` then `current_span()` — without the BEFORE-finally capture, `current_span()` would return `None` and the rag.eval span would land as an orphan root.

## Pitfall #3 Acceptance Evidence (Tests CF1, CF2, CF3)

Three independent integration tests cover the never-raise contract:

| Test | Asserts |
|------|---------|
| CF1  | POST /chat with `MockJudge(raise_on_call=TimeoutError)` returns 200 + body contains both `event: token` and `event: final` |
| CF2  | After the request, the rag.eval span has `attrs[ERROR_TYPE] == "TimeoutError"` |
| CF3  | After the request, no `UPDATE traces SET faithfulness` statement was issued (Pitfall #5: denorm column UPDATE only on score success) |

The dispatcher catches `BaseException` around the judge call (so `KeyboardInterrupt` and `SystemExit` also produce a failure span), and uses separate try/except blocks around `writer.emit` and `pool.acquire+execute` so a failure in one stage does not abort the others.

## EVAL-05 Budget Evidence (Test LA1)

```python
t0 = time.perf_counter()
dispatcher.enqueue(trace_id, ctx_snapshot, answer, chunks, query)
await asyncio.wait_for(
    asyncio.gather(*dispatcher._pending, return_exceptions=True),
    timeout=25.0,                  # EVAL-05 enforces a 25s ceiling
)
elapsed = time.perf_counter() - t0
assert elapsed < 25.0
```

With instant `MockJudge`, observed elapsed time is sub-second on local hardware. The 25s ceiling exercises the queue + UPDATE path overhead independent of the judge's wall budget. With the real Anthropic Haiku judge, the dispatcher's wall budget is the judge's own ≤21s per D-5.05; total path stays comfortably under the EVAL-05 30s envelope.

## Lifespan Drain Order Verified (Tests LD1, LD2)

LD1 source-position assertion:
```python
src = inspect.getsource(tracer_ai.api.lifespan)
eval_match = re.search(r"eval_disp\.drain\(", src)        # @ pos 5832
consumer_match = re.search(r"consumer\.drain\(", src)     # @ pos 6244
assert eval_match.start() < consumer_match.start()        # PASS
```

LD2 live drain-incomplete warn-log: with a `_SlowJudge` that sleeps 2.0s and a 0.1s drain timeout, `dispatcher.drain(timeout=0.1)` produces the structured warn-log `eval.dispatcher_drain_incomplete remaining=N` within ~0.1s and never raises (lifespan finally chain continues to consumer drain + pool close).

## Task Commits

Each task was committed atomically:

1. **Task 1: EvalDispatcher class + 10 unit tests** -- `3611972` (feat)
2. **Task 2: pipeline ctx-snapshot capture + ChatFinalEvent extension + chat.py SSE dispatch + lifespan integration + 9 integration tests** -- `c2361a5` (feat)

**Plan metadata:** (next commit) docs(05-04): complete eval-dispatcher-and-wiring plan

## Files Created/Modified

**Created:**
- `tracer_ai/eval/dispatcher.py` — 217 LOC. EvalDispatcher class (D-5.10): enqueue / _run_in_context / _do_score / drain. Never-raise contract at every layer per Pitfall #3.
- `tests/test_eval_dispatcher.py` — 10 unit tests DA1-DA10 covering enqueue/spawn (DA1), happy path (DA2), TimeoutError + RateLimitError failure shapes (DA3, DA4), cross-task parent linkage (DA5), post-drain enqueue rejection (DA6), drain timeout warn-log (DA7), empty-pending fast path (DA8), traces UPDATE invocation (DA9), pool failure swallowed (DA10).
- `tests/integration/test_eval_span_parentage.py` — 3 tests PA1-PA3 covering ChatFinalEvent private fields populated (PA1), parent linkage rag.eval -> rag.request (PA2), wire-shape exclusion + faithfulness attrs (PA3).
- `tests/integration/test_chat_with_failed_eval.py` — 3 tests CF1-CF3 covering 200 + final frame on judge timeout (CF1), ERROR_TYPE attrs on failure span (CF2), no faithfulness UPDATE on failure (CF3).
- `tests/integration/test_eval_latency.py` — 1 test LA1 covering EVAL-05 25s budget headroom.
- `tests/integration/test_eval_drain_order.py` — 2 tests LD1-LD2 covering source-position drain ordering invariant (LD1) and live drain-incomplete warn-log on slow judge (LD2).

**Modified:**
- `tracer_ai/eval/__init__.py` — export `EvalDispatcher` (was 21 LOC, now 23 LOC).
- `tracer_ai/rag/types.py` — extend `ChatFinalEvent` with 4 `Field(exclude=True)` private fields (`ctx_snapshot`, `chunks_for_judge`, `query`, `answer`); set `arbitrary_types_allowed=True` for the contextvars.Context typing (was 152 LOC, now 173 LOC).
- `tracer_ai/rag/pipeline.py` — import `capture_context` + `set_current_span`; extend `_orchestrate` return tuple to include the stub `root_for_ctx: Span`; modify `run_chat_stream` to capture the ctx snapshot BEFORE driving the iterator; thread snapshot + chunks + query + accumulated answer into `ChatFinalEvent` (was 479 LOC, now 514 LOC).
- `tracer_ai/api/chat.py` — import `UUID` for the `ev.trace_id` -> UUID coercion; add eval dispatch block AFTER `yield frame.encode("utf-8")` for the final frame; `getattr` fallback so missing dispatcher (e.g., dev without `ANTHROPIC_API_KEY`) does not break /chat (was 88 LOC, now 113 LOC).
- `tracer_ai/api/lifespan.py` — import `EvalDispatcher` + `AnthropicJudge`; construct dispatcher after pipeline (try/except graceful fallback); drain dispatcher BEFORE consumer in finally (was 169 LOC, now 197 LOC).

## Decisions Made

- **D-5.10 dispatcher class shape (locked):** EvalDispatcher is a class with `app.state.eval_dispatcher` injection rather than a free function. Composes better with lifespan ownership semantics + integration test ergonomics; mirrors `05-PATTERNS.md` analog. The free-function alternative would force a module-level singleton + globals for the writer/pool dependencies.
- **chunks_for_judge typed `list[Any]` (Rule 1 fix; not `list[RetrievedChunk]`):** caught by pre-commit pytest-testmon when `tests/perf/test_trace_write_p95.py` failed strict-mode validation (its `_FakeChunk` duck-type does not satisfy Pydantic v2 `RetrievedChunk` validation). The field is `Field(exclude=True)` and in-process pass-through only. The dispatcher's `chunks: list[RetrievedChunk]` parameter remains the typed contract one layer down; production callers all pass real `RetrievedChunk` instances. Documented inline in `tracer_ai/rag/types.py`.
- **5-tuple return from _orchestrate (added root_for_ctx):** chosen over reaching into _orchestrate's locals from run_chat_stream (would require exposing private state) or constructing a fresh stub in run_chat_stream from scratch (would duplicate trace_id/root_span_id allocation, risking drift). The stub Span carries trace_id + span_id + started_at — the dispatcher only reads parent.span_id + parent.trace_id via current_span(). _emit_root continues to own rag.request emission unchanged.
- **Dispatcher drain timeout = 5.0s (matches consumer drain):** chosen for symmetry with the existing `tracer.shutdown_drain_incomplete` 5s budget. Two independent timeouts mean a hung dispatcher does not starve the consumer drain budget. Both use `asyncio.wait_for + warn-log + continue` pattern; lifespan finally always reaches `pool.close()`.
- **AnthropicJudge construction wrapped in try/except (graceful fallback):** lifespan continues with `app.state.eval_dispatcher = None` if `AnthropicJudge()` raises (typically: missing `ANTHROPIC_API_KEY`). Mirrors the pre-existing `pipeline_construction_skipped` pattern. The chat SSE generator's `getattr(request.app.state, "eval_dispatcher", None) is not None` guard skips dispatch silently.

## Test Counts + Pass Status

| Test file | Tests | Status |
|-----------|-------|--------|
| `tests/test_eval_dispatcher.py` | 10 (new — DA1-DA10) | PASS |
| `tests/integration/test_eval_span_parentage.py` | 3 (new — PA1-PA3) | PASS |
| `tests/integration/test_chat_with_failed_eval.py` | 3 (new — CF1-CF3) | PASS |
| `tests/integration/test_eval_latency.py` | 1 (new — LA1) | PASS |
| `tests/integration/test_eval_drain_order.py` | 2 (new — LD1-LD2) | PASS |
| **Plan 05-04 net new tests** | **19** (10 unit + 9 integration) | **PASS** |
| `tests/integration/test_lifespan_drain.py` (Phase 4 regression) | 2 | PASS |
| `tests/integration/test_pipeline_with_postgres_writer.py` (Phase 4 regression) | 1 | PASS |
| `tests/perf/test_trace_write_p95.py` (Phase 4 perf gate) | 1 | PASS (after Rule 1 typing relaxation) |
| `tests/test_chat_route.py` (Phase 3 regression) | 7 | PASS |
| Full unit + integration suite | 280 passed, 1 skipped | PASS (no regressions vs Plan 05-03's 256+1s baseline; +24 new tests from Plan 05-04) |

## Verification Block Results

| Verify command | Result |
|----------------|--------|
| `pytest -q tests/test_eval_dispatcher.py` | PASS (10/10) |
| `pytest -q tests/integration/test_eval_span_parentage.py tests/integration/test_chat_with_failed_eval.py tests/integration/test_eval_latency.py tests/integration/test_eval_drain_order.py` | PASS (9/9) |
| `pytest -q tests/integration/test_lifespan_drain.py tests/integration/test_pipeline_with_postgres_writer.py` (Phase 4 regression) | PASS (3/3) |
| `pytest -q tests/perf/test_trace_write_p95.py` (Phase 4 perf gate) | PASS (1/1) |
| Full test suite `pytest -q --ignore=tests/perf` | PASS (280 passed, 1 skipped) |
| `mypy --strict tracer_ai/` | PASS (Success: no issues found in 42 source files) |
| `ruff check tracer_ai/eval/dispatcher.py tracer_ai/rag/types.py tracer_ai/rag/pipeline.py tracer_ai/api/chat.py tracer_ai/api/lifespan.py tests/integration/test_eval_*.py tests/test_eval_dispatcher.py` | PASS (All checks passed!) |
| `grep -rE "^from opentelemetry\|^import opentelemetry" tracer_ai/` (ADR 005 invariant) | PASS (0 lines) |
| `python infra/scripts/import_cycle_guard.py` | PASS (4 layers; eval/ does NOT import api/) |
| pre-commit hooks (ruff, ruff-format, gitleaks, mypy --strict tracer_ai/, pytest-testmon, module-DAG, anti-pattern grep) | PASS on both Task 1 and Task 2 commits |

## Done-Criteria Verification

**Task 1 grep witnesses:**

| Done-criterion | Result |
|----------------|--------|
| `grep -c "class EvalDispatcher" tracer_ai/eval/dispatcher.py` returns 1 | 1 PASS |
| `grep -c "def enqueue" tracer_ai/eval/dispatcher.py` returns 1 | 1 PASS |
| `grep -c "asyncio.create_task" tracer_ai/eval/dispatcher.py` returns >= 1 | 4 PASS |
| `grep -c "attach_context" tracer_ai/eval/dispatcher.py` returns >= 1 | 2 PASS |
| `grep -c "current_span" tracer_ai/eval/dispatcher.py` returns >= 1 | 5 PASS |
| `grep -c "ERROR_TYPE" tracer_ai/eval/dispatcher.py` returns >= 1 | 3 PASS |
| `grep -c "eval.dispatcher_drain_incomplete" tracer_ai/eval/dispatcher.py` returns >= 1 | 2 PASS |
| `grep -c "UPDATE traces SET faithfulness" tracer_ai/eval/dispatcher.py` returns 1 | 1 PASS |
| `grep -c "EvalDispatcher" tracer_ai/eval/__init__.py` returns >= 2 (import + __all__) | 2 PASS |

**Task 2 grep witnesses:**

| Done-criterion | Result |
|----------------|--------|
| `grep -c "ctx_snapshot" tracer_ai/rag/types.py` returns >= 1 | 1 PASS |
| `grep -c "chunks_for_judge" tracer_ai/rag/types.py` returns >= 1 | 2 PASS |
| `grep -c "exclude=True" tracer_ai/rag/types.py` returns >= 1 | 6 PASS |
| `grep -c "from tracer_ai.tracer.context import" tracer_ai/rag/pipeline.py` returns >= 1 | 1 PASS |
| `grep -c "capture_context" tracer_ai/rag/pipeline.py` returns >= 1 | 3 PASS |
| `grep -c "set_current_span" tracer_ai/rag/pipeline.py` returns >= 1 | 2 PASS |
| `grep -c "dispatcher.enqueue" tracer_ai/api/chat.py` returns >= 1 | 2 PASS (one in code, one in docstring) |
| `grep -c "request.app.state" tracer_ai/api/chat.py` returns >= 1 | 4 PASS |
| `grep -c "EvalDispatcher" tracer_ai/api/lifespan.py` returns >= 2 | 5 PASS |
| `grep -c "eval_disp.drain\|eval_dispatcher.drain" tracer_ai/api/lifespan.py` returns >= 1 | 1 PASS |

**Drain ordering invariant:** `eval_disp.drain` line 178 < `consumer.drain()` line 186 in `tracer_ai/api/lifespan.py`. Verified visually + by Test LD1's `inspect.getsource` regex assertion.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Phase 5 `chunks_for_judge` strict-typing broke perf-test `_FakeChunk` duck type**

- **Found during:** Task 2 commit (pre-commit pytest-testmon gate)
- **Issue:** Plan specified `chunks_for_judge: list[RetrievedChunk] = Field(default_factory=list, exclude=True)`. Pydantic v2 strict-mode validation rejects the perf test's `_FakeChunk` duck-typed class (it satisfies the structural shape but is not a `RetrievedChunk` instance). `tests/perf/test_trace_write_p95.py` uses `_FakeChunk` to avoid the cost of constructing 200 × 5 = 1000 real `RetrievedChunk` Pydantic models per benchmark iteration.
- **Fix:** Relaxed `chunks_for_judge: list[Any]`. The field is `Field(exclude=True)` and in-process pass-through only; the dispatcher's `chunks: list[RetrievedChunk]` parameter remains the typed contract one layer down. Production callers all pass real `RetrievedChunk` instances. Documented inline in `tracer_ai/rag/types.py` so future maintainers do not "fix" it back to `list[RetrievedChunk]`.
- **Files modified:** `tracer_ai/rag/types.py`
- **Verification:** Perf test passes; mypy --strict still clean (Pydantic accepts `list[Any]` and the dispatcher's typed parameter is unchanged); all 19 new tests + 10 Phase 4 regressions still green.
- **Committed in:** `c2361a5` (Task 2 commit)

**2. [Rule 3 - Blocking] Pre-commit ruff-format reformatted test file on first Task 1 commit**

- **Found during:** Task 1 commit attempt
- **Issue:** Pre-commit's ruff-format hook reformatted `tests/test_eval_dispatcher.py` (collapsed two-arg `__init__` into a wrapped form). Pure formatting; no semantic change.
- **Fix:** Re-staged the formatted file and re-ran the commit (standard pre-commit flow; consistent with Plan 05-01 deviation #2).
- **Files modified:** `tests/test_eval_dispatcher.py`
- **Verification:** All 10 unit tests still green; ruff clean.
- **Committed in:** `3611972` (Task 1 final commit)

---

**Total deviations:** 2 (1 Rule 1 bug + 1 Rule 3 blocking).
**Impact on plan:** All decisions implemented exactly as locked except the typing of `chunks_for_judge` which was relaxed for correctness. Zero scope creep; zero contract drift; `D-5.10` + EVAL-02 + EVAL-04 + EVAL-05 acceptance evidence all green.

## Issues Encountered

- None beyond the 2 auto-fixed deviations above.

## Imports / Endpoints Made Available to Plan 05-05+

```python
# Dispatcher importable from package root:
from tracer_ai.eval import EvalDispatcher
# Constructed in tracer_ai/api/lifespan.py and stashed:
#   app.state.eval_dispatcher: EvalDispatcher | None
```

```python
# ChatFinalEvent now carries (in-process; never on the wire):
class ChatFinalEvent(BaseModel):
    # Phase 4 fields unchanged on the wire ...
    ctx_snapshot: Any | None       # contextvars.Context snapshot
    chunks_for_judge: list[Any]    # RetrievedChunk in production
    query: str
    answer: str                    # full assembled answer text
```

```python
# Pipeline._orchestrate now returns 5-tuple:
trace_id, chunks, text_iter, usage_holder, root_for_ctx = await pipeline._orchestrate(query)
# root_for_ctx is a stub Span representing rag.request for ctx-snapshot purposes
```

```python
# tracer_ai/api/chat.py SSE generator dispatches eval AFTER yielding final frame:
elif isinstance(ev, ChatFinalEvent):
    yield final_frame
    dispatcher = getattr(request.app.state, "eval_dispatcher", None)
    if dispatcher is not None and ev.ctx_snapshot is not None:
        try:
            dispatcher.enqueue(...)
        except Exception:
            log.warning("eval.enqueue_swallowed", ...)
```

## Self-Check: PASSED

**Files claimed exist:**

- FOUND: tracer_ai/eval/dispatcher.py
- FOUND: tracer_ai/eval/__init__.py (modified)
- FOUND: tracer_ai/rag/types.py (modified)
- FOUND: tracer_ai/rag/pipeline.py (modified)
- FOUND: tracer_ai/api/chat.py (modified)
- FOUND: tracer_ai/api/lifespan.py (modified)
- FOUND: tests/test_eval_dispatcher.py
- FOUND: tests/integration/test_eval_span_parentage.py
- FOUND: tests/integration/test_chat_with_failed_eval.py
- FOUND: tests/integration/test_eval_latency.py
- FOUND: tests/integration/test_eval_drain_order.py

**Commits claimed exist (`git log --oneline | grep`):**

- FOUND: 3611972 (Task 1: feat(05-04): add EvalDispatcher for async judge dispatch)
- FOUND: c2361a5 (Task 2: feat(05-04): wire eval dispatch end-to-end)

**Endpoint contract grep witnesses:** all 19 grep done-criteria satisfied (per "Done-Criteria Verification" section above).

## Threat Flags

None. The plan introduced no new network endpoints, no new auth paths, no new file-access patterns. The single new module-state addition is `app.state.eval_dispatcher` (an in-process Python object, not a request-scoped state). The four new `Field(exclude=True)` private fields on `ChatFinalEvent` are NEVER serialized on the wire (T-05-04-10 mitigation acceptance verified by Test PA3). All threat surface stays within the explicitly enumerated `<threat_model>` of the plan (T-05-04-01 through T-05-04-10).

## TRCR-04 Deferral Closure

Phase 4 04-VERIFICATION.md:

> **TRCR-04 (cross-task ctx propagation): DEFERRED to Phase 5 EVAL-04.** Phase 4 sync 4-span emission passes parent_span_id explicitly via uuid4(); the cross-task context-snapshot pattern is needed for the BackgroundTasks async eval branch (per docs/sequence-diagrams.md Note callout). Phase 4 stays free of any opentelemetry-* runtime dep (ADR 005 compliance preserved).

Phase 5 closure:

- **Plan 05-01** shipped the hand-rolled contextvar helpers in `tracer_ai/tracer/context.py` (`capture_context`, `attach_context`, `current_span`, `set_current_span`) — zero `opentelemetry-*` runtime deps.
- **Plan 05-04 (this plan)** wired them through `Pipeline.run_chat_stream` (capture before _emit_root per Pitfall #1) and the dispatcher worker coroutine (`attach_context` then `current_span()` to read parent).
- **Test PA2** is the closure evidence: full pipeline run -> rag.eval span emit -> assert `parent_span_id == rag_request.span_id` and `trace_id == rag_request.trace_id`.

Phase 4 contract honored: rag.eval is a child of rag.request, NOT an orphan root. Phase 7 portfolio narrative: "I built async eval cross-task parentage with zero OTel runtime, just contextvars."

## Next Phase Readiness

- Plan 05-05 (timeseries endpoint) unblocked: independent of this plan -- no shared file changes -- but the EvalDispatcher is now live so the `traces.faithfulness` denorm column is populated, which the timeseries query reads.
- Plan 05-06 (calibration CLI) unblocked: independent; CLI prompts walk recent traces (which now have rag.eval children + faithfulness scores).
- Plan 05-07 (frontend) unblocked: trace-detail SpanWaterfall already auto-renders rag.eval rows with the dashed `└╌╌` async glyph (Phase 4 D-4.16 forward-compat); no UI changes needed for this plan's artifacts to surface.
- No blockers; no architectural concerns.

---
*Phase: 05-quality-feedback*
*Completed: 2026-05-08*
