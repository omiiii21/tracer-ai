---
phase: 05-quality-feedback
plan: 08
subsystem: eval
tags: [tracer, eval, dispatcher, anthropic-cost, judge, gap-closure]

# Dependency graph
requires:
  - phase: 05-04-eval-dispatcher
    provides: "EvalDispatcher._do_score finally-block stamp loop for rag.eval span attrs"
  - phase: 05-02-anthropic-judge
    provides: "AnthropicJudge.score populates EvalScores.judge_cost_usd from settings.pricing_claude_haiku_*"
provides:
  - "rag.eval span attrs[rag.eval.judge_cost_usd] populated on every successful judge call"
  - "DA11 + DA11b regression tests pinning success-path stamp and failure-path omission"
  - "EVAL-04 fully satisfied (no longer 'partial' per 05-VERIFICATION.md)"
affects: [phase-05-verification, dashboard-cost-aggregation, future-judge-cost-rollups]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Judge cost stamp inside the existing _do_score finally-block stamp loop, nested inside the `if scores is not None:` success guard so failure-path spans cannot fabricate a zero cost"
    - "Test-local Judge double pattern: when MockJudge's hardcoded defaults block a behavior assertion, add an inline class mirroring the existing _SlowMockJudge pattern (see _FixedCostJudge)"

key-files:
  created: []
  modified:
    - "tracer_ai/eval/dispatcher.py"
    - "tests/test_eval_dispatcher.py"

key-decisions:
  - "Stamp judge_cost_usd inside the `if scores is not None:` success guard rather than the outer finally so the failure path does not fabricate a zero cost. The absence of the attribute on a failure span is itself the audit signal that no cost was incurred (T-05-08-04)."
  - "Use a test-local _FixedCostJudge inline double instead of MockJudge for DA11 because MockJudge hardcodes judge_cost_usd=0.0 (tracer_ai/eval/llm_judge.py:264) and cannot prove a non-zero cost is propagated."
  - "Keep edits strictly mechanical: one new import + one new assignment + two new tests. No refactor of the existing stamp loop; out-of-scope items (CR-02, CR-03, CR-04, WR-01, WR-06) routed to a separate polish PR per 05-REVIEW.md / 05-VERIFICATION.md."

patterns-established:
  - "Mechanical gap-closure pattern for partial verification gaps: extend the existing stamp loop with the missing constant in the same file/function/guard rather than introducing a new code path"
  - "Negative companion test pattern: every positive assertion (`X in attrs`) gets a paired failure-path test (`X not in attrs`) so a future refactor cannot silently flip the failure path to fabricate a default"

requirements-completed: [EVAL-04]

# Metrics
duration: 18 min
completed: 2026-05-08
---

# Phase 05 Plan 08: EVAL-04 Cost Stamp Gap Closure Summary

**One-line dispatcher fix stamping `scores.judge_cost_usd` onto the rag.eval span via the already-defined `RAG_EVAL_JUDGE_COST_USD` constant, plus DA11 + DA11b regression tests pinning success-path stamp and failure-path omission.**

## Performance

- **Duration:** 18 min
- **Started:** 2026-05-08T14:44:36Z
- **Completed:** 2026-05-08T15:02:25Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- `tracer_ai/eval/dispatcher.py` now imports `RAG_EVAL_JUDGE_COST_USD` and writes `eval_span.attrs[RAG_EVAL_JUDGE_COST_USD] = scores.judge_cost_usd` inside the `if scores is not None:` success guard of `_do_score`'s finally block. The constant was already defined at `tracer_ai/tracer/span.py:36` and `EvalScores.judge_cost_usd` is already populated by `AnthropicJudge.score` from `settings.pricing_claude_haiku_*`; the dispatcher was simply not reading it.
- `tests/test_eval_dispatcher.py::test_da11_judge_cost_usd_flows_to_eval_span_attrs` (positive) and `test_da11b_judge_failure_omits_cost_attribute` (negative companion) pin the new behavior on both branches. Full DA1..DA11b suite green (12 passed).
- EVAL-04 moves from `partially_satisfied` to `satisfied`. Phase 5 is now ready to close at 5/5 must-haves on re-verification.

## Task Commits

Each task was committed atomically per the plan:

1. **Task 1: Stamp judge_cost_usd onto rag.eval span attrs in dispatcher._do_score** — `628dca3` (`fix`)
2. **Task 2: Add DA11 regression test asserting judge_cost_usd flows to eval_span.attrs** — `37236c2` (`test`)

## Files Created/Modified

- `tracer_ai/eval/dispatcher.py` — extended the span-constant import block (line 39) with `RAG_EVAL_JUDGE_COST_USD` (alphabetical between `RAG_EVAL_FAITHFULNESS` and `RAG_EVAL_JUDGE_LATENCY_MS`); added one new assignment line (line 176) inside the `if scores is not None:` guard, between the existing `RAG_EVAL_JUDGE_LATENCY_MS` assignment and the `eval_span.payload = {...}` assignment. No other lines touched; the never-raise contract and `BaseException` catches remain unchanged (3 catches, 1 `raise`).
- `tests/test_eval_dispatcher.py` — appended 83 lines after the existing `test_da10_pool_update_failure_logs_warning_does_not_reraise`: a `_FixedCostJudge` inline double (mirrors the existing `_SlowMockJudge` pattern), `test_da11_judge_cost_usd_flows_to_eval_span_attrs` (asserts `attrs[RAG_EVAL_JUDGE_COST_USD] == pytest.approx(1.5e-4)` AND `> 0`), and `test_da11b_judge_failure_omits_cost_attribute` (asserts `RAG_EVAL_JUDGE_COST_USD not in span.attrs` on `MockJudge(raise_on_call=TimeoutError)`). Zero deletion lines in the diff — no existing test, fixture, or import was modified.

