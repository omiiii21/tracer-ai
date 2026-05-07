---
phase: 05-quality-feedback
plan: 01
subsystem: eval
tags: [anthropic, haiku, judge, tool_use, contextvars, pydantic-v2, settings, otel]

# Dependency graph
requires:
  - phase: 04-tracer-trace-explorer
    provides: "Span Pydantic model + TraceWriter Protocol + trace constants block"
  - phase: 03-rag-pipeline
    provides: "AnthropicLLM SDK-isolation pattern + RetrievedChunk + LLM/Embedder Protocols"
  - phase: 02-skeleton-infrastructure
    provides: "Settings (extra='forbid') + anti-pattern allowlist for tracer_ai/eval/llm_judge.py"
  - phase: 01-research-design-artifacts
    provides: "ADR 005 zero-otel-runtime thesis; ADR 008 RAGAS-style + XML-delimiter prompt mandate; rag.eval span schema"
provides:
  - "Judge Protocol (runtime_checkable) + EvalScores Pydantic model with judge_cost_usd field (EVAL-04 fix)"
  - "AnthropicJudge adapter forcing tool_use; computes judge_cost_usd from settings.pricing_claude_haiku_*"
  - "MockJudge test double behind same Protocol"
  - "build_judge_prompt + JUDGE_SYSTEM_PROMPT + _escape_brackets injection mitigation"
  - "PROMPT_VERSION = 'v1.ragas-faithfulness-relevance' module constant (D-5.04)"
  - "SUBMIT_EVAL_TOOL ToolParam schema (D-5.02)"
  - "Module-level _judge_semaphore + get_judge_semaphore() singleton (D-5.09)"
  - "Hand-rolled contextvar helpers (capture_context / attach_context / current_span / set_current_span); zero opentelemetry-* runtime deps"
  - "ToolUseParseError (no-retry sentinel for D-5.05)"
  - "ERROR_TYPE + RAG_EVAL_JUDGE_LATENCY_MS span constants"
  - "4 new Settings fields: BAD_ANSWER_FAITHFULNESS_THRESHOLD, JUDGE_CONCURRENCY, JUDGE_TIMEOUT_SECONDS, CALIBRATION_DATE"
affects: [05-03 admin endpoint, 05-04 dispatcher + chat wiring, 05-06 calibration CLI, 06 regression CLI]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Two-attempt retry loop with type-discriminated catch (RateLimit/APIConnection/APITimeout retry once, ToolUseParseError no retry)"
    - "Pydantic re-validation of tool_use.input as defense-in-depth against malformed model output"
    - "Hand-rolled contextvar snapshot pattern (D-5.06) to close TRCR-04 with zero OTel runtime deps"
    - "Settings field bounds via Pydantic Field(ge=, le=, gt=) for fail-fast env-var validation"
    - "_escape_brackets HTML-entity-encoding pass to defeat closing-tag injection from untrusted retrieved chunks"

key-files:
  created:
    - "tracer_ai/eval/protocols.py - Judge Protocol + EvalScores + ToolUseParseError"
    - "tracer_ai/eval/prompts.py - JUDGE_SYSTEM_PROMPT + build_judge_prompt + _escape_brackets"
    - "tracer_ai/eval/llm_judge.py - AnthropicJudge + MockJudge + PROMPT_VERSION + SUBMIT_EVAL_TOOL + get_judge_semaphore"
    - "tests/test_context.py - 6 tests for contextvar helpers"
    - "tests/test_judge_prompts.py - 4 tests for prompt builder + injection mitigation"
    - "tests/test_llm_judge.py - 9 tests for judge adapter (Protocol, cost, retry, parse error)"
  modified:
    - "tracer_ai/config.py - 4 new Pydantic fields with bounded validators"
    - "tracer_ai/tracer/context.py - hand-rolled contextvar helpers (~70 LOC, was 7-line stub)"
    - "tracer_ai/tracer/span.py - ERROR_TYPE + RAG_EVAL_JUDGE_LATENCY_MS constants appended"
    - "tracer_ai/eval/__init__.py - re-export 8 public names"
    - ".env.example - Phase 5 quality-layer section with 4 new env vars"
    - "tests/conftest.py - clean_env evicts the 4 new env-var keys"
    - "tests/test_config_failfast.py - 7 new tests for Phase 5 Settings fields"

