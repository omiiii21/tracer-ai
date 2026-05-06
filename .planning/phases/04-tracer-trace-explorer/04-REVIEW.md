---
phase: 04-tracer-trace-explorer
reviewed: 2026-05-06T00:00:00Z
depth: standard
files_reviewed: 35
files_reviewed_list:
  - alembic/versions/0002_traces_denorm.py
  - frontend/package.json
  - frontend/src/api/traces.ts
  - frontend/src/components/AppShell.tsx
  - frontend/src/components/MetadataStrip.tsx
  - frontend/src/components/SpanWaterfall.tsx
  - frontend/src/components/ui/select.tsx
  - frontend/src/components/ui/slider.tsx
  - frontend/src/components/ui/table.tsx
  - frontend/src/components/ui/tabs.tsx
  - frontend/src/components/ui/tooltip.tsx
  - frontend/src/pages/Dashboard.tsx
  - frontend/src/pages/TraceDetail.tsx
  - frontend/src/router.tsx
  - frontend/src/types/trace.ts
  - tests/integration/test_alembic_reversibility.py
  - tests/integration/test_lifespan_drain.py
  - tests/integration/test_pipeline_with_postgres_writer.py
  - tests/integration/test_traces_api.py
  - tests/perf/test_trace_write_p95.py
  - tests/test_feedback_route.py
  - tests/test_pipeline.py
  - tests/test_writer_protocol.py
  - tests/unit/tracer/test_postgres_writer.py
  - tests/unit/tracer/test_queue.py
  - tracer_ai/api/feedback.py
  - tracer_ai/api/lifespan.py
  - tracer_ai/api/main.py
  - tracer_ai/api/schemas.py
  - tracer_ai/api/traces.py
  - tracer_ai/rag/pipeline.py
  - tracer_ai/tracer/exporters/postgres.py
  - tracer_ai/tracer/exporters/queue.py
  - tracer_ai/tracer/store.py
  - tracer_ai/tracer/writer.py
findings:
  blocker: 6
  warning: 11
  total: 17
status: issues_found
---

# Phase 04: Code Review Report

**Reviewed:** 2026-05-06
**Depth:** standard
**Files Reviewed:** 35
**Status:** issues_found

## Summary

Phase 04 ships the trace explorer (FastAPI `GET /traces`, `GET /traces/{trace_id}`), the trace-write background pipeline (`PostgresTraceWriter` + `BoundedDropOldestQueue` + `SpanConsumer`), the `0002` alembic migration adding denormalized scalar columns, and the React dashboard / trace detail UI. The code is generally well-typed, well-commented, and tested against fake pools.

Six BLOCKER-class defects exist, mostly in the consumer / shutdown path: the consumer's `run()` busy-loops on a hot CPU when its idle/empty path crosses the flush interval; the shutdown drain and the still-running consumer race for queue items so spans buffered inside the consumer's in-memory batch are silently lost on shutdown; the `stop_accepting` field is set on shutdown but the consumer never reads it; the dashboard `Slider` is wired with `defaultValue` (uncontrolled) but the surrounding component treats it as controlled, breaking external state resets; one batch flush path lacks a pool acquire timeout; and the dashboard datetime-local inputs ship naive (no-tz) timestamps to a `timestamptz` column. Eleven WARNING-class issues round out the report.

## BLOCKER Issues

### CR-01: `SpanConsumer.run()` busy-loops on idle event loop after flush interval elapses

**File:** `tracer_ai/tracer/exporters/postgres.py:73-110`

**Issue:** `batch_started_at` is initialized at loop entry and is only refreshed after a successful flush (line 110). When the queue is empty and time passes, `elapsed = time.monotonic() - batch_started_at` exceeds `_FLUSH_INTERVAL` (0.250s), so `remaining = max(0.0, 0.250 - elapsed) == 0.0`. `asyncio.wait_for(self._queue.get(), timeout=0)` then raises `TimeoutError` immediately on each iteration without yielding meaningful sleep, and `should_flush` stays `False` (batch still empty). The result is a tight CPU-hot loop spinning thousands of times per second whenever the trace queue is empty for longer than 250 ms — i.e. whenever the chatbot is idle.

