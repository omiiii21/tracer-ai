# Phase 4: Tracer + Trace Explorer - Context

**Gathered:** 2026-05-06
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 4 turns tracer-ai's trace pipeline from "spans go to a Noop writer" into "every chat request lands a complete, queryable trace in Postgres, browsable through `/dashboard`." Phase 3 already emits all four sync spans (`rag.request`, `rag.retrieve`, `rag.prompt_assemble`, `rag.llm_call`) through the `TraceWriter` Protocol — Phase 4 supplies the Postgres adapter, the read API, and the explorer UI.

Deliverables (one bullet per locked requirement; per `.planning/REQUIREMENTS.md` §"Tracer (Phase 4)" + §"Trace Explorer (Phase 4)"):

1. **TRCR-01** — `tracer_ai/tracer/span.py` already carries the OTel + RAG attribute name constants (Phase 2 stub). Phase 4 hardens it with the canonical `Span` Pydantic model (already in `tracer_ai/tracer/writer.py` from Phase 3) and ensures every emit site references constants by name (no literal `"gen_ai.*"` strings at call sites — already enforced by Phase 3 pipeline).
2. **TRCR-02 / TRCR-03** — Verified: spans use `gen_ai.provider.name` (NOT deprecated `gen_ai.system`) and the full `gen_ai.*` + `rag.*` set per `docs/trace-schema.md`. Pre-commit gate (D-2.40) catches drift.
3. **TRCR-04** — Context-propagation helpers (`start_span`, `current_span`, `set_span_in_context`) are deferred to Phase 5 EVAL-04 where the `BackgroundTasks` async eval branch needs them. Phase 4's four sync spans pass `parent_span_id` explicitly via `uuid4()` (the Phase 3 pattern); no `opentelemetry-api` dep is added in Phase 4. (ADR 005 forbids `opentelemetry-sdk`; `-api` would be permitted but is not load-bearing for sync-only Phase 4.)
4. **TRCR-05** — `TraceStore` Protocol (`write_span`, `get_trace`, `list_traces`) materializes in `tracer_ai/tracer/store.py` (Phase 3 stub becomes the read-side Protocol). Distinct from `TraceWriter` (write-only emit Protocol from Phase 3); `TraceStore` is the read-side abstraction the API endpoints depend on.
5. **TRCR-06** — `PostgresTraceWriter` in `tracer_ai/tracer/exporters/postgres.py` (Phase 3 stub becomes the body). Backed by a custom bounded queue (drop-oldest, see D-4.06–4.10) consumed by a background `asyncio.Task` that batches inserts.
6. **TRCR-07** — Lifespan shutdown handler signals consumer to stop, awaits drain with 5s timeout, warn-logs any remaining items.
7. **TRCR-08** — Trace write adds ≤100ms p95 to request path. Verifier: a benchmark plan that runs the pipeline with `NoopTraceWriter` and `PostgresTraceWriter` back-to-back and asserts the p95 delta ≤100ms.
8. **TRCR-09** — `span_payloads` JSONB side table written via the same writer. Spans with payload (retrieved chunks, full assembled prompt messages, full LLM response content) carry `payload: dict[str, Any] | None` on the in-memory `Span`; writer splits row+payload into two INSERTs at persist time.
9. **TRCR-10** — Already true: pipeline emits `rag.request` (root) → `rag.retrieve`, `rag.prompt_assemble`, `rag.llm_call` per Phase 3. Phase 4 verifies these land in Postgres end-to-end.
10. **EXPL-01** — `GET /traces` endpoint with cursor pagination + filters (`query`, `since`, `until`, `feedback`, `min_faithfulness`, `max_latency_ms`). Backed by denormalized columns on `traces` (D-4.02) so filtering is one indexed scan; no JSONB extraction or join-per-request on the hot path.
11. **EXPL-02** — `GET /traces/{trace_id}` returns the full trace tree (`TraceDetailResponse{trace, spans, payloads}` per `docs/api.md`). Server returns ALL payloads in one response (per wireframe: "reads from the already-fetched `TraceDetailResponse.payloads` map (no extra fetch)").
12. **EXPL-03** — `/dashboard` route renders the trace list per `docs/wireframes/dashboard-list.md`: KPI strip + quality drift mini-chart + filter bar + paginated `Table`.
13. **EXPL-04** — `/dashboard/traces/{trace_id}` renders the detail view per `docs/wireframes/dashboard-detail.md`: header KPI card + `Tabs` (Spans / Payloads / Feedback) + span waterfall + JSON viewers.

**Verification gate:**