key-decisions:
  - "calibration_date accepts BOTH tz-aware AND naive datetimes (Open Question 5 RESOLVED -- no enforcement in v1)"
  - "judge_concurrency upper bound = 32 (not 64); single-user local will never need higher"
  - "Eager init of _judge_semaphore at module top (no circular-import risk from llm_judge -> config); avoids the lazy-init mypy --strict friction"
  - "_escape_brackets order is &-then-<>-> to avoid double-escaping literal & characters"
  - "ToolUseParseError raises immediately with no retry (D-5.05): retrying same prompt won't change a model that refused tool_use"

patterns-established:
  - "SDK exception construction in tests: build a real httpx.Request + httpx.Response so anthropic.RateLimitError(message=..., response=..., body=...) can call super().__init__(..., response.request, body=...) without AttributeError. APITimeoutError accepts a SimpleNamespace(url='x') request because its __init__ never accesses .request attributes."
  - "Test files importing tracer_ai.eval at module-top must os.environ.setdefault the 3 required vars (DATABASE_URL/ANTHROPIC_API_KEY/VOYAGE_API_KEY) BEFORE the import line, because pytest autouse fixtures only run after collection-time imports. The deferred-import-inside-test pattern (used by test_llm_adapter.py) is the alternative when env vars are short-lived."
  - "Module-level Anthropic exception imports + eager-init of asyncio.Semaphore at import time (vs. lazy lru_cache singleton): only viable when the module's settings import isn't itself part of a cycle. tracer_ai.config has no upstream imports inside tracer_ai/, so eager init is safe and gives mypy --strict-clean typing without functools.lru_cache decorator clutter."

requirements-completed: [EVAL-01, EVAL-03]

# Metrics
duration: ~30min
completed: 2026-05-07
---

# Phase 5 Plan 1: Eval Foundation Summary

**Anthropic Haiku judge adapter with tool_use forced output, XML-delimited prompts with closing-tag-injection escape, hand-rolled contextvar helpers (zero OTel runtime), and 4 new bounded Settings fields -- the foundation Wave 2 plans (dispatcher, admin endpoint, calibration CLI) consume**

## Performance

- **Duration:** ~30 min
- **Started:** 2026-05-07 (Plan 05-01 execution start)
- **Completed:** 2026-05-07
- **Tasks:** 3 / 3 complete
- **Files modified:** 7 modified + 6 created (3 source + 3 test)

## Accomplishments