**Fix:**
```python
async def run(self) -> None:
    batch: list[Span] = []
    batch_started_at: float | None = None  # set when first item arrives
    while True:
        if batch_started_at is None:
            # Idle path: block indefinitely on the first item.
            try:
                span = await self._queue.get()
            except asyncio.CancelledError:
                raise
            batch.append(span)
            batch_started_at = time.monotonic()
            continue
        elapsed = time.monotonic() - batch_started_at
        remaining = max(0.0, _FLUSH_INTERVAL - elapsed)
        try:
            span = await asyncio.wait_for(self._queue.get(), timeout=remaining)
            batch.append(span)
        except TimeoutError:
            pass
        except asyncio.CancelledError:
            if batch:
                try:
                    await self._flush(batch)
                except Exception as exc:
                    log.exception("tracer.consumer_flush_on_cancel_failed", error=str(exc))
            raise
        if len(batch) >= _BATCH_SIZE or time.monotonic() - batch_started_at >= _FLUSH_INTERVAL:
            try:
                await self._flush(batch)
            except Exception as exc:
                log.exception("tracer.consumer_flush_failed", batch_size=len(batch), error=str(exc))
            batch = []
            batch_started_at = None
```

### CR-02: Shutdown drain races with running consumer task; spans buffered in consumer's in-memory batch are silently lost

**File:** `tracer_ai/api/lifespan.py:148-166`, `tracer_ai/tracer/exporters/postgres.py:73-132`

**Issue:** On shutdown, the lifespan finally block calls `consumer.drain()` while `consumer_task` (running `consumer.run()`) is still alive. Both consumers pull from the same queue. If `run()` has already moved N items into its local `batch: list[Span]` and is stalled inside `await self._flush(batch)`, the queue's `qsize()` returns 0 and `drain()` exits immediately thinking there is nothing to do. The lifespan then `consumer_task.cancel()`s the task. The cancellation is delivered to whatever `await` `run()` is currently sitting on. If it lands on the `_flush` SQL call, the in-memory `batch` is dropped without being persisted. The CancelledError handler in `run()` (lines 86-95) only flushes when the cancellation lands on the `wait_for(get(...))` await, NOT when it lands inside `_flush`. End result: spans pulled out of the queue but not yet committed are lost on every shutdown path that times out the flush.

**Fix:** Stop the consumer task *first*, then drain remaining queue items synchronously from the lifespan:
```python
finally:
    if consumer_task is not None:
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            pass
        # CancelledError handler in run() already flushed any in-memory batch.
    if consumer is not None and queue_obj is not None:
        try:
            await asyncio.wait_for(consumer.drain(), timeout=5.0)
        except TimeoutError:
            log.warning("tracer.shutdown_drain_incomplete", remaining=queue_obj.qsize())
    await app.state.db_pool.close()
```
Additionally, the cancel-handler in `run()` (postgres.py:86-95) only flushes when cancellation lands on the `wait_for` line. Wrap the `_flush` call inside `run()` in its own try/except CancelledError so an in-flight flush also drains its batch on cancel — or refactor so the consumer signals "stopped" cooperatively (see CR-03) and drains its own batch before exit.

### CR-03: `consumer.stop_accepting` is set during shutdown but never read by the consumer

**File:** `tracer_ai/tracer/exporters/postgres.py:71`, `tracer_ai/api/lifespan.py:151`

**Issue:** `SpanConsumer.__init__` declares `self.stop_accepting: bool = False` with the comment "reserved for shutdown signaling (D-4.10)". `lifespan.py:151` sets `consumer.stop_accepting = True` on shutdown. Nothing inside `run()`, `drain()`, or `_flush()` ever inspects `stop_accepting`. The flag is dead state: shutdown writes a value that the consumer never reads, so the cooperative-stop intent of D-4.10 is not actually implemented. Combined with CR-02 this means cancellation is the only stop signal, with the loss-of-batch consequences described above.