- A chat request issued in Phase 3's UI now appears in `/dashboard` within seconds; clicking through to detail shows the four-span waterfall with all `attrs` + payloads inspectable.
- `tracer.queue_saturated` log fires under synthetic burst load (1000+ qps producer); the request path latency stays ≤+100ms p95 vs. NoopTraceWriter baseline.
- A migration drill (`alembic upgrade head` on a Phase 2/3 DB) adds the three new denormalized columns (`latency_ms`, `faithfulness`, `feedback_rating`) to `traces` non-destructively.
- `feedback.user` event-style write path: Phase 3's `POST /feedback` endpoint UPDATEs `traces.feedback_rating` so the dashboard sees up/down badges immediately.
- Lifespan shutdown drain log fires correctly: kill the api container while load runs; warn log captures dropped count if any.

**Out of scope this phase (deferred to later phases):**

- `rag.eval` span emission (Phase 5 EVAL-04 — child-of-rag.request via OTel context-snapshot pattern, requiring TRCR-04 helpers — both Phase 5).
- LLM-as-judge worker, faithfulness scoring, calibration set (Phase 5 EVAL-01..06).
- Bad-answer queue UI, FBCK-05 diagnosis-tag UI surface, time-series charts beyond the stub mini-chart on the trace list (Phase 5 FBCK + DASH).
- Eval CLI / regression promotion (Phase 6).
- Demo polish — JSON export, cost widget, scripted demo flow (Phase 7).
- Multi-arch / production hardening / deployment ADR 009 work.

</domain>

<decisions>
## Implementation Decisions

### Trace Persistence Shape (D-4.01..D-4.04)
- **D-4.01:** **`traces` row is INSERTed up-front, before stages run.** Pipeline calls `INSERT INTO traces (id, started_at, query_text, root_span_id) VALUES (...)` synchronously at the top of `_orchestrate` — before `embedder.embed_batch`. Justification: makes `trace_id` referenceable from spans + payloads inserts (FK target exists), `ON DELETE CASCADE` works correctly, and the read API sees an in-flight trace as soon as the request enters the pipeline. The single indexed insert is well under 5ms in practice (no FK constraint at write time on this table). Tradeoff: one synchronous DB write on the request path before async write-path takes over for spans.
- **D-4.02:** **Denormalized scalar columns on `traces`: `latency_ms INT NULL`, `faithfulness REAL NULL`, `feedback_rating SMALLINT NULL`.** Added via a new Alembic revision (NOT `0001_initial.py` — never edit that). The `TraceListItem` Pydantic shape in `docs/api.md` already exposes these fields, so this is contract-aligned, not contract-breaking. Filter queries become one indexed scan (`WHERE faithfulness >= ? AND feedback_rating = ?`) — no JSONB extraction or join-per-request on the hot path.
- **D-4.03:** **Three writers, one row, three single-statement UPDATEs.**
  - **Pipeline** UPDATEs `latency_ms` after `_emit_root` runs (the `t0`-anchored wall clock measurement). Same DB connection; happens in the spans-flush batch path (consumer marks the root span and triggers an UPDATE on traces with the same `trace_id`).
  - **Phase 3's `POST /feedback`** endpoint UPDATEs `feedback_rating` on the same DB transaction that INSERTs the feedback row. Single INSERT + single UPDATE, atomic.
  - **Phase 5's eval worker** (deferred) UPDATEs `faithfulness` after the judge returns. Phase 4 only reserves the column; no Phase 4 code writes to it.
- **D-4.04:** Rejected: materialized view `traces_indexed`, on-the-fly join, Postgres triggers. View was rejected because dashboard latency tolerance is "see your trace right now" and view refresh lags reality. On-the-fly join was rejected because partitioned `spans` + JSONB extraction multiplies cost at scale. Triggers were rejected because cross-cutting DB-side logic is opaque to test suites and couples app evolution to DDL.

### Async Write Path Durability (D-4.05..D-4.10)
- **D-4.05:** **Drop-oldest under saturation.** Newer telemetry is more representative of current system state; allowing the request path to slow down for tracing violates the "observability of the observability never fails user requests" constraint from PROJECT.md.
- **D-4.06:** **Custom bounded queue wrapping `collections.deque` with `asyncio.Lock`.** Lives in `tracer_ai/tracer/exporters/queue.py` (~30 LOC). API:
  ```python
  class BoundedDropOldestQueue:
      def __init__(self, maxsize: int) -> None: ...
      async def put(self, item: Span) -> bool: ...   # returns True if queued, False if dropped-to-make-room
      async def get(self) -> Span: ...               # awaits item availability
      def qsize(self) -> int: ...
  ```
  Predictable, testable, single-process. `asyncio.Queue` was rejected — its `put_nowait`+except+`get_nowait` retry pattern has a race window between the get and the put under concurrent producers, and ordering invariants get murky.
