# Phase 4: Tracer + Trace Explorer - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in `04-CONTEXT.md` — this log preserves the alternatives considered.

**Date:** 2026-05-06
**Phase:** 4-tracer-trace-explorer
**Areas discussed:** Trace persistence shape, Async write path durability, Payload capture mechanism

---

## Initial Gray-Area Selection

| Option | Description | Selected |
|--------|-------------|----------|
| Trace persistence shape | When does the `traces` row get inserted; do we denormalize `latency_ms`/`faithfulness`/`feedback_rating` onto traces for fast list filtering vs joining spans+feedback every request? | ✓ |
| Async write path durability | Queue overflow policy and consumer batching strategy under burst load. | ✓ |
| Payload capture mechanism | Pipeline currently has no path to emit full prompts/responses/chunks into `span_payloads`. Span-model shape decision. | ✓ |
| Trace explorer UX scaffolding | Span waterfall implementation, eval-pending state, route migration from Phase 3 stub. | (skipped — user judged reversible) |

**User's framing:** "skip in discuss-phase. Three implementation choices that are all reversible in a few hours of code. Tremor BarList will work fine for the waterfall as a starter; eval-pending row is a CSS/skeleton concern; route migration is a 10-line change. Don't burn a discuss round on it."

The skipped UX area was assigned default decisions in CONTEXT.md §"Trace Explorer UX Scaffolding (D-4.15..D-4.18) — Claude's Discretion."

---

## Trace Persistence Shape

**User's lean (provided up-front, before sub-questions):** "denormalize latency_ms, faithfulness, feedback_rating onto the traces row at write time. List-view filters become one indexed scan. The cost is a targeted UPDATE when async eval/feedback land — cheap, well worth it for the dashboard's responsiveness."

### Sub-decision: When does the `traces` row get INSERTed?

| Option | Description | Selected |
|--------|-------------|----------|
| Up-front, before stages run | Pipeline INSERTs `traces(id, started_at, query_text, root_span_id)` synchronously before `embedder.embed_batch`. trace_id is referenceable from spans+payloads inserts; ON DELETE CASCADE works; small synchronous DB write (<5ms). | ✓ |
| Async via the queue alongside spans | Pipeline pushes a `TraceCreate` envelope onto the same queue; consumer INSERTs in batch. Zero sync DB I/O on request, but spans queued before consumer drains the trace row will fail FK. | |
| Lazily on first span flush | Consumer detects unknown trace_id, INSERTs traces row before its first span. Minimal pipeline change but flow control complexity in consumer. | |

### Sub-decision: How are the denormalized columns added?

| Option | Description | Selected |
|--------|-------------|----------|
| Alembic migration adds nullable columns to `traces` | New revision: `latency_ms INT NULL`, `faithfulness REAL NULL`, `feedback_rating SMALLINT NULL`. The `TraceListItem` Pydantic shape in `docs/api.md` already exposes these fields, so no schema drift. Direct indexed scan for filters. | ✓ |
| Materialized view `traces_indexed` joining spans+feedback | Refreshed on cron or trigger. Source spans+feedback stay normalized but refresh latency lags reality. | |
| Compute on-the-fly with joins per query | Every `GET /traces` does `LEFT JOIN spans ... LEFT JOIN feedback`. Zero new schema but multiplies cost at scale on partitioned spans + JSONB extraction. | |

### Sub-decision: Who writes each denormalized column?

| Option | Description | Selected |
|--------|-------------|----------|
| Pipeline / feedback endpoint / Phase 5 worker each own one column | Three distinct triggers, three single-statement UPDATEs. Pipeline UPDATEs `latency_ms` after root span end. POST /feedback UPDATEs `feedback_rating`. Phase 5 EVAL worker UPDATEs `faithfulness`. Clean accountability. | ✓ |
| Single trigger-style updater task that re-derives from spans+feedback | One place to change derivation logic but duplicates work and adds latency. | |
| Postgres triggers (AFTER INSERT on spans/feedback) | DB-side triggers maintain denorm columns; opaque cross-cutting logic; harder to test. | |