**Fix:** Either remove the field entirely and rely on cancellation, or actually use it:
```python
async def run(self) -> None:
    while not self.stop_accepting:
        ...
    # drain remaining batch on cooperative stop
    if batch:
        try:
            await self._flush(batch)
        except Exception as exc:
            log.exception("tracer.consumer_stop_flush_failed", error=str(exc))
```
And in lifespan, set `stop_accepting = True` *before* `cancel()` so the loop exits cleanly. Either choice is fine, but the current "set but never read" state is a correctness bug masquerading as documentation.

### CR-04: Dashboard `Slider` is wired with `defaultValue` (uncontrolled) but treated as controlled — external resets to `filters` do not propagate to slider thumb

**File:** `frontend/src/pages/Dashboard.tsx:217-232`

**Issue:** The component uses `defaultValue={[filters.min_faithfulness ?? 0]}`. Radix `Slider`'s `defaultValue` is the *uncontrolled* prop and is read only on first mount. The slider's internal state then drifts away from `filters.min_faithfulness`. When `filters` is reset programmatically (e.g., a future "Clear filters" button, browser back/forward navigation through query state, or the `staleTime: 0` refetch repopulating from props), the thumb position remains stuck at the user's last drag value. Coupled with the queryKey memo that includes `filters.min_faithfulness`, this creates an "out of sync" state where the displayed thumb position no longer matches the actual filter being applied to results.

**Fix:** Use the controlled `value` prop instead:
```tsx
<Slider
  value={[filters.min_faithfulness ?? 0]}
  max={1}
  step={0.05}
  onValueChange={(v) =>
    setFilters({
      ...filters,
      min_faithfulness: v[0] === 0 ? undefined : v[0],
    })
  }
/>
```

### CR-05: `SpanConsumer._flush` acquires a pool connection without a timeout — pool-exhaustion deadlocks the consumer

**File:** `tracer_ai/tracer/exporters/postgres.py:158`

**Issue:** Every other `pool.acquire(...)` call site in this codebase passes `timeout=2.0` (pipeline.py:168, pipeline.py:368, pipeline.py:410, lifespan.py:71, feedback.py:53). The `_flush` path is the high-frequency one — every 250 ms or every 50 spans, whichever comes first — and is the most likely site to encounter pool saturation. A bare `self._pool.acquire()` blocks forever when the pool is exhausted. Combined with CR-02 / CR-03, an exhausted pool means `_flush` never returns, the consumer task can't be cancelled cleanly, and the lifespan drain times out and discards spans on every shutdown.

**Fix:**
```python
async with self._pool.acquire(timeout=2.0) as conn:
    ...
```
Match the timeout already used by the pipeline write path. If `_flush` hits the timeout, the existing `try/except Exception` in `run()` will log the failure and reset the batch — preferable to an indefinite deadlock.

### CR-06: Dashboard `datetime-local` inputs ship naive timestamps to a `timestamptz` filter; query results depend on server timezone

**File:** `frontend/src/pages/Dashboard.tsx:174-194`, `tracer_ai/tracer/store.py:252-253`

**Issue:** `<Input type="datetime-local">` produces strings like `"2026-05-06T10:30"` with no timezone. These are passed verbatim to `searchParams.since` / `searchParams.until` (frontend/src/api/traces.ts:26-27), then parsed by FastAPI Pydantic `datetime` (which produces a *naive* datetime), and then bound into asyncpg `WHERE started_at >= $2 AND started_at <= $3` against a `timestamptz` column. asyncpg interprets naive datetimes against the connection's session timezone. Result: a user in UTC+5:30 entering "2026-05-06T10:30" actually filters on a server-time interpretation that is 5.5 hours off from what they meant. Filter results silently disagree with intent. Worst case, a "since 09:00" filter shows traces from before 09:00. T-04-04-09 mitigations rely on this filter being correct.