- **D-4.07:** **`maxsize=1000` per `.planning/REQUIREMENTS.md` TRCR-06.** The queue holds Span pydantic instances (small; ~1KB each); 1000 items ≈ 1MB worst-case in memory.
- **D-4.08:** **Saturation log: rate-limited counter, structured log every 1s while saturated.** Track dropped count in the queue object; when `dropped > 0` and `now - last_log_at >= 1s`, emit `tracer.queue_saturated dropped=N window=1s queue_depth=K` via `structlog.get_logger()`, reset counter, update `last_log_at`. Per-event logging was rejected as it would swamp structured-log streams during burst.
- **D-4.09:** **Batch flush: first-of (50 spans OR 250ms since first item in current batch).** Consumer task accumulates pulled items into a batch; flushes when `len(batch) >= 50` or `time.monotonic() - batch_started_at >= 0.250`. Flush issues a single `executemany` (asyncpg `pool.acquire().executemany(...)`) against the `spans` table — Postgres routes inserts to the correct monthly partition automatically. Tail latency bounded ~250ms regardless of arrival rate.
- **D-4.10:** **Lifespan shutdown drain: 5s timeout, then warn-log + exit.** Lifespan finally block:
  1. Set `consumer.stop_accepting = True` (rejects new producers; pipeline emits become a noop with a single warn log).
  2. `await asyncio.wait_for(consumer.drain(), timeout=5.0)`.
  3. On `TimeoutError`: log `tracer.shutdown_drain_incomplete remaining=N` (where N = `queue.qsize()`) and proceed.
  4. Close pool.
  Bounded shutdown — orchestrators send SIGKILL after ~30s anyway; 5s leaves headroom for normal traffic to drain without holding the container.

### Payload Capture Mechanism (D-4.11..D-4.14)
- **D-4.11:** **`Span.payload: dict[str, Any] | None = None`** added to `tracer_ai/tracer/writer.py` `Span` Pydantic model. JSONB-shaped — pipeline emits known keys per span name (documented in `docs/trace-schema.md`):
  - `rag.retrieve`: `{"retrieved_chunks": [{"chunk_id": "...", "content": "...", "score": ..., "doc_id": "...", "doc_section": "..."}]}`
  - `rag.prompt_assemble`: `{"messages": [{"role": "...", "content": "..."}], "prompt_template_id": "..."}`
  - `rag.llm_call`: `{"request": {...}, "response": {"content": [...], "usage": {...}}}`
  - `rag.eval` (Phase 5): `{"judge_prompt": "...", "judge_response": "...", "rationale": "..."}`
  - `rag.request` (root): None — root carries no heavy payload per `docs/trace-schema.md` "Payload table: none."
  Reader doesn't need static typing; the `<pre>`-block JSON viewer in the trace detail UI renders raw. Discriminated union of typed Pydantic models was rejected: doesn't add real safety since the JSONB layer is dynamic, doubles the code per new span type.
- **D-4.12:** **Always emit payload if span has any payload data** (no size threshold). The whole reason `span_payloads` exists is the 4–16KB OTel attribute limit + GIN-index-bloat prevention (`docs/trace-schema.md` §"Payload Storage Convention"). Conditional emit was rejected — two code paths for one concept = bug class.
- **D-4.13:** **Pipeline pre-allocates `payload_id = uuid4()` at emit site; collapse `payload_id` to be `span_id`.** Per `docs/data-model.md` `span_payloads.span_id PRIMARY KEY` — there is no separate `payload_id` column in the locked DDL. The `Span.payload_id` field currently in `tracer_ai/tracer/writer.py` (Phase 3 stub artifact) is removed; pipeline emits `Span(..., payload={...})` and writer's persist path INSERTs `span_payloads (span_id=span.span_id, payload=span.payload::jsonb)` when `payload is not None`.
- **D-4.14:** **`TraceWriter.emit(span)` Protocol unchanged.** Single-method contract; writer adapter splits row+payload internally. `NoopTraceWriter`, `StdoutTraceWriter`, `PostgresTraceWriter` all satisfy the same Protocol. Two-phase API (`emit(span)` + `emit_payload(span_id, payload)`) was rejected — couples pipeline to writer return values, complicates the failure semantics across stages.

### Trace Explorer UX Scaffolding (D-4.15..D-4.18) — Claude's Discretion
The user explicitly skipped UX scaffolding in discuss-phase as reversible. Defaults below, planner may revise:

