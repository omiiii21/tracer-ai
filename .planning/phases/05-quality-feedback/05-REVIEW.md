---
phase: 05-quality-feedback
reviewed: 2026-05-07T00:00:00Z
depth: standard
files_reviewed: 26
files_reviewed_list:
  - alembic/versions/0003_feedback_resolved.py
  - frontend/src/api/traces.ts
  - frontend/src/components/AppShell.tsx
  - frontend/src/pages/Dashboard.tsx
  - frontend/src/pages/Queue.tsx
  - frontend/src/pages/TraceDetail.tsx
  - frontend/src/router.tsx
  - frontend/src/types/trace.ts
  - tracer_ai/api/admin.py
  - tracer_ai/api/chat.py
  - tracer_ai/api/feedback.py
  - tracer_ai/api/lifespan.py
  - tracer_ai/api/schemas.py
  - tracer_ai/api/traces.py
  - tracer_ai/cli/__main__.py
  - tracer_ai/config.py
  - tracer_ai/eval/__init__.py
  - tracer_ai/eval/calibrate.py
  - tracer_ai/eval/dispatcher.py
  - tracer_ai/eval/llm_judge.py
  - tracer_ai/eval/prompts.py
  - tracer_ai/eval/protocols.py
  - tracer_ai/rag/pipeline.py
  - tracer_ai/rag/types.py
  - tracer_ai/tracer/context.py
  - tracer_ai/tracer/span.py
  - tracer_ai/tracer/store.py
findings:
  critical: 4
  warning: 11
  info: 4
  total: 19
status: issues_found
---

# Phase 5: Code Review Report

**Reviewed:** 2026-05-07
**Depth:** standard
**Files Reviewed:** 26 (one duplicate counted: `tracer_ai/tracer/store.py` appears in scope as part of the timeseries delivery)
**Status:** issues_found

## Summary

The Phase 5 quality + feedback delivery is structurally consistent with the locked invariants (no `opentelemetry-*` runtime imports; SDK isolation respected in `eval/llm_judge.py`; `tracer/` does not import `api/`; `print()` confined to `cli/__main__.py`; Pydantic v2 strict-mode + `extra="forbid"` everywhere). Pitfall #1 (contextvar capture before `_emit_root`) is correctly implemented in `pipeline.run_chat_stream` and Pitfall #3 (judge failures never fail user requests) is honored at every dispatch boundary in `eval/dispatcher.py` and the SSE generator in `api/chat.py`.

However, the EVAL-04 cost-attribution work is incomplete: the dispatcher computes `judge_cost_usd` but never stamps it on the `rag.eval` span. The dispatcher also catches `BaseException` in three places, swallowing `asyncio.CancelledError` and breaking cooperative shutdown. There is a small but real race in `EvalDispatcher.drain()` where tasks created after `_pending` is unpacked into `gather()` are not awaited. The new PATCH `/feedback/{trace_id}/resolved` endpoint returns a fabricated `resolved_at` timestamp on idempotent calls when no rows were updated, which misleads the frontend's optimistic invalidation flow. The diagnosis-tag panel forces a thumbs-down rating onto traces that have never been rated, silently flagging them in the user-flagged queue.

The blockers below must ship a fix before Phase 5 closes.

## Critical Issues

### CR-01: EVAL-04 incomplete — `judge_cost_usd` is computed but never persisted on the rag.eval span

**File:** `tracer_ai/eval/dispatcher.py:165-180`

**Issue:** `tracer_ai/tracer/span.py:36` defines the constant `RAG_EVAL_JUDGE_COST_USD: str = "rag.eval.judge_cost_usd"`. `tracer_ai/eval/llm_judge.py:197-200` computes `judge_cost_usd` and `tracer_ai/eval/protocols.py:46` adds it to `EvalScores`. But `EvalDispatcher._do_score` never reads `scores.judge_cost_usd` and never stamps `RAG_EVAL_JUDGE_COST_USD` on `eval_span.attrs`. The constant is imported nowhere in `dispatcher.py`. End result: the EVAL-04 fix lands the cost in `EvalScores` but it is silently dropped before reaching the trace store; the dashboard cannot sum judge spend.