**Fix:** Either client-side append local timezone before calling the API, e.g.:
```ts
function localToIso(dt: string | undefined): string | undefined {
  if (!dt) return undefined;
  // datetime-local: "2026-05-06T10:30" -> Date treats as local -> .toISOString() -> UTC
  return new Date(dt).toISOString();
}
// in caller:
if (filters.since) searchParams.since = localToIso(filters.since)!;
```
Or normalize on the server side before passing to asyncpg (less robust — frontend may also use the value for display). Add a unit test in `test_traces_api.py` that asserts a since filter at the DST boundary returns the right rows.

## WARNING Issues

### WR-01: `pipeline.py` retrieve / prompt-assemble stages catch `BaseException` (not `Exception`)

**File:** `tracer_ai/rag/pipeline.py:194, 250`

**Issue:** `except BaseException:` swallows `KeyboardInterrupt`, `SystemExit`, and `asyncio.CancelledError` to set the failure flag, then re-raises. The re-raise preserves correctness, but `BaseException` is rarely the right base — it forces handling of `SystemExit` paths that other code may rely on. More importantly, on `CancelledError`, the `finally` blocks emit additional spans and call `await self.writer.emit(...)`, which means a cancelled task does additional `await` work after cancellation — that work itself can be cancelled again, leaving span emission half-done.

**Fix:** Use `except Exception` for the failure-tracking flag; keep `try/finally` for span emission so cancellation still flushes:
```python
try:
    chunks = await self.retriever.retrieve(q_emb, self.top_k)
except Exception:
    retrieve_failed = True
    raise
```
If you specifically want to track CancelledError as well, do `except (Exception, asyncio.CancelledError):` — but never `BaseException`.

### WR-02: Alembic 0002 only adds the 2026-08 partition; no automation for 2026-09+

**File:** `alembic/versions/0002_traces_denorm.py:49-67`

**Issue:** The docstring acknowledges Pitfall 4 ("extend spans partitions to 2026-08"), but the project ships with no scheduled mechanism to roll forward partitions month-by-month. Today is 2026-05-06; this migration takes the table through 2026-08-31. A trace inserted on 2026-09-01 will fail with `no partition of relation "spans" found for row`. This is a guaranteed production outage on a known calendar date.

**Fix:** Either (a) ship a follow-up migration for 2026-09 / 2026-10 / 2026-11 covering at least 6 months ahead, OR (b) add a startup hook in `lifespan.py` that idempotently creates the next 2 months of partitions on every boot. Option (b) is more robust:
```python
async def _ensure_spans_partitions(pool: asyncpg.Pool) -> None:
    today = datetime.now(UTC).date()
    for offset in range(0, 4):  # this month + 3 ahead
        start = (today.replace(day=1) + relativedelta(months=offset))
        end = start + relativedelta(months=1)
        partition_name = f"spans_y{start.year}m{start.month:02d}"
        async with pool.acquire(timeout=2.0) as conn:
            await conn.execute(
                f"CREATE TABLE IF NOT EXISTS {partition_name} PARTITION OF spans "
                f"FOR VALUES FROM ('{start}') TO ('{end}');"
            )
```

### WR-03: `feedback.py` does not check that `traces` row exists before writing the denorm UPDATE

**File:** `tracer_ai/api/feedback.py:67-71`