- **D-4.15:** **Span waterfall = hand-rolled scaled-`div` component.** Tremor `BarList` was considered but its primitives are bar-chart-shaped, not waterfall-shaped (no parent-line indicators). Build a `<SpanWaterfall>` component in `frontend/src/components/SpanWaterfall.tsx` that takes `spans: Span[]` + `root_duration_ms: number` and renders one row per span with: `parent_line` (solid `├─` or dashed `└╌╌` for async per wireframe), `bar` (absolute-positioned div with `left: (started_at-root_started_at)/root_duration * 100%, width: duration/root_duration * 100%`), `label`, `duration_ms`. Min-width 4px on the bar so very-fast spans (<10ms in a 3000ms request) stay visible.
- **D-4.16:** **`rag.eval` row in the waterfall: hidden when no `rag.eval` span exists in the response** (Phase 4: always hidden because Phase 4 doesn't emit it). Phase 5 fills in the row. UI is forward-compatible: `spans.find(s => s.name === "rag.eval")` returns `undefined` in Phase 4 → no row rendered. Wireframe's "Eval pending" state (striped bar) is reserved for Phase 5 when the eval span exists with `ended_at == null`.
- **D-4.17:** **Route migration:** Replace Phase 3's `frontend/src/pages/TraceStub.tsx` (mounted at `/traces/:trace_id`) with two new pages:
  - `frontend/src/pages/Dashboard.tsx` mounted at `/dashboard`
  - `frontend/src/pages/TraceDetail.tsx` mounted at `/dashboard/traces/:trace_id`
  - Update `frontend/src/components/MessageBubble.tsx` "View trace" link to point at `/dashboard/traces/${trace_id}`.
  - Delete `frontend/src/pages/TraceStub.tsx` and remove its route from `frontend/src/router.tsx`.
  - Add `Dashboard` to the `AppShell` nav (per wireframe: `[Chat] [Dashboard] [Admin]`).
- **D-4.18:** **TanStack Query for fetching.** `useQuery({queryKey: ["traces", filters], queryFn: () => ky.get("/traces", {searchParams: filters}).json()})` for the list; `useQuery({queryKey: ["trace", trace_id], ...})` for detail. No polling on the list (stale-while-revalidate via TanStack default `staleTime: 0`). Detail page polls `GET /traces/{trace_id}` once after 5s when `rag.eval.ended_at == null` per wireframe — implemented as a one-shot `setTimeout` in a `useEffect`, not a recurring `refetchInterval`, to avoid Phase 4 over-engineering for a Phase 5 surface.

### Read-Side Endpoint Implementation (D-4.19..D-4.22)
- **D-4.19:** **`GET /traces` cursor encoding: keyset on `(started_at, id)`.** Cursor is base64-encoded JSON `{"started_at": "ISO8601", "id": "uuid"}`. Sort order: `ORDER BY started_at DESC, id DESC`. Resume: `WHERE (started_at, id) < (cursor.started_at, cursor.id)`. Performance scales independent of page depth; rejected: offset-based (slow at depth on partitioned tables).
- **D-4.20:** **Filters compose into a single SQL query against `traces`** (denormalized columns make this single-table). `query` filter uses `traces.query_text ILIKE '%' || $1 || '%'` — accepts the sequential scan cost in Phase 4 (single-user portfolio scope); future full-text index (`tsvector` GENERATED column + GIN) is a Phase 7 polish item if perf becomes load-bearing.
- **D-4.21:** **`GET /traces/{trace_id}` does two queries** (one trace + one spans-with-LEFT-JOIN-payloads). Returns `TraceDetailResponse` per `docs/api.md`. Spans server-side ordered by `started_at` ASC; client trusts order (waterfall renders top-down).
- **D-4.22:** **No streaming on read endpoints.** `GET /traces/{trace_id}` returns a single JSON body even with full payloads (~50-200KB worst-case). HTTP/1.1 chunked transfer is automatic if `httpx`/`uvicorn` decides to use it; no SSE, no pagination of spans within a trace.

### Plan-Time Decisions Reserved for the Planner (D-4.23..D-4.25)
- **D-4.23:** **Number and order of plans.** Recommend ~6 plans:
  1. Alembic revision adding `latency_ms`/`faithfulness`/`feedback_rating` to `traces`; up-front `INSERT INTO traces` in pipeline; remove `Span.payload_id`; add `Span.payload`.
  2. `BoundedDropOldestQueue` + saturation logging (unit-tested standalone).
  3. `PostgresTraceWriter` + consumer task + batch flush + `executemany`; lifespan integration (swap NoopTraceWriter → PostgresTraceWriter); shutdown drain.
  4. `GET /traces` + `GET /traces/{trace_id}` endpoints; `TraceStore` Protocol + Postgres impl in `tracer_ai/tracer/store.py`; cursor pagination.
  5. Frontend `Dashboard.tsx` (list view + KPI strip + filter bar + Table) + `SpanWaterfall.tsx` + `TraceDetail.tsx` (Tabs / waterfall / payload viewer / feedback).
  6. Phase 4 verification gate: synthetic-load p95 benchmark for TRCR-08 + end-to-end fresh-checkout drill (chat request → trace appears → detail renders).
  Planner may merge/split. Hard sequence: 1 → (2,3) → 4 → 5 → 6. Plans 2 and 3 can run sequentially or merged.
- **D-4.24:** **Wave parallelization.** Plan 4 (read API) and Plan 5 (frontend) can run in parallel after Plan 3, IF the OpenAPI contract from `docs/api.md` is treated as the integration boundary. Frontend can mock against fixture JSON during development.
- **D-4.25:** **Verification ordering inside each plan.** Each plan ends with a `<verify>` block exercising only what that plan changed (e.g., Plan 1 greps the new migration file for the three columns + asserts `alembic upgrade head` → `alembic downgrade -1` is reversible). Phase-end verifier (Plan 6) runs the synthetic-load p95 benchmark + the fresh-checkout drill against ROADMAP.md success criteria 1, 2, 3, 4.

### Claude's Discretion (open items planner may revise)
- D-4.15 (waterfall implementation — hand-rolled vs. a chart library; reversible)
- D-4.18 (TanStack Query vs. raw `ky` + state — reversible; only impacts cache/refetch ergonomics)
- D-4.19 (cursor format — keyset vs. offset; reversible at the protocol level since cursor is opaque)
- D-4.20 (`query` filter using ILIKE — could be upgraded to `tsvector` if Phase 7 perf testing flags it)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents (researcher, planner, executor) MUST read these before planning or implementing.**

### Foundation & Vision
- `tracer-ai-foundation-prd.md` — locked foundation PRD; canonical "why" + "what"
- `.planning/PROJECT.md` — project guardrails, locked tech stack, Out of Scope list
- `.planning/REQUIREMENTS.md` §"Tracer (Phase 4)" + §"Trace Explorer (Phase 4)" — TRCR-01..10 + EXPL-01..04 requirement bodies
- `.planning/ROADMAP.md` §"Phase 4: Tracer + Trace Explorer" — phase goal, depends_on, success criteria

### Phase 1 Outputs (Phase 4 implements against these contracts — every Phase 4 decision cites at least one)
- `docs/architecture.md` — system overview; tracer module placement
- `docs/module-deps.md` — `tracer/` is a foundation module; `api/` consumes the read-side `TraceStore` Protocol from `tracer/store.py`
- `docs/data-model.md` — Postgres DDL; partitioned `spans` table; `span_payloads` side table convention; **D-4.02 adds three new columns to `traces` via a new Alembic revision** (the schema in this file is the post-Phase-2 baseline; Phase 4 extends it)
- `docs/trace-schema.md` — every span name, attribute, type, OTel-conformance status, payload examples; **the constants block is already implemented in `tracer_ai/tracer/span.py`** (Phase 2 stub)
- `docs/api.md` — `GET /traces`, `GET /traces/{trace_id}` Pydantic v2 strict-mode schemas (sections 4 + 5); error envelope; cursor pagination contract
- `docs/sequence-diagrams.md` — request lifecycle; the OTel context-snapshot pattern is documented but only Phase 5 needs it (Phase 4 stays synchronous)
- `docs/wireframes/dashboard-list.md` — `/dashboard` route component inventory + endpoint binding (`GET /traces`)
- `docs/wireframes/dashboard-detail.md` — `/dashboard/traces/{trace_id}` component inventory + endpoint binding (`GET /traces/{trace_id}`, `POST /feedback`)
- `docs/wireframes/README.md` — wireframe index + click-through map

### ADRs (Phase 4 MUST cite at least one per decision)
- `docs/decisions/004-trace-storage.md` — Postgres + JSONB; `spans` partitioned by `started_at` monthly; `span_payloads` JSONB side table
- `docs/decisions/005-observability-strategy.md` — custom tracer using OTel GenAI attribute names as Python constants; **NO `opentelemetry-sdk` runtime dep** (Phase 4 stays compliant); `gen_ai.provider.name` not deprecated `gen_ai.system`
- `docs/decisions/001-charting-library.md` — Tremor v3 (Phase 4 dashboard mini-chart uses Tremor `AreaChart`)
- `docs/decisions/010-scope-trim.md` — DASH-04 / FBCK-05 are first cuts on >25% slip; Phase 4 reserves the schema columns but no UI surfaces them

### Phase 1 + 2 + 3 Discuss Artifacts (precedent)
- `.planning/phases/01-research-design-artifacts/01-CONTEXT.md` — D-19..D-30 trace schema + wireframe contracts
- `.planning/phases/02-skeleton-infrastructure/02-CONTEXT.md` — D-2.05 (`uv`), D-2.15 (`migrate` service), D-2.17 (verbatim DDL initial revision), D-2.36..D-2.40 (anti-pattern enforcement)
- Phase 3 has no CONTEXT.md (Phase 3 was planned without discuss; the Phase 3 plans + summaries under `.planning/phases/03-rag-pipeline-chat-ui-corpus-admin/` are the authoritative record)
- `.planning/phases/03-rag-pipeline-chat-ui-corpus-admin/03-RESEARCH.md` — Phase 3 research (RAG pipeline mechanics, payload-side-table rationale section reusable here)
- `.planning/phases/03-rag-pipeline-chat-ui-corpus-admin/03-PATTERNS.md` — Phase 3 patterns (Backend Subsystem 5 pattern: `TraceWriter` Protocol shape — Phase 4 extends with `PostgresTraceWriter`)
- `.planning/phases/03-rag-pipeline-chat-ui-corpus-admin/03-VERIFICATION.md` — Phase 3 verification (carries the live-key SC gaps; Phase 4 doesn't depend on those)

### Existing Source-of-Truth Code (Phase 4 modifies / extends)
- `tracer_ai/tracer/span.py` — attribute name constants (Phase 2 stub) — Phase 4 keeps as-is
- `tracer_ai/tracer/writer.py` — `Span` model + `TraceWriter` Protocol + `NoopTraceWriter`/`StdoutTraceWriter` (Phase 3) — Phase 4 ADDS `payload` field, REMOVES `payload_id` field, ADDS `PostgresTraceWriter`
- `tracer_ai/tracer/store.py` — currently 5 LOC stub — Phase 4 fills with `TraceStore` Protocol + Postgres impl
- `tracer_ai/tracer/exporters/postgres.py` — currently 5 LOC stub — Phase 4 fills with `PostgresTraceWriter` body
- `tracer_ai/tracer/exporters/queue.py` — NEW; `BoundedDropOldestQueue`
- `tracer_ai/rag/pipeline.py` — Phase 3 emits 4 spans correctly; Phase 4 ADDS up-front `INSERT INTO traces` and ADDS `payload=` to each `Span(...)` construction; UPDATES `latency_ms` on `traces` after `_emit_root`
- `tracer_ai/api/lifespan.py` — Phase 3 wires `NoopTraceWriter()`; Phase 4 swaps to `PostgresTraceWriter(pool)` + starts/stops the consumer task
- `tracer_ai/api/feedback.py` — Phase 3 endpoint; Phase 4 adds the `UPDATE traces SET feedback_rating = ?` step in the same transaction
- `tracer_ai/api/main.py` — Phase 4 ADDS `app.include_router(traces.router)` (new traces.py module for `GET /traces` + `GET /traces/{trace_id}`)
- `frontend/src/router.tsx` — Phase 4 ADDS `/dashboard` + `/dashboard/traces/:trace_id` routes; REMOVES `/traces/:trace_id` stub
- `frontend/src/components/MessageBubble.tsx` — update "View trace" link target
- `frontend/src/components/AppShell.tsx` — add `Dashboard` nav link
- `frontend/src/pages/TraceStub.tsx` — DELETE (replaced by `Dashboard.tsx` + `TraceDetail.tsx`)
- `alembic/versions/0001_initial.py` — DO NOT EDIT (per D-2.17); Phase 4 adds a new revision

### Research (already done; ADRs codified — refer when ADR is silent)
- `.planning/research/STACK.md` — Tremor v3 + shadcn Tabs/Table/Card/Badge/Slider/Input/Select component inventory
- `.planning/research/ARCHITECTURE.md` §"Anti-Patterns" — Anti-Pattern #2 (heavy payloads on span rows) is mitigated by Phase 4 D-4.11
- `.planning/research/PITFALLS.md` — Pitfalls relevant to Phase 4: write amplification under burst (Pitfall #2 partition-related), saturation handling (Pitfall #5)
- `.planning/research/SUMMARY.md` — executive summary

### State / Memory
- `.planning/STATE.md` §"Decisions" — Phase 1 + 2 + 3 cumulative decisions; the rag.eval contract (Phase 5 EVAL-04) is locked even though Phase 4 doesn't implement it; Phase 4's `payload` shape conventions inherit from Phase 1's `docs/trace-schema.md` examples
- `.planning/STATE.md` §"Blockers/Concerns" — Voyage pricing (still pending; not Phase 4-blocking); Tailwind v3 pin (still critical for Tremor + shadcn)

### External (cited; do not re-fetch)
- asyncpg `executemany` semantics — used for batch INSERT in Plan 3
- pgvector + Postgres partitioned table behavior — INSERT auto-routes to monthly partition
- TanStack Query 5.x `useQuery` keyset patterns
- Tremor v3 `KpiCard` + `AreaChart` component APIs (already cited in `.planning/research/STACK.md`)
- Recharts (Tremor's underlying lib) — fallback only if Tremor's primitives don't cover a chart need
- shadcn/ui `Tabs` + `Table` + `Slider` + `Tooltip` + `Badge` + `Alert` component APIs

### Outputs (created during Phase 4; become canonical for later phases)
- `alembic/versions/000N_traces_denorm.py` — new migration adding `latency_ms`/`faithfulness`/`feedback_rating` to `traces`
- `tracer_ai/tracer/exporters/queue.py` — `BoundedDropOldestQueue` (Phase 5 eval worker may also use this if it queues judge invocations)
- `tracer_ai/tracer/exporters/postgres.py` — `PostgresTraceWriter` (Phase 5 EVAL-04 emits `rag.eval` through the same writer)
- `tracer_ai/tracer/store.py` — `TraceStore` Protocol + `PostgresTraceStore` (Phase 5 + 6 query through this for bad-answer-queue + eval CLI)
- `tracer_ai/api/traces.py` — NEW route module
- `frontend/src/pages/Dashboard.tsx` + `TraceDetail.tsx` + `frontend/src/components/SpanWaterfall.tsx` — reusable across Phase 5 (bad-answer queue is a filtered view of `Dashboard`)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`tracer_ai/tracer/writer.py` `Span` model + `TraceWriter` Protocol + Noop/Stdout adapters** (Phase 3) — Phase 4 adds `PostgresTraceWriter` against the same Protocol; one-line lifespan swap upgrades dev (Stdout) to production (Postgres) — exactly the design intent stated in the writer.py docstring (`Phase 4 TRCR-06 adds PostgresTraceWriter against the same Protocol`).
- **`tracer_ai/rag/pipeline.py` 4-span emission** (Phase 3 Plan 06) — fully complete with try/finally cancellation safety, span constants imported by name, root-span-always-emitted invariant. Phase 4 only adds (a) `INSERT INTO traces` at the top, (b) `payload=` arg to each `Span(...)` constructor, (c) `UPDATE traces SET latency_ms=?` after `_emit_root`.
- **`tracer_ai/api/lifespan.py` lifespan handler** (Phase 3) — already creates the asyncpg pool, runs CORP-04 startup assertion, constructs the Pipeline. Phase 4 adds: swap `NoopTraceWriter()` → `PostgresTraceWriter(pool)`, start consumer task, register the consumer-stop + drain in the finally block.
- **`tracer_ai/api/feedback.py`** (Phase 3) — accepts feedback writes; Phase 4 adds the `UPDATE traces SET feedback_rating = ?` step in the same transaction.
- **`tracer_ai/api/schemas.py`** (Phase 3) — `TraceListItem` / `TraceListResponse` / `TraceDetailResponse` are already defined per `docs/api.md` (Phase 3 RAG-05 wave landed `ChatResponse` and the chat-related schemas; the trace-list/detail schemas may need to be added — Phase 4 plan 4 creates them if absent).
- **`frontend/src/components/AppShell.tsx`** (Phase 3) — already has `[Chat] [Admin]` nav; Phase 4 adds `[Dashboard]`.
- **`frontend/src/components/MessageBubble.tsx`** (Phase 3) — already renders the "View trace" link to `/traces/:trace_id`; Phase 4 changes the target to `/dashboard/traces/:trace_id`.
- **shadcn `Tabs`, `Table`, `Card`, `Badge`, `Slider`, `Input`, `Select`, `Alert`, `Tooltip`** — Phase 3 brought in Card/Button; Phase 4 needs to add Tabs/Table/Slider/Tooltip via `npx shadcn add`. Tremor `KpiCard` + `AreaChart` already in `package.json` per Phase 2 D-2.30.
- **TanStack Query** — already in `package.json` per Phase 2 D-2.30; Phase 3 may or may not have wired the QueryClientProvider — Phase 4 plan 5 verifies and wires it.

### Established Patterns
- **Protocol-first adapter design (ADR 005, D-2.38)** — Phase 4 `PostgresTraceWriter` is the second concrete implementation of `TraceWriter`; `PostgresTraceStore` is the only concrete implementation of `TraceStore` for now.
- **Pre-commit anti-pattern enforcement (D-2.36..D-2.40)** — `from anthropic` only in `rag/llm.py` + `eval/llm_judge.py`; no `:latest` tags; no `gen_ai.system` outside the explicitly-commented DEPRECATED line; no `class Config:` v1 blocks; no `print(...)` outside `cli/__main__.py`. Phase 4 code respects these from day one.
- **Pydantic v2 `extra="forbid"` on every API schema** (D-26 / D-2.39) — all new schemas in `tracer_ai/api/traces.py` follow.
- **Module-deps DAG (D-2.27)** — `tracer/` is a foundation; `api/` may import `tracer/`. `tracer/` MUST NOT import `api/`. Phase 4 verifier re-runs the import-cycle guard.
- **Embedding-metadata triple-column pattern (D-49 / ADR 003)** — irrelevant to Phase 4 (not adding a vector table); Phase 4's denorm columns are unrelated.
- **Async-context cancellation safety (Phase 3 Pipeline)** — try/finally per stage. Phase 4's consumer task uses the same discipline: shutdown signal handled, drain bounded, no pending awaitables on the floor.

### Integration Points
- **`tracer_ai.config.Settings`** — already imported by lifespan + alembic env.py + every adapter. Phase 4 adds no new env vars (the `BoundedDropOldestQueue.maxsize=1000` is a code-level constant per TRCR-06).
- **asyncpg pool from `tracer_ai/api/lifespan.py`** — shared between read-side TraceStore queries and the PostgresTraceWriter consumer task. The pool sizing (min=1, max=10) is fine for Phase 4 single-user load; revisit in Phase 7 polish.
- **`tracer_ai/rag/pipeline.py` emit sites** — Phase 4 modifies the `Span(...)` constructions in `_orchestrate` to pass `payload=`; existing attrs / span name / parent-id wiring is unchanged.
- **`alembic/versions/`** — never edit `0001_initial.py` (D-2.17). Phase 4 adds `000N_traces_denorm.py` (Plan 1). Future Phase 5 may add another for any rag.eval-driven schema.
- **`docs/api.md`** — already documents the read endpoints; Phase 4 plan 4 ships them. Schema in `docs/api.md` IS the contract; `tracer_ai/api/schemas.py` IS source-of-truth at runtime — they must agree (D-26).

</code_context>

<specifics>
## Specific Ideas

- **Drop-oldest preferred over drop-newest** — newer telemetry is more representative of current system state. The user articulated this directly during discussion; preserved as D-4.05.
- **One synchronous `INSERT INTO traces` is acceptable on the request path** — even though it adds a small write, it makes everything downstream simpler (FK targets exist, read API sees in-flight traces immediately). Tradeoff explicitly considered in D-4.01.
- **`Span.payload` as a single optional field is the right level of abstraction** — single emit call, no two-phase API; writer adapter splits row+payload internally. Confirmed during discussion.
- **Memory note honored:** "Design artifacts before any coding" — Phase 1 + 2 + 3 produced all relevant design artifacts (`docs/data-model.md`, `docs/api.md`, `docs/trace-schema.md`, `docs/wireframes/dashboard-*`). Phase 4 is implementation against locked specs; only the three implementation gray areas (persistence shape, durability, payload mechanism) required user judgment beyond what design captured.
- **Memory note honored:** "List alternatives in PRDs for downstream-agent research" — every D-4.* decision either references an ADR with alternatives or names the rejected alternative inline (e.g., D-4.04 names materialized view + on-the-fly join + triggers; D-4.06 names asyncio.Queue retry pattern; D-4.11 names discriminated-union typed payloads).
- **Phase 4 ships only sync spans; rag.eval is Phase 5** — the wireframe shows 5 rows, but waterfall code is forward-compatible (`spans.find(s => s.name === "rag.eval")` returns undefined in Phase 4 → no row rendered). No Phase 4 plan emits or persists rag.eval. Documented in D-4.16.
- **TRCR-04 (`opentelemetry-api` context wrapper) is deferred to Phase 5** — Phase 4 doesn't need cross-task context propagation; sync 4-span emission passes parent_span_id explicitly. Phase 5 EVAL-04 will need it for the BackgroundTasks async dispatch (per `docs/sequence-diagrams.md` "Snapshot otel_context.get_current() BEFORE root.end()" Note callout). Documented in deliverable 3.

</specifics>

<deferred>
## Deferred Ideas

- **rag.eval span emission, LLM-as-judge worker, faithfulness scoring** — Phase 5 EVAL-01..06.
- **TRCR-04 (`start_span`, `current_span`, `set_span_in_context` helpers wrapping `opentelemetry-api`)** — Phase 5 needs them for the async eval dispatch. Phase 4 stays free of any `opentelemetry-*` runtime dep (ADR 005 compliance preserved).
- **Bad-answer queue UI (filtered view of `Dashboard`)** — Phase 5 FBCK-03 reuses Phase 4's `Dashboard` + `TraceListItem` shape with extra filter wiring.
- **FBCK-05 diagnosis-tag UI** — column reserved on `feedback` table; UI surface deferred. Wireframe shows the surface; Phase 5 wires it.
- **Time-series charts (DASH-01..05)** — Phase 5; Phase 4 ships only the mini-chart on the trace list (a single `AreaChart` for `faithfulness` + `relevance` over the windowed query, which is empty in Phase 4 because no rag.eval data exists yet — render with placeholder or omit chart in Phase 4).
- **Cost widget on dashboard (DEMO-03)** — Phase 7 polish; data is available (`estimated_cost_usd` per trace) but no aggregator endpoint.
- **Eval CLI / regression promotion** — Phase 6.
- **JSON export of trace from detail view (DEMO-04)** — Phase 7 polish; data is fully available via `GET /traces/{trace_id}` already.
- **Full-text search on `traces.query_text`** — Phase 4 uses ILIKE; Phase 7 polish if perf flags it.
- **Polling cadence beyond a single 5s retry on eval-pending** — Phase 5 may revisit when rag.eval becomes a real surface.
- **Routing convention if Phase 5 wants `/dashboard/queue` (bad-answer queue)** — Phase 4 mounts `/dashboard` (list) and `/dashboard/traces/:trace_id` (detail); Phase 5 will add a sibling.

</deferred>

---

*Phase: 4-Tracer + Trace Explorer*
*Context gathered: 2026-05-06*