**Fix:**
```python
# tracer_ai/eval/dispatcher.py — add to imports
from tracer_ai.tracer.span import (
    ERROR_TYPE,
    RAG_EVAL_FAITHFULNESS,
    RAG_EVAL_JUDGE_COST_USD,  # NEW
    RAG_EVAL_JUDGE_LATENCY_MS,
    RAG_EVAL_JUDGE_MODEL,
    RAG_EVAL_JUDGE_PROMPT_VERSION,
    RAG_EVAL_RELEVANCE,
)

# inside _do_score, after the latency_ms stamp (around line 174):
if scores is not None:
    if scores.faithfulness is not None:
        eval_span.attrs[RAG_EVAL_FAITHFULNESS] = scores.faithfulness
    if scores.relevance is not None:
        eval_span.attrs[RAG_EVAL_RELEVANCE] = scores.relevance
    eval_span.attrs[RAG_EVAL_JUDGE_LATENCY_MS] = scores.judge_latency_ms or int(
        (time.perf_counter() - t0) * 1000
    )
    eval_span.attrs[RAG_EVAL_JUDGE_COST_USD] = scores.judge_cost_usd  # NEW
    eval_span.payload = { ... }
```

---

### CR-02: Dispatcher catches `BaseException` — swallows `asyncio.CancelledError`, breaks cooperative cancellation

**File:** `tracer_ai/eval/dispatcher.py:154`, `tracer_ai/eval/dispatcher.py:185`, `tracer_ai/eval/dispatcher.py:201`

**Issue:** Three try/except blocks in `_do_score` catch `BaseException`:

```python
except BaseException as exc:   # line 154 — judge call
except BaseException as exc:   # line 185 — writer.emit
except BaseException as exc:   # line 201 — UPDATE traces
```

`BaseException` includes `asyncio.CancelledError`, `KeyboardInterrupt`, and `SystemExit`. When the lifespan finally block calls `eval_disp.drain(timeout=5.0)` and exceeds the timeout, the surrounding `asyncio.wait_for` cancels the gather — pending dispatcher tasks receive `CancelledError`. The catch-all swallows the cancellation and the task continues to run (especially the writer.emit catch on line 185 which sits in the `finally` block — it runs even after a cancelled judge call). This violates Pitfall #3's intent: yes, eval failures must not fail user requests, but cancellation must still propagate to allow shutdown to complete.

The same BaseException catch on line 201 wraps a synchronous `pool.acquire(timeout=2.0)` — if the lifespan's `await app.state.db_pool.close()` runs before this `_do_score` finishes, the pool is closed mid-acquire and the SQL execute will raise; we then swallow the failure rather than logging the pool-closed condition distinctly.

**Fix:** Catch `Exception` instead of `BaseException`. Let `CancelledError` propagate (it is the correct shutdown signal):
```python
except Exception as exc:  # not BaseException — let CancelledError propagate
    log.warning(
        "eval.judge_failed",
        trace_id=str(trace_id),
        error=str(exc),
        error_type=type(exc).__name__,
    )
    eval_span.attrs[ERROR_TYPE] = type(exc).__name__
```
Repeat at the writer.emit and UPDATE traces sites.

---

### CR-03: `EvalDispatcher.drain()` race — tasks enqueued during drain are never awaited

**File:** `tracer_ai/eval/dispatcher.py:216-236`, `tracer_ai/eval/dispatcher.py:91-106`

**Issue:** `drain()` reads `_pending`, sets `_stopped = True`, then unpacks `*self._pending` into `asyncio.gather`. There are two race windows:

1. **TOCTOU on `_stopped`:** In `enqueue` (line 91), the check `if self._stopped:` happens BEFORE `asyncio.create_task`. If `drain()` flips `_stopped` to `True` between the check and the `create_task`, the new task gets created and added to `_pending` but is never awaited (gather already snapshotted the set). The frontend SSE final frame triggers `enqueue()` from the request task — under shutdown pressure where requests are still completing as drain begins, this race is realistic, not theoretical.