**Issue:** The docstring explicitly accepts orphan feedback ("affects 0 rows" is documented). However the success log at line 76 emits `feedback_recorded` regardless of whether the UPDATE actually matched a row. If a forged or stale `trace_id` is posted, the audit log claims feedback was recorded against a trace that does not exist. The dashboard will then never surface it (it's joined on traces). This is a silent inconsistency between the audit log and the data.

**Fix:** Capture the UPDATE's row count and either log a distinct event (`feedback_recorded_orphan`) or return a 404. Minimal change:
```python
update_result = await conn.execute(
    "UPDATE traces SET feedback_rating = $1 WHERE id = $2",
    body.rating, body.trace_id,
)
# asyncpg returns "UPDATE n"
matched = int(update_result.rsplit(" ", 1)[-1])
log.info(
    "feedback_recorded",
    trace_id=str(body.trace_id),
    rating=body.rating,
    orphan=(matched == 0),
)
```

### WR-04: `BoundedDropOldestQueue.qsize()` reads `len(self._deque)` without holding `self._lock`

**File:** `tracer_ai/tracer/exporters/queue.py:81-83`

**Issue:** The docstring explicitly says "not under lock" — but the consumer's `drain()` method (`postgres.py:116`) uses `qsize()` to decide whether to keep pulling from the queue. Under concurrent producers + consumers, `len(deque)` can return a stale value or temporarily inconsistent value during a `popleft()`/`append()` pair under saturation. CPython's `deque.__len__` is currently atomic, so this is fine in practice on CPython, but the contract is fragile and the comment in code makes the staleness sound intentional and load-bearing.

**Fix:** Use `qsize()` only as a hint and rely on `wait_for(get(), timeout=...)` for actual dequeue (drain() already does this). Either acquire the lock in `qsize()` or drop `qsize()` from the drain loop in favour of a TimeoutError-driven exit.

### WR-05: `frontend/src/api/traces.ts` does not encode `trace_id` into the path

**File:** `frontend/src/api/traces.ts:38`

**Issue:** `_api.get(\`traces/${traceId}\`)` interpolates `traceId` directly into the URL with no encoding. A maliciously-crafted `traceId` containing `..` or `?` segments would alter the URL meaning. In v1 single-user local dev this is benign (only the operator's own UI provides the value), but the function takes a typed string — a future caller could pass user-controllable input. Use `encodeURIComponent(traceId)`.

**Fix:**
```ts
return _api.get(`traces/${encodeURIComponent(traceId)}`).json<TraceDetailResponse>();
```

### WR-06: `SpanWaterfall` uses `<pre>` as direct sibling of a `<button>` inside fragment — accessibility / nested-button issue if `attrs` is later made interactive

**File:** `frontend/src/components/SpanWaterfall.tsx:91-99`

**Issue:** The expanded JSON `<pre>` is rendered as a sibling of a `<button>` row via `<>...</>`. When the parent `SpanWaterfall` wraps these in a `flex flex-col`, the `<pre>` lands as a direct child of the flex container. That's fine today, but `aria-controls={\`span-attrs-${span.span_id}\`}` on the button promises a related region — it should be wrapped in a `<div role="region" aria-labelledby="...">` for screen readers. Also, if the JSON ever needs to be selectable / copyable, it must remain a sibling (not a child of the button) — currently OK but future maintainers may unintentionally nest.

**Fix:**
```tsx
{expanded && (
  <div
    id={`span-attrs-${span.span_id}`}
    role="region"
    aria-label={`Attributes for span ${span.name}`}
  >
    <pre className="text-xs font-mono bg-muted p-2 rounded overflow-auto mx-4 my-1">
      {JSON.stringify(span.attrs, null, 2)}
    </pre>
  </div>
)}
```

### WR-07: `Dashboard.tsx` slider check `v[0] === 0 ? undefined : v[0]` is brittle to floating-point drift

**File:** `frontend/src/pages/Dashboard.tsx:228`

**Issue:** Slider with `step={0.05}` returning 0 starting from 0 is exact in this case, but if the step ever changes to a non-power-of-two fraction (e.g., 0.1), the user sliding to "0" may produce 5.551e-17. Strict `=== 0` then fails to clear the filter.

**Fix:** Use a tolerance:
```ts
min_faithfulness: v[0] < 0.001 ? undefined : v[0],
```

### WR-08: Tooltip component file exports `TooltipContent` but not the rest of the standard shadcn tooltip API

**File:** `frontend/src/components/ui/tooltip.tsx`

**Issue:** The file exports `TooltipProvider`, `Tooltip`, `TooltipTrigger`, `TooltipContent`. That matches the shadcn standard. However it does not re-export the `TooltipPortal` primitive, which is needed when the trigger is inside a `transform`-ed parent (the dashboard `Card` uses Tailwind transforms via `@tremor/react`). Without `TooltipPortal`, content positioning will be wrong inside Tremor cards. Since no caller currently uses `Tooltip` in the diff, this is forward-looking — but the file's incompleteness will surprise the next consumer.

**Fix:** Add `export const TooltipPortal = TooltipPrimitive.Portal;` and use `<TooltipPortal>` in any transformed-parent usage.

### WR-09: `TraceDetail.tsx` polls every 5 s for an unbounded number of refetches when `rag.eval` is in-flight

**File:** `frontend/src/pages/TraceDetail.tsx:41-47`

**Issue:** Looks fine for Phase 4 (the comment says no-op in Phase 4). For Phase 5 forward-compat: if the user keeps the trace detail page open while `rag.eval` never completes (e.g., judge stuck), this triggers an infinite chain of 5-second refetches. There is no max-retry cap. Memory pressure is fine but each refetch hits the API.

**Fix:** Add a retry-count cap or back off:
```ts
const [retries, setRetries] = React.useState(0);
React.useEffect(() => {
  if (!evalPending || !trace_id || retries >= 6) return;  // max ~30s of polling
  const timer = setTimeout(() => {
    queryClient.invalidateQueries({ queryKey: ["trace", trace_id] });
    setRetries(r => r + 1);
  }, 5000);
  return () => clearTimeout(timer);
}, [evalPending, trace_id, queryClient, retries]);
```

### WR-10: `tests/integration/test_pipeline_with_postgres_writer.py:135` relies on a sleep to wait for the consumer flush

**File:** `tests/integration/test_pipeline_with_postgres_writer.py:135`

**Issue:** `await asyncio.sleep(0.4)` is a timing-based barrier that is exactly at the edge of the 250 ms `_FLUSH_INTERVAL`. On a slow CI runner the consumer task may not have flushed before the sleep elapses; on a fast machine it's fine. This produces flaky test failures on CI with no clear signal.

**Fix:** Replace the sleep with an explicit `await consumer.drain()` after cancelling the consumer task — drain guarantees all queued items are flushed deterministically:
```python
consumer_task.cancel()
with contextlib.suppress(asyncio.CancelledError):
    await consumer_task
await consumer.drain()
# now make all pool.recorder assertions
```

### WR-11: `tracer_ai/api/lifespan.py` swallows pipeline construction failures including authentication errors

**File:** `tracer_ai/api/lifespan.py:134-144`

**Issue:** `except Exception as exc: log.warning("pipeline_construction_skipped", error=str(exc))` catches `anthropic.AuthenticationError`, `voyageai.AuthenticationError`, and any other adapter init failure. The api boots with `app.state.pipeline = None` and a NoopTraceWriter. Routes that need the pipeline (chat) presumably check for None and 503, but the operator gets a single warning log line on startup. In production this would mask config errors — `ANTHROPIC_API_KEY=invalid` would result in a healthy-looking server with broken `/chat`. The intent (let tests run without real keys) is right; the implementation doesn't differentiate test from prod.

**Fix:** Log at error level for non-test failures, and surface the detail to the warning's structured fields:
```python
except Exception as exc:
    log.error(
        "pipeline_construction_failed",
        error_type=type(exc).__name__,
        error=str(exc),
        embedder=type(embedder).__name__ if 'embedder' in locals() else None,
    )
    # ... existing fallback
```
Or gate the catch on a known-test env var rather than catching everything.

---

_Reviewed: 2026-05-06_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