- **EVAL-01 (Anthropic Haiku judge):** AnthropicJudge.score() returns EvalScores via forced tool_use; computes judge_cost_usd from settings.pricing_claude_haiku_*_per_mtok per call (EVAL-04 cost fix); 1-retry policy on transient SDK errors; ToolUseParseError raised immediately on parse-shape failures (no retry per D-5.05).
- **EVAL-03 (XML-delimited prompts):** JUDGE_SYSTEM_PROMPT declares <retrieved_chunk> + <assistant_answer> tags as inert DATA; build_judge_prompt wraps untrusted query/answer/chunks; _escape_brackets HTML-entity-encodes literal angle brackets so closing-tag injection (Pitfall #3) cannot break out of the envelope.
- **TRCR-04 closure (D-5.06):** Hand-rolled contextvar helpers in tracer_ai/tracer/context.py replaced the 7-line Phase 2 stub. capture_context() snapshots BEFORE root.end() per Pitfall #1; attach_context() installs the snapshot's _current_span in a worker coroutine. Zero opentelemetry-* runtime deps.
- **D-5.13/D-5.09/D-5.05/D-5.14 Settings extension:** 4 new Pydantic fields with bounded validators (ge/le/gt) -- BAD_ANSWER_FAITHFULNESS_THRESHOLD (default 0.6), JUDGE_CONCURRENCY (default 4, ≤32), JUDGE_TIMEOUT_SECONDS (default 10.0, ≤60), CALIBRATION_DATE (optional, accepts naive AND tz-aware per Open Question 5 RESOLVED).
- **Wave 2 contracts ready for import:** Plan 05-04 (dispatcher) can import Judge, EvalScores, AnthropicJudge, MockJudge, capture_context, attach_context, current_span, set_current_span, ERROR_TYPE, RAG_EVAL_JUDGE_LATENCY_MS, get_judge_semaphore. Plan 05-03 (admin endpoint) can import PROMPT_VERSION + settings.bad_answer_faithfulness_threshold. Plan 05-06 (calibration CLI) can import EvalScores + PROMPT_VERSION.

## Task Commits

Each task was committed atomically:

1. **Task 1: Settings extension + ERROR_TYPE / RAG_EVAL_JUDGE_LATENCY_MS span constants** -- `a243fba` (feat)
2. **Task 2: Hand-rolled contextvar helpers (D-5.06; closes TRCR-04)** -- `7c77224` (feat)
3. **Task 3: Judge Protocol + AnthropicJudge + XML-delimited prompts (EVAL-01 / EVAL-03 / EVAL-04 cost fix)** -- `26f5ca1` (feat)

**Plan metadata:** (this commit) docs(05-01): complete eval-foundation plan

_Per-task TDD discipline: each task wrote failing tests first (RED), then minimal implementation (GREEN). No REFACTOR-only commits were necessary -- the implementations passed mypy --strict + ruff on first GREEN._

## Files Created/Modified

**Created:**
- `tracer_ai/eval/protocols.py` -- Judge Protocol (runtime_checkable) + EvalScores Pydantic model with judge_cost_usd field (EVAL-04 fix) + ToolUseParseError exception
- `tracer_ai/eval/prompts.py` -- JUDGE_SYSTEM_PROMPT + build_judge_prompt + _escape_brackets injection-mitigation pass
- `tracer_ai/eval/llm_judge.py` -- AnthropicJudge (forced tool_use, retry policy, EVAL-04 cost computation) + MockJudge test double + PROMPT_VERSION + SUBMIT_EVAL_TOOL + module-level _judge_semaphore + get_judge_semaphore()
- `tests/test_context.py` -- 6 tests for contextvar helpers (None default, set/reset, capture+attach in different task, asyncio.create_task auto-inheritance, child mutation isolation, attach idempotency)
- `tests/test_judge_prompts.py` -- 4 tests for prompt builder (system prompt declares inert envelope, query+answer wrapping, per-chunk index tags, injection-escape acceptance)
- `tests/test_llm_judge.py` -- 9 tests for judge (AnthropicJudge isinstance Judge, MockJudge isinstance Judge, tool_use happy path, EVAL-04 cost formula match, retry-once-on-rate-limit, no-third-attempt-on-timeout, no-retry-on-parse-error, PROMPT_VERSION constant, semaphore singleton)

**Modified:**
- `tracer_ai/config.py` -- 4 new Pydantic fields per D-5.13/D-5.09/D-5.05/D-5.14 with bounded validators
- `tracer_ai/tracer/context.py` -- replaced 7-line stub with ~70-LOC hand-rolled contextvar implementation
- `tracer_ai/tracer/span.py` -- ERROR_TYPE + RAG_EVAL_JUDGE_LATENCY_MS appended to constants block
- `tracer_ai/eval/__init__.py` -- re-exports 8 public names
- `.env.example` -- new Phase 5 quality-layer section
- `tests/conftest.py` -- clean_env fixture evicts the 4 new env-var keys
- `tests/test_config_failfast.py` -- 7 new tests for Phase 5 Settings fields (Test 1-7 per plan behaviors)

## Decisions Made

- **Open Question 5 RESOLVED:** calibration_date accepts BOTH tz-aware AND naive datetimes -- Pydantic v2 datetime accepts naive without raising; documented in field description. Tz-aware is recommended via the .env.example comment but not enforced.
- **judge_concurrency upper bound = 32 (not 64):** single-user local will never need higher; keeps the bound concrete and testable. Field validator: `Field(default=4, ge=1, le=32)`.
- **Eager `_judge_semaphore` init at module top:** chose this over the lazy `functools.lru_cache(None)` fallback since `tracer_ai.config` has no upstream imports inside `tracer_ai/`, so no circular-import risk. Cleaner mypy --strict typing; no decorator overhead.
- **`_escape_brackets` replacement order is `&` first, then `<` and `>`:** prevents double-escape of any literal `&` already in untrusted input. Verified by Test PromptD which counts closing tags exactly == N chunks (the injected ones are entity-encoded).
- **Test SDK exception construction:** `RateLimitError(message=..., response=httpx.Response(429, request=httpx.Request("POST", url)), body=None)` because the SDK's `super().__init__` accesses `response.request`. `APITimeoutError(request=SimpleNamespace(url="x"))` works because its `__init__` does not access `.request` attributes.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] gitleaks pre-commit hook flagged the test API-key constant**

- **Found during:** Task 1 commit attempt
- **Issue:** Existing `_set_required_env` test helper used `"sk-ant-test-12345678901234567890"` (matches the gitleaks `sk-ant-[a-zA-Z0-9_-]{20,}` regex). The pre-existing test functions in `test_config_failfast.py` already use this string and were committed before the gitleaks rule was added; the rule scans only the staged diff, so adding a NEW reference (line 111) flagged the file.
- **Fix:** Shortened the helper's value to `"sk-ant-x"` (<20 chars after the prefix, below the regex threshold). Documented the rationale in a docstring so future readers do not re-introduce a long fake key. The existing 5 occurrences (lines 23, 49, 61, 68, 88) are unchanged because they are not on the new commit's diff.
- **Files modified:** tests/test_config_failfast.py
- **Verification:** `gitleaks` hook passed on retry; 12/12 tests still green
- **Committed in:** a243fba (Task 1 commit)

**2. [Rule 3 - Blocking] Pre-commit ruff-format ran twice (Tasks 2 + 3)**

- **Found during:** Task 2 + Task 3 commit attempts
- **Issue:** Pre-commit's ruff-format hook reformatted whitespace in 5 files (Task 2: 2 files; Task 3: 5 files). The format changes were cosmetic only (single-line `replace` chains, no semantic change).
- **Fix:** Re-staged the formatted files and re-ran the commit (standard pre-commit flow).
- **Files modified:** tracer_ai/tracer/context.py, tests/test_context.py (Task 2); tracer_ai/eval/protocols.py, tracer_ai/eval/prompts.py, tracer_ai/eval/llm_judge.py, tests/test_judge_prompts.py, tests/test_llm_judge.py (Task 3)
- **Verification:** Tests still green after format; ruff clean; mypy --strict clean
- **Committed in:** 7c77224 (Task 2), 26f5ca1 (Task 3)

**3. [Rule 1 - Bug] RateLimitError construction fails with SimpleNamespace response**

- **Found during:** Task 3 GREEN run (test JudgeD)
- **Issue:** Anthropic SDK 0.49+ `RateLimitError.__init__` calls `super().__init__(message, response.request, body=body)` -- so the `response` kwarg must be a real `httpx.Response` object with an attached `.request` attribute. The plan's example used `SimpleNamespace(status_code=429)` which fails with AttributeError.
- **Fix:** Construct a real `httpx.Request("POST", "https://api.anthropic.com/v1/messages")` and pass it to `httpx.Response(429, request=fake_request)`. APITimeoutError can still take SimpleNamespace because its __init__ never reads .request attributes.
- **Files modified:** tests/test_llm_judge.py
- **Verification:** Test JudgeD passes; httpx is already a transitive dep via anthropic SDK so no new requirement.
- **Committed in:** 26f5ca1 (Task 3 commit)

**4. [Rule 3 - Blocking] tracer_ai.eval/__init__.py eager imports break test_judge_prompts collection**

- **Found during:** Task 3 GREEN run (initial collection)
- **Issue:** test_judge_prompts.py uses module-top `from tracer_ai.eval.prompts import ...`. Because `tracer_ai.eval/__init__.py` re-exports from llm_judge.py (per plan spec), importing prompts triggers the chain prompts -> tracer_ai.eval -> llm_judge -> tracer_ai.config -> Settings(). Settings raises ValidationError because pytest fixtures (autouse) run AFTER collection.
- **Fix:** Add `os.environ.setdefault(...)` for the 3 required vars at the top of test_judge_prompts.py BEFORE the import line. test_llm_judge.py uses the deferred-import-inside-test pattern (mirrors test_llm_adapter.py) so it doesn't need this; test_judge_prompts.py does because its imports are all at module-top.
- **Files modified:** tests/test_judge_prompts.py
- **Verification:** `pytest -q tests/test_judge_prompts.py tests/test_llm_judge.py` collects + passes 13 tests.
- **Committed in:** 26f5ca1 (Task 3 commit)

---

**Total deviations:** 4 auto-fixed (1 Rule 1 bug, 3 Rule 3 blocking)
**Impact on plan:** All four fixes were environmental (gitleaks rule, ruff-format hook, SDK API contract, fixture timing). No scope creep; no contract drift; all locked decisions implemented exactly. The plan's `<verify>` blocks all pass, and the verification block (mypy --strict on 7 files; ruff on 4; zero opentelemetry imports; allowlist invariant) is green.

## Issues Encountered

- None beyond the 4 auto-fixed deviations above.

## EVAL-04 Cost-Fix Evidence

- `EvalScores.judge_cost_usd: float = Field(default=0.0, ge=0.0)` field added (tracer_ai/eval/protocols.py:46).
- AnthropicJudge.score() computes `cost_usd = (settings.pricing_claude_haiku_input_per_mtok * input_tokens + settings.pricing_claude_haiku_output_per_mtok * output_tokens) / 1_000_000.0` immediately before constructing the returned EvalScores (tracer_ai/eval/llm_judge.py).
- Test `test_judge_cost_usd_matches_pricing_formula` (JudgeC2) asserts `pytest.approx(0.00168, rel=1e-6)` for the canonical (1500 input + 120 output) case at default rates -- closing the EVAL-04 cost-fix gap.

## Open Question 5 Resolution

CALIBRATION_DATE accepts both tz-aware (`2026-05-15T12:00:00Z`) and naive (`2026-05-15T12:00:00`) ISO 8601 strings. The `.env.example` comment recommends a tz suffix but does not enforce. Pydantic v2 `datetime | None` type hint accepts naive without raising. Test `test_calibration_date_accepts_tz_aware_and_naive` covers all three subcases (aware, naive, unset->None).

## Imports Made Available to Wave 2

Plan 05-04 (dispatcher + chat wiring), 05-03 (admin endpoint), 05-06 (calibration CLI) can import the following without modifying this plan's outputs:

```python
from tracer_ai.eval import (
    AnthropicJudge,
    EvalScores,
    Judge,
    MockJudge,
    PROMPT_VERSION,
    SUBMIT_EVAL_TOOL,
    ToolUseParseError,
    get_judge_semaphore,
)
from tracer_ai.tracer.context import (
    attach_context,
    capture_context,
    current_span,
    set_current_span,
)
from tracer_ai.tracer.span import (
    ERROR_TYPE,
    RAG_EVAL_JUDGE_LATENCY_MS,
)
from tracer_ai.config import settings
# Available: settings.bad_answer_faithfulness_threshold (D-5.13)
#            settings.judge_concurrency (D-5.09)
#            settings.judge_timeout_seconds (D-5.05)
#            settings.calibration_date (D-5.14)
```

## Test Counts per File + Pass Status

| Test file | Tests | Status |
|-----------|-------|--------|
| tests/test_config_failfast.py | 12 (5 existing + 7 new) | PASS |
| tests/test_context.py | 6 (new) | PASS |
| tests/test_judge_prompts.py | 4 (new) | PASS |
| tests/test_llm_judge.py | 9 (new) | PASS |
| tests/test_anti_patterns.py | 7 (existing; allowlist regression check) | PASS |
| **Phase 5 Plan 01 net new tests** | **26** | **PASS** |
| Full unit suite (228 tests) | 228 passed, 1 skipped | PASS (no regressions) |

## Self-Check: PASSED

**Files claimed exist:**
- FOUND: tracer_ai/eval/protocols.py
- FOUND: tracer_ai/eval/prompts.py
- FOUND: tracer_ai/eval/llm_judge.py
- FOUND: tests/test_context.py
- FOUND: tests/test_judge_prompts.py
- FOUND: tests/test_llm_judge.py
- FOUND: tracer_ai/tracer/context.py (overwritten from 7-line stub)
- FOUND: tracer_ai/config.py (modified)
- FOUND: tracer_ai/tracer/span.py (modified)
- FOUND: tracer_ai/eval/__init__.py (modified)
- FOUND: .env.example (modified)
- FOUND: tests/conftest.py (modified)
- FOUND: tests/test_config_failfast.py (modified)

**Commits claimed exist (`git log --oneline | grep`):**
- FOUND: a243fba (Task 1)
- FOUND: 7c77224 (Task 2)
- FOUND: 26f5ca1 (Task 3)

## Next Phase Readiness

- Wave 2 plans (05-03 admin, 05-04 dispatcher + chat wiring, 05-06 calibration CLI) unblocked. All contracts importable.
- 05-04 will wire the Judge into the SSE chat handler post-final-frame using capture_context + dispatcher.enqueue, and emit the rag.eval span as a child of rag.request via the contextvar snapshot established here.
- 05-03 will surface PROMPT_VERSION + settings.bad_answer_faithfulness_threshold + settings.llm_judge_model via GET /admin/eval-config.
- No blockers; no architectural concerns.

---
*Phase: 05-quality-feedback*
*Completed: 2026-05-07*