2. **Set unpack vs. concurrent add:** `*self._pending` unpacks the set at the moment `gather()` is called. If a task is enqueued in the same event-loop tick after that unpack but before the `enqueue` task completes its `create_task` line, the new task is in `_pending` but excluded from gather.

The consequence is a leaked judge task that may try to use `self._pool` after lifespan close, raising `pool is closed` — and CR-02's BaseException catch will then swallow that failure, producing silent data loss (faithfulness UPDATE never runs).

**Fix:** Set `_stopped = True` first; then snapshot under a lock or accept "pending plus any newly-added tasks" by capturing the set under an `asyncio.Lock`:
```python
def __init__(self, ...) -> None:
    ...
    self._stop_lock = asyncio.Lock()

def enqueue(self, ...) -> None:
    if self._stopped:
        log.warning("eval_dispatch_after_stop", trace_id=str(trace_id))
        return
    # ... create_task ...

async def drain(self, timeout: float = 5.0) -> None:
    self._stopped = True
    # Iterate until the set is stable; new tasks are blocked by _stopped.
    snapshot = list(self._pending)
    if not snapshot:
        return
    try:
        await asyncio.wait_for(
            asyncio.gather(*snapshot, return_exceptions=True),
            timeout=timeout,
        )
    except TimeoutError:
        log.warning("eval.dispatcher_drain_incomplete", remaining=len(self._pending))
```
Setting `_stopped = True` BEFORE snapshotting closes the window: any `enqueue` that wins the race against the flag flip will still produce a task that IS in `_pending` at snapshot time. The remaining race (a task added between `_stopped = True` and `snapshot = list(...)`) is bounded by one event-loop tick because the `_stopped` flag is checked synchronously in `enqueue`. Documented as acceptable.

---

### CR-04: PATCH `/feedback/{trace_id}/resolved` returns a fabricated `resolved_at` when zero rows updated

**File:** `tracer_ai/api/feedback.py:124-138`

**Issue:**
```python
rows_updated = len(rows)
resolved_at = rows[0]["resolved_at"] if rows else datetime.now(UTC)
```
When `rows_updated == 0` (idempotent re-PATCH of an already-resolved trace, or PATCH against an orphan trace_id), the response body carries `resolved_at = datetime.now(UTC)` — a value that does not exist in any database row. Two consequences:

1. **Frontend misuse:** `frontend/src/pages/Queue.tsx:108-115` invokes `markResolved` and on success invalidates `["queue-health"]`. The Dashboard's 5th KpiCard reads `resolved_this_week` from `/admin/queue-health`, which counts rows where `resolved_at >= NOW() - INTERVAL '7 days'`. The fabricated `resolved_at` does not contribute to that count (correct), but the UI shows a fresh timestamp implying a successful resolution event. Operators clicking "Mark Resolved" twice in a row see two "successful" responses for actions where the second was a no-op.

2. **Contract violation:** The Pydantic model `FeedbackResolveResponse` (`schemas.py:108-126`) requires `resolved_at: datetime`, and the docstring claims it carries the resolution moment. With `rows_updated=0`, the field carries a fictional time — no caller can distinguish a real resolution from a re-PATCH unless they read `rows_updated`.

**Fix:** Make `resolved_at` optional and only populate it when rows were actually updated:
```python
# schemas.py
class FeedbackResolveResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trace_id: UUID
    resolved_at: datetime | None = None  # None when rows_updated == 0
    rows_updated: Annotated[int, Field(ge=0)]

# feedback.py
resolved_at = rows[0]["resolved_at"] if rows else None
```
The frontend type in `frontend/src/types/trace.ts:83-87` will need to mirror the change (`resolved_at: string | null`).

## Warnings

### WR-01: `frontend/src/pages/TraceDetail.tsx` — selecting a diagnosis tag silently downvotes an unrated trace

**File:** `frontend/src/pages/TraceDetail.tsx:78-83`