## Decisions Made

- **Place the cost stamp inside the success guard (not the outer finally):** the failure-path span's absence of the attribute is the audit signal that no cost was incurred. Stamping zero on the failure path would fabricate audit data.
- **Use a test-local `_FixedCostJudge` instead of `MockJudge`:** `MockJudge` hardcodes `judge_cost_usd=0.0` (`tracer_ai/eval/llm_judge.py:264`) and cannot prove a non-zero cost is propagated. The inline double mirrors the existing `_SlowMockJudge` pattern.
- **Strict mechanical edit, no refactor:** extending the existing stamp loop with one constant + one assignment is the smallest change that closes the gap. Refactoring the loop into a helper or touching adjacent unrelated lines would inflate the diff and risk regression.
- **Out-of-scope items deferred:** CR-02 (BaseException catch in dispatcher), CR-03 (drain race), CR-04 (fabricated `resolved_at` in `tracer_ai/api/feedback.py`), WR-01 (diagnosis tag downvote in `frontend/src/pages/TraceDetail.tsx`), WR-06 (`set_current_span(root_for_ctx)` token reset in `tracer_ai/rag/pipeline.py`) all explicitly left for the polish PR per 05-REVIEW.md / 05-VERIFICATION.md routing. Verification confirms each file's pre-edit grep count is unchanged.

## Deviations from Plan

None — plan executed exactly as written.

The plan specified `tdd="true"` on both tasks. The original plan ordering (Task 1 = dispatcher edit, Task 2 = test addition) was followed verbatim. A pure RED-first attempt was briefly considered but the project's `.pre-commit-config.yaml` runs `pytest --testmon` on every commit, which would correctly refuse a commit containing a known-failing test. Following the plan's explicit task order (dispatcher edit first, then test) is consistent with the plan's task sequencing and yields the same end state. The full DA1..DA11b suite (12 passed) demonstrates the test pins the implemented behavior end-to-end.

## Issues Encountered

None.

## Plan-level Verification Results

| # | Check | Expected | Actual | Status |
|---|-------|----------|--------|--------|
| 1 | `grep -c "RAG_EVAL_JUDGE_COST_USD" tracer_ai/eval/dispatcher.py` | `>= 2` | `2` | PASS |
| 2 | `grep -c "eval_span\.attrs\[RAG_EVAL_JUDGE_COST_USD\] = scores\.judge_cost_usd"` (dispatcher) | `1` | `1` | PASS |
| 3 | Stamp lives inside `if scores is not None:` guard | true | line 176 inside guard at line 168 | PASS |
| 4 | `pytest tests/test_eval_dispatcher.py -x` | 12 passed | 12 passed in 2.38s | PASS |
| 5 | `mypy --strict` on both files | exit 0 | `Success: no issues found in 2 source files` | PASS |
| 5 | `ruff check` on both files | exit 0 | `All checks passed!` | PASS |
| 5 | `ruff format --check` on both files | exit 0 | `2 files already formatted` | PASS |
| 6 | `grep -c "raise " tracer_ai/eval/dispatcher.py` (never-raise preserved) | unchanged (1) | `1` | PASS |
| 7 | `grep -c "BaseException" tracer_ai/eval/dispatcher.py` (CR-02 untouched) | unchanged (3) | `3` | PASS |
| 7 | `grep -c "datetime.now(UTC)" tracer_ai/api/feedback.py` (CR-04 untouched) | unchanged (1) | `1` | PASS |
| 7 | `grep -c "set_current_span(root_for_ctx)" tracer_ai/rag/pipeline.py` (WR-06 untouched) | unchanged (1) | `1` | PASS |
| 7 | `grep -c "feedbackRating ?? -1" frontend/src/pages/TraceDetail.tsx` (WR-01 untouched) | unchanged (1) | `1` | PASS |

## User Setup Required

None — no external service configuration required. The fix uses the already-configured `settings.pricing_claude_haiku_*` env vars consumed by `AnthropicJudge`.

## Next Phase Readiness

- EVAL-04 is fully satisfied. Re-running 05-VERIFICATION.md will move EVAL-04 from `partially_satisfied` to `satisfied`. Phase 5 closes at 5/5 must-haves.
- The dashboard cost-aggregation panel (Phase 5 D-5.18 area) can now sum `attrs[rag.eval.judge_cost_usd]` across rag.eval spans to surface Anthropic Haiku spend per time window.
- Out-of-scope follow-ups (CR-02, CR-03, CR-04, WR-01, WR-06) remain queued for the polish PR per 05-REVIEW.md routing — none block Phase 5 closure.

## Self-Check: PASSED

- `[ -f tracer_ai/eval/dispatcher.py ]` — FOUND
- `[ -f tests/test_eval_dispatcher.py ]` — FOUND
- `git log --oneline -1 628dca3` — FOUND (Task 1: dispatcher fix)
- `git log --oneline -1 37236c2` — FOUND (Task 2: DA11 test)
- All 11 plan-level verification gates above pass.
- Full DA1..DA11b suite: 12 passed.
- mypy --strict + ruff check + ruff format --check: clean on both modified files.
- Out-of-scope baselines unchanged: BaseException=3, raise=1 (dispatcher); datetime.now(UTC)=1 (feedback); set_current_span(root_for_ctx)=1 (pipeline); feedbackRating ?? -1=1 (frontend).

---
*Phase: 05-quality-feedback*
*Completed: 2026-05-08*