**Notes:** User confirmed all recommended choices. Codified as D-4.01..D-4.04 in CONTEXT.md.

---

## Async Write Path Durability

**User's lean (provided up-front):** "drop-oldest with a WARN log (newer telemetry is more representative; never let the request path slow down for tracing). Batch flush on 250ms window OR 50 spans, whichever first."

### Sub-decision: How is drop-oldest implemented?

| Option | Description | Selected |
|--------|-------------|----------|
| Custom bounded queue wrapping `collections.deque` with asyncio.Lock | ~30 LOC class; predictable, testable, single-process. Drop-oldest is one branch; no try/except churn. | ✓ |
| Wrap `asyncio.Queue` with try-put-then-pop-oldest retry | Uses stdlib primitive but introduces a race window between get and put under concurrent producers. | |
| `asyncio.Queue` with drop-newest | Reverses the policy. Simplest possible but contradicts user's drop-oldest preference. | |

### Sub-decision: WARN log granularity

| Option | Description | Selected |
|--------|-------------|----------|
| Rate-limited counter, structured log every 1s while saturated | Track dropped count; emit `tracer.queue_saturated dropped=N window=1s` at most once per second. Visibility without log spam during burst. | ✓ |
| Log every drop event individually | Zero hidden drops but log spam swamps everything else under saturation. | |
| Counter exposed via /healthz, no per-event log | Programmatic observability but invisible in normal log streams. | |

### Sub-decision: Batch flush trigger

| Option | Description | Selected |
|--------|-------------|----------|
| First-of: 50 spans OR 250ms since first item in batch | Bounds tail latency to ~250ms regardless of arrival rate. Single `executemany` per flush against the partitioned `spans` table. | ✓ |
| Fixed 250ms cadence, batch whatever's queued | Deterministic flush rhythm but bursts of >50 spans flush as one giant batch. | |
| Eager (per-item) flush — no batching | Simplest but misses TRCR-06 "batches inserts" requirement. | |

### Sub-decision: Lifespan force-flush on shutdown timeout

| Option | Description | Selected |
|--------|-------------|----------|
| Drain with 5s timeout, then warn-log remaining + exit | Lifespan finally signals consumer to stop; awaits drain with `asyncio.wait_for(timeout=5)`; if timeout, logs `tracer.shutdown_drain_incomplete remaining=N` and proceeds. | ✓ |
| Drain unconditionally, no timeout | Zero loss but a wedged DB hangs container shutdown. | |
| Best-effort: stop accepting, flush whatever's batched, exit | Fast shutdown but items in deque but not yet batched are lost without log signal. | |

**Notes:** User confirmed all recommended choices. Codified as D-4.05..D-4.10 in CONTEXT.md.

---

## Payload Capture Mechanism

**User's lean (provided up-front):** "Span.payload as an optional inline field, writer splits into spans row + span_payloads row at persist time. Single emit call, no two-phase API."

### Sub-decision: Payload field shape on Span

| Option | Description | Selected |
|--------|-------------|----------|
| `payload: dict[str, Any] \| None = None` keyed by convention in trace-schema.md | Typed only as JSONB-shaped dict. Pipeline emits known keys per span name; reader doesn't need static typing. Matches `span_payloads.payload JSONB` directly. Lowest blast radius. | ✓ |
| Discriminated union of typed Pydantic models per span name | `RetrievePayload \| PromptAssemblePayload \| ...`. Schema enforced at type system but every new span-type addition = new model + writer branch + tests. | |
| Bytes/string (raw JSON serialized by pipeline) | Writer treats payload as opaque blob but reader has to parse. Loses Pydantic introspection. | |

### Sub-decision: When does the pipeline emit a payload — always, or only above a size threshold?

| Option | Description | Selected |
|--------|-------------|----------|
| Always emit if the span has any payload data | TRCR-09 mandates the side table for full prompts/responses; the side table exists for that purpose. Conditional emit complicates reader logic. | ✓ |
| Only emit if payload >4KB; else inline into spans.attrs | Tiny payloads avoid an extra row insert but reader needs branch logic; risk of GIN index bloat. | |