**Issue:**
```typescript
const ratingToSend: 1 | -1 = feedbackRating ?? -1;
await postFeedback({
  trace_id: traceId,
  rating: ratingToSend,
  diagnosis_tag: newTag === "none" ? null : newTag,
});
```
When a trace has no prior feedback (`feedbackRating === null`), tagging a diagnosis defaults the rating to `-1` (thumbs down). The trace then appears in the User-flagged queue (`feedback=down` filter) without any explicit user input. An operator using the tagger as a triage / labeling tool to categorize a borderline trace inadvertently flags it as bad. The accompanying helper text ("Selecting a tag records a new feedback row...") does not mention that an absent rating becomes a downvote.

**Fix:** Either disable the diagnosis-tag panel entirely when `feedbackRating === null`, OR change the default to `1` (thumbs up), OR add explicit UI text "No prior rating — this will mark the trace as thumbs-down" with confirmation. The principle of least surprise points to disabling until the user has explicitly rated.

---

### WR-02: Mock judge type widening — `BaseException` allows `KeyboardInterrupt`/`SystemExit` as test inputs

**File:** `tracer_ai/eval/llm_judge.py:236, 249-250`

**Issue:** `MockJudge(raise_on_call: type[BaseException] | None = None)` and `raise self._raise_on_call("...")`. Passing `BaseException` widens beyond what test code should be able to inject: a unit test can construct `MockJudge(raise_on_call=KeyboardInterrupt)` and unintentionally mask process-shutdown semantics in the test harness. Combined with CR-02's `BaseException` catch in the dispatcher, this is the path by which a test's intentional-shutdown signal would be silently swallowed by the production code under test.

**Fix:** Restrict to `type[Exception] | None`. Tests that want to simulate cancellation should use `asyncio.CancelledError` explicitly via a separate code path that documents the intent.

---

### WR-03: Inconsistent UUID parameter binding for `traces.id` between modules

**File:** `tracer_ai/eval/dispatcher.py:197-200` vs `tracer_ai/rag/pipeline.py:384-387, 441-444` vs `tracer_ai/api/feedback.py:71-74`

**Issue:** Same UUID column written/read with three different binding styles:
- `dispatcher.py:199`: `trace_id` (raw `uuid.UUID` object)
- `pipeline.py:386, 444`: `str(trace_id)` (string)
- `feedback.py:73`: `body.trace_id` (raw `uuid.UUID` object)

asyncpg accepts both, but mixing styles invites future confusion. The `traces.id` column is `UUID NOT NULL` per the alembic migration; the canonical binding is the raw object. The inconsistency is a maintenance smell: a future developer porting the dispatcher to a different driver may not know which form is expected.

**Fix:** Standardize on raw UUID throughout the codebase (asyncpg's preferred form). Update `pipeline.py:386` and `pipeline.py:444` to `trace_id` (drop `str()`); the existing `INSERT` at pipeline.py:188 and `WHERE id = $1::uuid` casts in `tracer/store.py:189` are unchanged.

---

### WR-04: `EvalDispatcher` may UPDATE the `traces` table after the asyncpg pool is closed

**File:** `tracer_ai/eval/dispatcher.py:193-206`

**Issue:** Even with CR-03 fixed, an in-flight task that has already passed the `_stopped` check but is still inside `_do_score` may try to `pool.acquire(timeout=2.0)` after the lifespan's `await app.state.db_pool.close()` has run. The drain awaits up to 5s but `pool.close()` runs in the same `finally` block immediately after; if drain succeeds the task is done, but if drain times out the leaked task continues into the closed pool. The current code catches `BaseException` (CR-02) so the failure is silenced.

**Fix:** Two layers — fix CR-02 (catch `Exception`, log distinctly when the pool is closed) AND ensure drain timeout is honored by cancelling the leaked tasks:
```python
async def drain(self, timeout: float = 5.0) -> None:
    self._stopped = True
    snapshot = list(self._pending)
    if not snapshot:
        return
    try:
        await asyncio.wait_for(
            asyncio.gather(*snapshot, return_exceptions=True),
            timeout=timeout,
        )
    except TimeoutError:
        log.warning("eval.dispatcher_drain_incomplete", remaining=len(self._pending))
        for task in snapshot:
            if not task.done():
                task.cancel()
        # Wait briefly for cancellations to propagate.
        await asyncio.gather(*snapshot, return_exceptions=True)
```
With CR-02 fixed (catch Exception, not BaseException), the cancellation propagates and the task exits cleanly without ever reaching `pool.acquire`.

---

### WR-05: `_BUCKET_BY_WINDOW` not declared `Final` — accidental mutation pivots into SQL injection

**File:** `tracer_ai/tracer/store.py:61-66`, `tracer_ai/tracer/store.py:394-485`

**Issue:** The `timeseries()` SQL composer uses f-string interpolation of `unit`, `interval`, and `since` strings sourced from the module-level `_BUCKET_BY_WINDOW` dict. The defense is that the dict is hardcoded and the route's `Literal["1h","24h","7d","30d"]` validation rejects all other inputs. Both defenses hold today.

But `_BUCKET_BY_WINDOW: dict[str, tuple[str, str, str]]` is not annotated `typing.Final` and is not frozen — a downstream test fixture, monkeypatch, or future code path could mutate the dict to include attacker-controlled values. Defense-in-depth is missing.

**Fix:**
```python
from typing import Final
_BUCKET_BY_WINDOW: Final[dict[str, tuple[str, str, str]]] = {
    "1h": ("minute", "1 minute", "1 hour"),
    ...
}
```
`Final` does not prevent runtime mutation but signals intent and gates mypy. For runtime immutability, switch to `types.MappingProxyType(_BUCKET_BY_WINDOW)`.

---

### WR-06: `set_current_span(root_for_ctx)` token never reset — pollutes the request task contextvar

**File:** `tracer_ai/rag/pipeline.py:502`

**Issue:** `set_current_span` returns a `Token[Span | None]` for use with `_current_span.reset(token)`. The call site discards the token. The contextvar mutation persists in the SSE generator's task context for the rest of the request. Downstream code in the same task that queries `current_span()` (e.g., the SSE error path that may emit a span) sees this stale rag.request stub even though `_emit_root` has already finalized and emitted the real root span.

The current Phase 5 code does not query `current_span()` later in the same task (the dispatcher works in its own task with its own contextvar copy), so the bug is latent. But any future code path that emits a span from inside the chat SSE generator AFTER iteration would parent its span under the stub rag.request, creating a parent-after-end ordering anomaly in trace data.

**Fix:**
```python
token = set_current_span(root_for_ctx)
try:
    ctx_snapshot = capture_context()
    ...
    yield ChatFinalEvent(...)
finally:
    _current_span.reset(token)
```
Or use a `contextlib.contextmanager` wrapper. Document that the contextvar is expected to be `None` outside the snapshot window.

---

### WR-07: Defensive `getattr` on Pydantic model masks legitimate AttributeError

**File:** `tracer_ai/eval/dispatcher.py:211-213`

**Issue:**
```python
log.info(
    "eval.scored",
    trace_id=str(trace_id),
    faithfulness=getattr(scores, "faithfulness", None),
    relevance=getattr(scores, "relevance", None),
    error_type=eval_span.attrs.get(ERROR_TYPE),
)
```
`scores` is either `None` (judge failed) or an `EvalScores` Pydantic model that ALWAYS has `.faithfulness` and `.relevance` attributes (declared at `protocols.py:38-39`). The `getattr(scores, "faithfulness", None)` defense suppresses any future AttributeError that should be a bug signal. Replacing `EvalScores` with a duck-typed object that omits these fields (e.g., a test stub) would silently log `None` instead of failing the test.

**Fix:**
```python
log.info(
    "eval.scored",
    trace_id=str(trace_id),
    faithfulness=scores.faithfulness if scores is not None else None,
    relevance=scores.relevance if scores is not None else None,
    error_type=eval_span.attrs.get(ERROR_TYPE),
)
```

---

### WR-08: `Dashboard.tsx` uses `window` as state name, shadowing the global `window` object

**File:** `frontend/src/pages/Dashboard.tsx:64-76`

**Issue:**
```typescript
const [window, setWindow] = React.useState<TimeseriesWindow>("24h");
...
queryFn: () => getTimeseries(window),
```
`window` shadows the browser's global `window` reference within this scope. Any subsequent use of `window.location` or `window.scrollTo` in this component would refer to the React state instead of the DOM global. The current code does not use the global `window` in `QualityCharts`, so this is currently latent. It still hurts grep-ability and confuses future maintainers.

**Fix:** Rename to `timeseriesWindow` or `selectedWindow`:
```typescript
const [timeseriesWindow, setTimeseriesWindow] = React.useState<TimeseriesWindow>("24h");
...
queryFn: () => getTimeseries(timeseriesWindow),
```

---

### WR-09: Diagnosis-tag UI accepts arbitrary backend strings, falling outside the locked v1 set

**File:** `frontend/src/pages/TraceDetail.tsx:65-67`

**Issue:**
```typescript
const [tag, setTag] = React.useState<DiagnosisTag | "none">(
  (current as DiagnosisTag | null) ?? "none",
);
```
`current: string | null` from the backend is type-asserted as `DiagnosisTag` (a closed Literal). The Pydantic schema explicitly leaves `diagnosis_tag: str | None` open (schemas.py:96, "reserved-but-flexible") so calibration can add categories. When that happens, the frontend's `as DiagnosisTag` casts a non-member string into the closed type. The Select component's `value=tag` will then reference a string that has no matching `<SelectItem>`, so Radix renders no selection — the operator sees an empty Select even though the backend has a tag attached.

**Fix:** Detect the unknown-tag case and either render it as a dimmed read-only label or as a synthesized SelectItem labeled "(legacy: PromptDriftV2)". Minimal patch:
```typescript
const isKnownTag = (s: string | null): s is DiagnosisTag =>
  s !== null && (DIAGNOSIS_TAGS as readonly string[]).includes(s);

const initial: DiagnosisTag | "none" = isKnownTag(current) ? current : "none";
const [tag, setTag] = React.useState<DiagnosisTag | "none">(initial);
```

---

### WR-10: `MockJudge.score` in EVAL-04 fix can now return `EvalScores` whose `faithfulness=None` is treated as a successful score

**File:** `tracer_ai/eval/llm_judge.py:231-265`, `tracer_ai/eval/dispatcher.py:167-205`

**Issue:** `MockJudge(faithfulness=None)` returns an `EvalScores` with `faithfulness=None`. In `dispatcher._do_score`, `scores is not None` (the mock returned a valid object), so the dispatcher enters the success branch but skips the `RAG_EVAL_FAITHFULNESS` stamp (line 168 guard) and skips the `UPDATE traces` (line 193 `scores.faithfulness is not None` guard). The structlog event `eval.scored` (line 208) emits with `error_type=None` despite faithfulness=None — there's no signal that this trace ended without a faithfulness score.

In production, `AnthropicJudge.score` always returns `faithfulness` populated from `tool_input.get("faithfulness", 0.0)` (line 208), so this case never arises. But Pydantic allows `faithfulness: float | None` (protocols.py:38), so ANY future judge implementation returning None falls into a silent-skip path with no rag.eval `error.type` and no UPDATE. The dispatcher's failure-span path is bypassed.

**Fix:** Stamp `ERROR_TYPE` when the dispatcher receives `scores is not None` but `scores.faithfulness is None`:
```python
if scores is not None and scores.faithfulness is None:
    eval_span.attrs[ERROR_TYPE] = "JudgeReturnedNullFaithfulness"
```
Or constrain the `Judge` protocol so the success path requires non-null `faithfulness` (tighten `EvalScores.faithfulness: float = Field(ge=0.0, le=1.0)` and let the dispatcher rely on Pydantic for that). Either approach is acceptable; the second is stricter.

---

### WR-11: Cursor pagination semantics break for `sort_by=faithfulness_asc`

**File:** `tracer_ai/tracer/store.py:298-311`

**Issue:** The cursor is keyed on `(started_at, id)`, but for `sort_by=faithfulness_asc` the rows are ordered by `faithfulness ASC NULLS LAST, started_at DESC, id DESC`. The cursor predicate `(started_at, id) < ($7::timestamptz, $8::uuid)` uses lexicographic comparison on `(started_at, id)` only. Result: when a client paginates a faithfulness-sorted result, the second page may include rows with faithfulness >= the previous page's last faithfulness AND skip rows with the same faithfulness but earlier started_at.

The plan-level docstring at line 302-306 acknowledges the limitation ("acceptable for small datasets <1000 judge-flagged traces; Phase 6 may add a faithfulness-aware cursor variant"). This is documented but the queue page uses `limit=50` and a poorly-tuned threshold could easily exceed 1000 unresolved judge-flagged traces in production. The bug is shipping with an explicit acceptance note rather than a guard.

**Fix:** Either (a) ship the faithfulness-aware cursor now (encode `(faithfulness, started_at, id)` and adjust the predicate), or (b) make Phase 5 explicitly truncate the result when the total exceeds the cursor's correctness bound:
```python
if filters.sort_by == "faithfulness_asc" and len(rows) > limit:
    next_cursor = None  # disable pagination — first page only
    log.warning("queue.cursor_disabled_for_faithfulness_sort", limit=limit)
```
At minimum, the Queue.tsx page should not allow paging past page 1 in the judge-flagged tab.

## Info

### IN-01: `_is_source_request` / `_is_urls_request` discriminator helpers are dead-code-equivalent

**File:** `tracer_ai/api/admin.py:125-132, 183-188`

**Issue:** The helpers exist solely so `mypy` can narrow the `body: IngestRequest` discriminated union, but the consumer at line 183-188 then re-checks `isinstance(body, IngestSourceRequest)` and `isinstance(body, IngestUrlsRequest)` inside the `_is_*_request` branches. Each isinstance check happens twice. The double-check is harmless but reads as redundant.

**Fix:** Use the standard discriminated-union pattern with a `match` statement or replace the helpers with a single isinstance ladder:
```python
match body:
    case IngestSourceRequest():
        source_value = body.source
    case IngestUrlsRequest():
        urls_value = body.urls
```

---

### IN-02: `chat.py` uses `getattr` with default to defend against missing `eval_dispatcher`, but the lifespan always sets it (possibly to None)

**File:** `tracer_ai/api/chat.py:87`, `tracer_ai/api/lifespan.py:165`

**Issue:** `getattr(request.app.state, "eval_dispatcher", None)` is a defensive read, but `lifespan.py:165` ALWAYS sets `app.state.eval_dispatcher` (to `None` on construction failure, to a real dispatcher otherwise). The defense is for the case where the lifespan exception handler did not run or app.state was reset — which cannot happen in normal operation. Cleaner:
```python
dispatcher = request.app.state.eval_dispatcher
```

---

### IN-03: Pricing constants in `Settings` are not bounded

**File:** `tracer_ai/config.py:123-142`

**Issue:** The four `pricing_claude_*` floats have no `ge=0.0` bound. A negative pricing env var would produce a negative `judge_cost_usd`, which Pydantic later rejects in `EvalScores.judge_cost_usd: float = Field(ge=0.0)` — but the rejection is one layer late and produces a less-helpful error message ("validation error in EvalScores" instead of "PRICING_CLAUDE_HAIKU_INPUT_PER_MTOK must be >= 0").

**Fix:**
```python
pricing_claude_haiku_input_per_mtok: float = Field(default=0.80, ge=0.0, ...)
```
Apply to all four pricing fields.

---

### IN-04: `eval/llm_judge.py:186` defensive raise after `for ... break` is genuinely unreachable

**File:** `tracer_ai/eval/llm_judge.py:186-187`

**Issue:**
```python
if msg is None:  # pragma: no cover -- only reachable via logic bug
    raise RuntimeError(f"judge call exited without a message; last error: {last_exc!r}")
```
The for loop has only two paths out: `break` after a successful call (sets `msg`) or `raise` on the second exception (control leaves the function). If the loop falls through without break or raise, that means iteration ended without either — which `for attempt in (1, 2):` guarantees cannot happen. The `pragma: no cover` is correctly applied. Cosmetically, the defensive guard adds noise; consider removing it. (Listed as Info because removing it has ~zero practical benefit; just noting.)

---

_Reviewed: 2026-05-07_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