### Sub-decision: Who allocates `payload_id`?

| Option | Description | Selected |
|--------|-------------|----------|
| Pipeline pre-allocates `uuid4()` at emit site; collapse `payload_id` to be `span_id` | Per `docs/data-model.md`, `span_payloads.span_id PRIMARY KEY` — there is no separate `payload_id` column in the locked DDL. The `Span.payload_id` field in writer.py becomes redundant. Cleanup task: remove `payload_id` from the Pydantic model. | ✓ |
| Writer assigns payload_id at persist time | Pipeline doesn't manage IDs but couples pipeline to writer return values; current Protocol is `emit(span) -> None`, would need to change. | |
| Drop `payload_id` field entirely; use `span_id` as the side-table FK key | Same effect as the chosen option (note: the chosen option includes the `payload_id` removal). | |

**Notes:** User confirmed all recommended choices. Codified as D-4.11..D-4.14 in CONTEXT.md. Note: `Span.payload_id` (a Phase 3 stub artifact in `tracer_ai/tracer/writer.py`) is removed in Phase 4 Plan 1 because the locked DDL has no separate `payload_id` column.

---

## Wrap-up

**User chose:** "I'm ready for context" — no further gray areas to surface.

The user explicitly considered and skipped these (which I had identified internally but did not present as separate questions):

- TRCR-04 OTel context propagation helpers — assigned to Phase 5 EVAL-04 in CONTEXT.md deliverable 3.
- Cursor pagination encoding — assigned in D-4.19 as keyset on `(started_at, id)`.
- Route migration details — assigned in D-4.17 as the Phase 3 `TraceStub.tsx` deletion + `Dashboard.tsx`/`TraceDetail.tsx` introduction.

---

## Claude's Discretion

User explicitly delegated:

1. **Trace explorer UX scaffolding** (Area 4 — skipped from discussion). Codified as D-4.15..D-4.18:
   - Span waterfall = hand-rolled scaled-`div` component (Tremor `BarList` doesn't fit waterfall semantics)
   - rag.eval row hidden when no rag.eval span exists (forward-compatible for Phase 5)
   - Route migration: replace `TraceStub.tsx` with `Dashboard.tsx` + `TraceDetail.tsx`; update `MessageBubble` link
   - TanStack Query for fetching, no list polling, single 5s retry on eval-pending in detail
2. **Read-side endpoint implementation details** — D-4.19..D-4.22:
   - Cursor format: keyset on `(started_at, id)`, base64-encoded
   - Filter composition: single-table query against denormalized `traces`
   - `query` filter uses ILIKE (Phase 7 polish item if perf flags it)
   - Two-query trace detail (trace + spans-with-LEFT-JOIN-payloads); no streaming
3. **Plan structure** — D-4.23..D-4.25:
   - Recommended ~6 plans; planner may merge/split
   - Parallel waves possible after Plan 3
   - Each plan ends with a scoped `<verify>` block; phase-end verifier runs the full p95 benchmark + fresh-checkout drill

The planner has explicit override authority on D-4.15 (waterfall implementation), D-4.18 (TanStack Query vs raw `ky`), D-4.19 (cursor format), and D-4.20 (ILIKE vs tsvector).

---

## Deferred Ideas

- rag.eval span emission, LLM judge worker, faithfulness scoring (Phase 5 EVAL-01..06)
- TRCR-04 OTel context propagation helpers (Phase 5 EVAL-04)
- Bad-answer queue UI (Phase 5 FBCK-03 — reuses Phase 4's Dashboard + TraceListItem shape)
- FBCK-05 diagnosis-tag UI surface (Phase 5)
- Time-series charts beyond mini-chart (Phase 5 DASH-01..05)
- Cost widget on dashboard (Phase 7 DEMO-03)
- JSON export of trace from detail view (Phase 7 DEMO-04)
- Full-text search on `traces.query_text` (Phase 7 polish — currently ILIKE)
- Recurring polling on eval-pending detail page (Phase 5 — Phase 4 ships only single 5s retry)
- Routing convention for Phase 5's `/dashboard/queue` sibling (Phase 5 add-on)
