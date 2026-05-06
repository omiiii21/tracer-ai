# Phase 4: Tracer + Trace Explorer — Research

**Researched:** 2026-05-06
**Domain:** Async trace persistence (asyncpg batch write path), Postgres keyset pagination on partitioned tables, custom bounded queue, FastAPI lifespan task lifecycle, React waterfall component, TanStack Query 5.x, shadcn/ui Tabs/Table/Slider/Tooltip/Badge, Tremor v3 KpiCard/AreaChart, Alembic incremental revision
**Confidence:** HIGH — all critical decisions pre-locked in CONTEXT.md; research deepens implementation patterns, not alternatives.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Trace Persistence Shape (D-4.01..D-4.04)**
- D-4.01: `traces` row INSERTed up-front synchronously at the top of `_orchestrate` before `embedder.embed_batch`.
- D-4.02: Three denormalized columns added to `traces` via a NEW Alembic revision (never edit `0001_initial.py`): `latency_ms INT NULL`, `faithfulness REAL NULL`, `feedback_rating SMALLINT NULL`.
- D-4.03: Three single-statement UPDATEs: pipeline sets `latency_ms` after `_emit_root`; `POST /feedback` sets `feedback_rating`; Phase 5 eval worker sets `faithfulness`.
- D-4.04: Materialized view, on-the-fly JSONB join, and Postgres triggers all rejected.

**Async Write Path Durability (D-4.05..D-4.10)**
- D-4.05: Drop-oldest under queue saturation (newer telemetry is more representative).
- D-4.06: Custom `BoundedDropOldestQueue` wrapping `collections.deque` + `asyncio.Lock` in `tracer_ai/tracer/exporters/queue.py`. `asyncio.Queue` rejected.
- D-4.07: `maxsize=1000` (code-level constant, not env var).
- D-4.08: Rate-limited saturation log: structured log via `structlog` every 1s while saturated; counter resets per log period.
- D-4.09: Batch flush: first-of (50 spans OR 250ms since first item). Single `executemany` call per flush against `spans` table.
- D-4.10: Lifespan shutdown: 5s drain timeout; warn-log `tracer.shutdown_drain_incomplete remaining=N`; then close pool.

**Payload Capture Mechanism (D-4.11..D-4.14)**
- D-4.11: `Span.payload: dict[str, Any] | None = None` added; `Span.payload_id` removed.
- D-4.12: Always emit payload if non-None (no size threshold).
- D-4.13: `span_payloads.span_id = Span.span_id` (no separate payload_id column).
- D-4.14: `TraceWriter.emit(span)` Protocol unchanged; writer splits row+payload internally.

**Trace Explorer UX (D-4.15..D-4.18) — Claude's Discretion**
- D-4.15: Hand-rolled `<SpanWaterfall>` component (absolute-positioned divs; min-width 4px; parent-line glyphs `├─` / `└╌╌`).
- D-4.16: `rag.eval` row hidden when span absent; forward-compatible.
- D-4.17: Routes `/dashboard` + `/dashboard/traces/:trace_id`; delete `TraceStub.tsx`.
- D-4.18: TanStack Query; one-shot `setTimeout` 5s re-fetch on eval-pending (not `refetchInterval`).

**Read-Side Endpoint Implementation (D-4.19..D-4.22)**
- D-4.19: Cursor: base64 JSON `{"started_at": "ISO8601", "id": "uuid"}`; ORDER BY `(started_at DESC, id DESC)`; resume via `WHERE (started_at, id) < (cursor.started_at, cursor.id)`.
- D-4.20: Filters compose into single SQL on `traces` (denormalized). `query` filter uses `ILIKE`.
- D-4.21: `GET /traces/{trace_id}` does two queries: one trace + one spans-LEFT-JOIN-payloads. Server-side ordered by `started_at ASC`.
- D-4.22: No streaming; single JSON response.

**Plan-Time Decisions (D-4.23..D-4.25)**
- D-4.23: Recommend ~6 plans; hard sequence 1→(2,3)→4→5→6.
- D-4.24: Plans 4+5 can run in parallel after Plan 3 using docs/api.md as integration boundary.
- D-4.25: Each plan ends with a verify block for what that plan changed. Plan 6 runs p95 benchmark + fresh-checkout drill.

### Claude's Discretion
- D-4.15 waterfall implementation (hand-rolled confirmed, but planner may revise specifics)
- D-4.18 TanStack Query vs raw ky + state (reversible)
- D-4.19 cursor format (opaque; reversible)
- D-4.20 ILIKE (may upgrade to tsvector in Phase 7)

### Deferred Ideas (OUT OF SCOPE)
- `rag.eval` span emission — Phase 5 EVAL-04
- TRCR-04 context propagation helpers (`opentelemetry-api`) — Phase 5
- LLM-as-judge worker, faithfulness scoring — Phase 5
- Bad-answer queue UI — Phase 5 FBCK-03
- FBCK-05 diagnosis-tag UI surface — Phase 5
- Time-series charts beyond stub mini-chart — Phase 5
- Eval CLI / regression promotion — Phase 6
- JSON export button, cost widget, demo polish — Phase 7
- Full-text search (`tsvector`) on `traces.query_text` — Phase 7
- Polling beyond one-shot 5s retry on eval-pending — Phase 5
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TRCR-01 | Span dataclass in `tracer/span.py` with OTel-aligned + RAG-specific attributes; all attribute names as constants | Constants block already in `tracer_ai/tracer/span.py` (Phase 2 stub); needs full `docs/trace-schema.md` constant set added; writer.py Span model stays as the dataclass |
| TRCR-02 | Use `gen_ai.provider.name` (NOT deprecated `gen_ai.system`) | Already enforced by pre-commit gate (D-2.40); `span.py` already has correct constants |
| TRCR-03 | Custom `rag.*` attributes for retrieval scores, prompt template, eval metrics | All defined in `tracer_ai/tracer/span.py`; pipeline.py already emits correct subset; Phase 4 adds remaining constants from `docs/trace-schema.md` |
| TRCR-04 | DEFERRED to Phase 5 EVAL-04 | No action in Phase 4 |
| TRCR-05 | `TraceStore` Protocol (`write_span`, `get_trace`, `list_traces`) | `tracer_ai/tracer/store.py` is a 5-LOC stub; Phase 4 fills with Protocol + Postgres impl |
| TRCR-06 | Postgres+JSONB exporter via bounded queue (`maxsize=1000`) + background consumer | Custom `BoundedDropOldestQueue` (D-4.06) + `PostgresTraceWriter`; `executemany` batch flush (D-4.09) |
| TRCR-07 | Lifespan shutdown drains span queue before exit | 5s `asyncio.wait_for` drain; warn-log on timeout (D-4.10) |
| TRCR-08 | Trace write adds ≤100ms p95 to request path | Async queue + batch flush pattern; benchmark in Plan 6 verifier |
| TRCR-09 | Full prompt/response payloads in `span_payloads` JSONB side table | `Span.payload` field (D-4.11); writer splits INSERT spans + INSERT span_payloads |
| TRCR-10 | Every chat request emits `rag.request` → `rag.retrieve`, `rag.prompt_assemble`, `rag.llm_call` | Already emitting in Phase 3 pipeline.py; Phase 4 adds `payload=` to Span constructors + up-front traces INSERT |
| EXPL-01 | `GET /traces` with cursor pagination + filters | Keyset cursor (D-4.19); single-table filter query (D-4.20); `tracer_ai/api/traces.py` new module |
| EXPL-02 | `GET /traces/{trace_id}` full trace tree | Two-query pattern (D-4.21); `TraceDetailResponse` per `docs/api.md` |
| EXPL-03 | `/dashboard` trace list view with KPI strip + filter bar + paginated table | `Dashboard.tsx`; Tremor KpiCard + AreaChart; shadcn Table/Input/Select/Slider/Badge |
| EXPL-04 | Trace detail view with span waterfall + payload inspectors | `TraceDetail.tsx` + `SpanWaterfall.tsx`; shadcn Tabs/Badge; `<pre>` block JSON viewer |
</phase_requirements>

---

## Summary

Phase 4 is pure implementation against a fully-locked spec. Every design decision in the `## Decisions` section of CONTEXT.md is non-negotiable and documented with rationale. The research task is therefore to answer: what does each implementation decision require in terms of exact API calls, code patterns, test surface, and ordering constraints?

The three technical areas that most reward deep research are: (1) the asyncpg `executemany` batch insert semantics, which have a subtle interaction with the monthly-partitioned `spans` table; (2) the `BoundedDropOldestQueue` `asyncio.Lock` + `asyncio.Event` coordination under concurrent producers; and (3) the hand-rolled `SpanWaterfall` CSS positioning math and the shadcn Tabs + TanStack Query wiring for the detail page.

The ADRs, wireframes, and `docs/api.md` form a hermetically sealed design space. The planner should produce one plan per D-4.23 recommendation (6 plans), with hard sequencing 1→(2,3 merged or sequential)→4→5→6. Plans 4 (read API) and 5 (frontend) can be written in parallel because `docs/api.md` is the stable integration boundary.

**Primary recommendation:** Implement in strict plan order. The Alembic migration (Plan 1) is the keystone — every subsequent plan depends on the three new `traces` columns and the `Span.payload` field existing. The `BoundedDropOldestQueue` is best implemented as a standalone unit (Plan 2) tested in isolation before the `PostgresTraceWriter` (Plan 3) wraps it.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Up-front traces INSERT | API / Backend (`rag/pipeline.py`) | — | Sync write on request path; must happen before spans FK is needed |
| Span emit (4 spans) | API / Backend (`rag/pipeline.py`) | — | Sync emit to `TraceWriter` Protocol; already Phase 3 |
| Span persistence (async) | API / Backend (`tracer/exporters/postgres.py` consumer task) | — | Consumer task owned by lifespan; writes batch to Postgres |
| Payload split (spans vs span_payloads) | API / Backend (`PostgresTraceWriter`) | — | Writer layer; pipeline just passes `payload=` to Span |
| `feedback_rating` UPDATE | API / Backend (`api/feedback.py`) | — | Same DB transaction as feedback INSERT |
| `latency_ms` UPDATE | API / Backend (`rag/pipeline.py` via `_emit_root`) | — | Wall-clock measurement at root span emit time |
| `GET /traces` list + filters | API / Backend (`api/traces.py`) | — | Single-table SQL against denormalized `traces` |
| `GET /traces/{trace_id}` tree | API / Backend (`api/traces.py`) | — | Two queries; `TraceStore` Protocol |
| Dashboard list UI | Browser / Frontend (`pages/Dashboard.tsx`) | — | TanStack Query + shadcn Table + Tremor KpiCard/AreaChart |
| Trace detail UI + waterfall | Browser / Frontend (`pages/TraceDetail.tsx` + `SpanWaterfall.tsx`) | — | Hand-rolled positioned divs; TanStack Query one-shot |
| Route management | Browser / Frontend (`router.tsx`) | — | react-router-dom; replace `/traces/:id` stub |

---

## Standard Stack

All libraries are already in `pyproject.toml` or `package.json` from Phases 2–3. Phase 4 adds zero new runtime dependencies.

### Core (Backend — no new deps)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `asyncpg` | 0.29+ | Async Postgres driver; `executemany` batch insert | Already in stack; `pool.acquire()` context manager; `executemany` is atomic and faster than N individual INSERTs [VERIFIED: Context7 /magicstack/asyncpg] |
| `pydantic` v2 | 2.x | `Span` model (existing); `TraceListItem`/`TraceDetailResponse` schemas | Already in stack; `model_dump(mode="json")` for JSON serialization |
| `structlog` | 24.x | `tracer.queue_saturated` + `tracer.shutdown_drain_incomplete` logs | Already in stack; `log = structlog.get_logger()` pattern |
| `alembic` | 1.x | New revision `000N_traces_denorm.py` | Already in stack; `op.execute(sa.text(...))` for DDL |
| `fastapi` | 0.128.x | `app.include_router(traces.router)` + lifespan consumer task ownership | Already in stack |
| `asyncio` stdlib | Python 3.12 | `asyncio.Lock`, `asyncio.Event`, `asyncio.wait_for`, `asyncio.create_task` | No install needed |
| `collections.deque` stdlib | Python 3.12 | `BoundedDropOldestQueue` backing store | No install needed; O(1) append + popleft |
| `base64` stdlib | Python 3.12 | Cursor encoding/decoding | No install needed |
| `json` stdlib | Python 3.12 | Cursor JSON serialization | No install needed |

### Core (Frontend — no new packages)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `@tanstack/react-query` | 5.x | `useQuery` for list + detail fetches; one-shot refetch via `useEffect`+`setTimeout` | Already in `package.json` (Phase 2 D-2.30); QueryClientProvider already wired in `main.tsx` (Phase 3) [VERIFIED: Context7 /tanstack/query] |
| `@tremor/react` | 3.x | `KpiCard` (or equivalent `Card` + stat) + `AreaChart` | Already in `package.json` (Phase 2 D-2.30) [VERIFIED: Context7 /tremorlabs/tremor] |
| `react-router-dom` | 6.x | New `/dashboard` + `/dashboard/traces/:trace_id` routes | Already in `package.json` (Phase 3) |
| `ky` | latest | `ky.get("/traces", {searchParams: filters}).json()` | Already in `package.json` (Phase 3) |

### shadcn Components to Add in Phase 4
| Component | Install Command | Already Present? |
|-----------|----------------|-----------------|
| `Tabs` / `TabsList` / `TabsTrigger` / `TabsContent` | `npx shadcn@latest add tabs` | NO — not in current `frontend/src/components/ui/` |
| `Table` / `TableHeader` / `TableBody` / `TableRow` / `TableCell` / `TableHead` | `npx shadcn@latest add table` | NO |
| `Slider` | `npx shadcn@latest add slider` | NO |
| `Tooltip` / `TooltipContent` / `TooltipTrigger` | `npx shadcn@latest add tooltip` | NO |
| `Badge` | `npx shadcn@latest add badge` | YES — `frontend/src/components/ui/badge.tsx` exists |
| `Input` | `npx shadcn@latest add input` | YES — `frontend/src/components/ui/input.tsx` exists |
| `Skeleton` | `npx shadcn@latest add skeleton` | YES — `frontend/src/components/ui/skeleton.tsx` exists |
| `Select` | `npx shadcn@latest add select` | VERIFY — not confirmed in glob results; install defensively |

[VERIFIED: Context7 /shadcn-ui/ui for install commands and composition rules]

**Batch install command (Plan 5 Wave 0):**
```bash
npx shadcn@latest add tabs table slider tooltip select
```

---

## Architecture Patterns

### System Architecture Diagram

```
POST /chat request
       │
       ▼
pipeline._orchestrate(query)
       │
       ├──► [SYNC] INSERT INTO traces (id, started_at, query_text, root_span_id)
       │                              ← D-4.01: up-front, before embed_batch
       │
       ├──► embed → retrieve → assemble → llm_call
       │    (each stage emits Span with payload= to PostgresTraceWriter.emit())
       │
       └──► [SYNC] writer.emit(root_span)  [Span.payload=None for root]
                   [SYNC] UPDATE traces SET latency_ms=? WHERE id=?
                          ← D-4.03: wall-clock after _emit_root

PostgresTraceWriter.emit(span):   [called synchronously from pipeline]
       │
       ▼
BoundedDropOldestQueue.put(span)  ← O(1); returns bool (queued vs dropped)
       │
       ▼ (async consumer task — separate asyncio.Task)
Consumer loops: accumulate batch until (len≥50 OR 250ms elapsed)
       │
       ▼
pool.acquire() → conn.executemany("INSERT INTO spans ...")  [auto-routes to monthly partition]
             → conn.executemany("INSERT INTO span_payloads ...")  [for spans with payload]
             → conn.execute("UPDATE traces SET latency_ms=? ...")  [for root span]

GET /traces  ──► TraceStore.list_traces(filters, cursor)
                  └──► Single SQL on traces (denorm cols)
                       ORDER BY started_at DESC, id DESC
                       WHERE (started_at, id) < (cursor.started_at, cursor.id)
                       → TraceListResponse {items, next_cursor}

GET /traces/{id} ──► TraceStore.get_trace(id)
                      ├──► SELECT * FROM traces WHERE id=?
                      └──► SELECT spans.*, sp.payload
                            FROM spans
                            LEFT JOIN span_payloads sp ON sp.span_id = spans.id
                            WHERE spans.trace_id=?
                            ORDER BY started_at ASC
                      → TraceDetailResponse {trace, spans, payloads}

Frontend /dashboard ──► useQuery(["traces", filters])
                          └──► ky.get("/traces", {searchParams})
                               → renders KpiCard strip + AreaChart + Table

Frontend /dashboard/traces/:id ──► useQuery(["trace", id])
                                     └──► ky.get(`/traces/${id}`)
                                          → renders Tabs: Spans | Payloads | Feedback
                                          → SpanWaterfall renders positioned divs
```

### Recommended Project Structure (Phase 4 New/Modified Files)

```
tracer_ai/
├── tracer/
│   ├── span.py              # ADD missing constants from docs/trace-schema.md
│   ├── writer.py            # MODIFY: add payload field, remove payload_id field
│   ├── store.py             # FILL: TraceStore Protocol + PostgresTraceStore
│   └── exporters/
│       ├── queue.py         # NEW: BoundedDropOldestQueue
│       └── postgres.py      # FILL: PostgresTraceWriter + consumer task
├── rag/
│   └── pipeline.py          # MODIFY: up-front traces INSERT, payload= args, latency UPDATE
├── api/
│   ├── lifespan.py          # MODIFY: swap Noop→Postgres writer, start/stop consumer
│   ├── feedback.py          # MODIFY: add UPDATE traces SET feedback_rating
│   ├── main.py              # MODIFY: include traces router
│   ├── schemas.py           # VERIFY/ADD: TraceListItem, TraceListResponse, TraceDetailResponse
│   └── traces.py            # NEW: GET /traces + GET /traces/{trace_id}
alembic/
└── versions/
    └── 0002_traces_denorm.py  # NEW: adds latency_ms, faithfulness, feedback_rating to traces
frontend/src/
├── router.tsx               # MODIFY: add /dashboard + /dashboard/traces/:id; remove /traces/:id
├── components/
│   ├── AppShell.tsx         # MODIFY: add Dashboard nav link
│   ├── MessageBubble.tsx    # (no change — link target updated via MetadataStrip)
│   ├── MetadataStrip.tsx    # MODIFY: change /traces/${id} to /dashboard/traces/${id}
│   └── SpanWaterfall.tsx    # NEW
├── pages/
│   ├── Dashboard.tsx        # NEW
│   ├── TraceDetail.tsx      # NEW
│   └── TraceStub.tsx        # DELETE
└── components/ui/
    ├── tabs.tsx             # ADD via shadcn CLI
    ├── table.tsx            # ADD via shadcn CLI
    ├── slider.tsx           # ADD via shadcn CLI
    ├── tooltip.tsx          # ADD via shadcn CLI
    └── select.tsx           # VERIFY / ADD via shadcn CLI
```

---

## Pattern 1: BoundedDropOldestQueue

**What:** A custom queue wrapping `collections.deque` with `asyncio.Lock` + `asyncio.Event`. Supports drop-oldest under saturation. Producer-side `put()` is O(1). Consumer-side `get()` awaits an event rather than polling.

**Why custom vs `asyncio.Queue`:** `asyncio.Queue.put_nowait()` + exception + `get_nowait()` retry has a race window between the popleft and the append under concurrent producers. `collections.deque` with a lock gives deterministic ordering guarantees. [ASSUMED — asyncio.Queue race condition under concurrent producers; the decision is locked in D-4.06]

**Pattern:**
```python
# tracer_ai/tracer/exporters/queue.py
import asyncio
import time
from collections import deque
from typing import Any

import structlog

log = structlog.get_logger()


class BoundedDropOldestQueue:
    """Bounded queue that drops the OLDEST item when full (D-4.05/D-4.06/D-4.07)."""

    def __init__(self, maxsize: int) -> None:
        self._maxsize = maxsize
        self._deque: deque[Any] = deque()
        self._lock = asyncio.Lock()
        self._not_empty = asyncio.Event()
        # Rate-limited saturation logging state (D-4.08)
        self._dropped_count: int = 0
        self._last_log_at: float = 0.0

    async def put(self, item: Any) -> bool:
        """Enqueue item. Returns True if queued, False if an old item was dropped."""
        dropped = False
        async with self._lock:
            if len(self._deque) >= self._maxsize:
                self._deque.popleft()  # Drop oldest
                self._dropped_count += 1
                dropped = True
                # Rate-limited log: at most once per second (D-4.08)
                now = time.monotonic()
                if now - self._last_log_at >= 1.0:
                    log.warning(
                        "tracer.queue_saturated",
                        dropped=self._dropped_count,
                        window="1s",
                        queue_depth=len(self._deque),
                    )
                    self._dropped_count = 0
                    self._last_log_at = now
            self._deque.append(item)
            self._not_empty.set()
        return not dropped

    async def get(self) -> Any:
        """Await next item."""
        while True:
            await self._not_empty.wait()
            async with self._lock:
                if self._deque:
                    item = self._deque.popleft()
                    if not self._deque:
                        self._not_empty.clear()
                    return item
                # Spurious wake — loop

    def qsize(self) -> int:
        return len(self._deque)
```

**Key correctness invariants:**
- `_not_empty.clear()` happens under the lock AFTER confirming deque is empty.
- `get()` loops on spurious wakes (multiple consumers competing — Phase 4 has only one consumer, but the pattern is safe).
- The lock is always released before the `await self._not_empty.wait()` call to avoid deadlock.

[ASSUMED — the specific implementation above; the API shape (put/get/qsize returning bool) is LOCKED in D-4.06]

---

## Pattern 2: PostgresTraceWriter + Consumer Task

**What:** `PostgresTraceWriter` satisfies the `TraceWriter` Protocol. It enqueues spans via `BoundedDropOldestQueue`. A separate `asyncio.Task` (the "consumer") drains the queue in batches using `executemany`.

**asyncpg executemany semantics:**
- `conn.executemany(sql, list_of_tuples)` is atomic (all-or-nothing). [VERIFIED: Context7 /magicstack/asyncpg]
- Works with `pool.acquire()` as an async context manager; connection is returned to pool on context exit. [VERIFIED: Context7 /magicstack/asyncpg]
- Postgres automatically routes INSERTs to the correct monthly partition via the `PARTITION BY RANGE (started_at)` rule — no special routing code needed. [ASSUMED — standard Postgres partitioned-table routing behavior]
- The `spans` table has composite PK `(id, started_at)` — the INSERT must include `started_at`.
- `span_payloads` has no FK to `spans` (intentional — partitioned-parent FK is expensive); application-layer ordering is: INSERT spans first, then INSERT span_payloads.

**Batch flush logic:**
```python
# tracer_ai/tracer/exporters/postgres.py (consumer task excerpt)
import asyncio
import time
from typing import Any
from uuid import UUID

import asyncpg
import structlog

from tracer_ai.tracer.writer import Span

log = structlog.get_logger()
_BATCH_SIZE = 50
_FLUSH_INTERVAL = 0.250  # seconds


class SpanConsumer:
    """Background asyncio.Task that drains BoundedDropOldestQueue in batches."""

    def __init__(self, queue: "BoundedDropOldestQueue", pool: asyncpg.Pool) -> None:
        self._queue = queue
        self._pool = pool
        self.stop_accepting: bool = False  # Set True during shutdown (D-4.10)

    async def run(self) -> None:
        batch: list[Span] = []
        batch_started_at: float = time.monotonic()

        while True:
            # Determine time remaining until flush deadline
            elapsed = time.monotonic() - batch_started_at
            remaining = max(0.0, _FLUSH_INTERVAL - elapsed)

            try:
                span = await asyncio.wait_for(self._queue.get(), timeout=remaining)
                batch.append(span)
            except asyncio.TimeoutError:
                pass  # Time-based flush trigger

            should_flush = (
                len(batch) >= _BATCH_SIZE
                or (batch and time.monotonic() - batch_started_at >= _FLUSH_INTERVAL)
            )
            if should_flush and batch:
                await self._flush(batch)
                batch = []
                batch_started_at = time.monotonic()

    async def drain(self) -> None:
        """Flush all remaining items. Called during shutdown (D-4.10)."""
        batch: list[Span] = []
        while self._queue.qsize() > 0:
            try:
                span = await asyncio.wait_for(self._queue.get(), timeout=0.1)
                batch.append(span)
            except asyncio.TimeoutError:
                break
        if batch:
            await self._flush(batch)

    async def _flush(self, spans: list[Span]) -> None:
        span_rows = [
            (
                str(span.span_id),
                str(span.trace_id),
                str(span.parent_span_id) if span.parent_span_id else None,
                span.name,
                span.started_at,
                span.ended_at,
                span.attrs,  # asyncpg serializes dict → jsonb
            )
            for span in spans
        ]
        payload_rows = [
            (str(span.span_id), span.payload)
            for span in spans
            if span.payload is not None
        ]
        # Find the root span to UPDATE traces.latency_ms
        root_spans = [s for s in spans if s.parent_span_id is None and s.name == "rag.request"]

        async with self._pool.acquire() as conn:
            await conn.executemany(
                "INSERT INTO spans (id, trace_id, parent_span_id, name, started_at, ended_at, attrs) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7) "
                "ON CONFLICT (id, started_at) DO NOTHING",
                span_rows,
            )
            if payload_rows:
                await conn.executemany(
                    "INSERT INTO span_payloads (span_id, payload) VALUES ($1, $2) "
                    "ON CONFLICT (span_id) DO NOTHING",
                    payload_rows,
                )
            if root_spans:
                # UPDATE traces.latency_ms from the root span attrs
                for root in root_spans:
                    latency = root.attrs.get("rag.latency_ms")
                    if latency is not None:
                        await conn.execute(
                            "UPDATE traces SET latency_ms = $1 WHERE id = $2",
                            int(latency),
                            str(root.trace_id),
                        )
```

**Note on `attrs` JSONB serialization:** asyncpg accepts a Python `dict` for a `jsonb` column directly when the connection is configured with a JSON codec, or you can pass `json.dumps(span.attrs)` as a string. The safer approach for Phase 4 is `json.dumps(span.attrs)` with explicit column type hint or using asyncpg's codec registration. [ASSUMED — asyncpg JSONB dict-direct support; verify at test time]

**Alternative (safer) attrs serialization:**
```python
import json
# In _flush, serialize attrs explicitly:
"attrs": json.dumps(span.attrs)
# And column type: jsonb — asyncpg accepts string for jsonb column without codec
```

---

## Pattern 3: Lifespan Integration (FastAPI + Consumer Task)

**What:** Swap `NoopTraceWriter` to `PostgresTraceWriter` in `lifespan.py`. Start the consumer `asyncio.Task`. Register drain + pool teardown in `finally`.

**Pattern:**
```python
# tracer_ai/api/lifespan.py — Phase 4 additions (partial)
from tracer_ai.tracer.exporters.postgres import PostgresTraceWriter, SpanConsumer
from tracer_ai.tracer.exporters.queue import BoundedDropOldestQueue

# Inside lifespan(), after pool is created:
_queue = BoundedDropOldestQueue(maxsize=1000)
writer = PostgresTraceWriter(queue=_queue)
consumer = SpanConsumer(queue=_queue, pool=pool)
consumer_task = asyncio.create_task(consumer.run(), name="tracer-consumer")
app.state.trace_writer = writer
app.state.consumer = consumer
app.state.consumer_task = consumer_task
# Rebuild pipeline with new writer:
app.state.pipeline = Pipeline(embedder, retriever, llm, writer, top_k=5)

try:
    yield
finally:
    # D-4.10: Signal consumer to stop, drain, then close pool
    consumer.stop_accepting = True
    try:
        await asyncio.wait_for(consumer.drain(), timeout=5.0)
    except asyncio.TimeoutError:
        remaining = _queue.qsize()
        log.warning("tracer.shutdown_drain_incomplete", remaining=remaining)
    consumer_task.cancel()
    try:
        await consumer_task
    except asyncio.CancelledError:
        pass
    await pool.close()
    log.info("db_pool_closed")
```

**Ordering constraint:** Consumer task must be cancelled AFTER drain completes (or times out). Pool must close AFTER consumer task is stopped. [ASSUMED — standard asyncio teardown ordering]

---

## Pattern 4: Alembic Incremental Revision

**What:** New revision file `alembic/versions/0002_traces_denorm.py` adds three nullable columns to the `traces` table. Uses hand-written DDL (same pattern as `0001_initial.py`).

**Pattern:**
```python
# alembic/versions/0002_traces_denorm.py
"""add latency_ms, faithfulness, feedback_rating to traces (Phase 4 D-4.02)

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-06

Never edit 0001_initial.py (D-2.17). This revision is additive-only.
Downgrade reverses the three ALTER TABLE statements.
"""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(sa.text("ALTER TABLE traces ADD COLUMN IF NOT EXISTS latency_ms INT NULL;"))
    op.execute(sa.text("ALTER TABLE traces ADD COLUMN IF NOT EXISTS faithfulness REAL NULL;"))
    op.execute(sa.text("ALTER TABLE traces ADD COLUMN IF NOT EXISTS feedback_rating SMALLINT NULL;"))
    # Index for filter queries (EXPL-01: min_faithfulness, feedback filters)
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS traces_faithfulness_idx ON traces (faithfulness);"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS traces_feedback_rating_idx ON traces (feedback_rating);"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS traces_faithfulness_idx;"))
    op.execute(sa.text("DROP INDEX IF EXISTS traces_feedback_rating_idx;"))
    op.execute(sa.text("ALTER TABLE traces DROP COLUMN IF EXISTS latency_ms;"))
    op.execute(sa.text("ALTER TABLE traces DROP COLUMN IF EXISTS faithfulness;"))
    op.execute(sa.text("ALTER TABLE traces DROP COLUMN IF EXISTS feedback_rating;"))
```

**Reversibility test (per D-4.25):** `alembic upgrade head` → `alembic downgrade -1` → `alembic upgrade head` on a Phase 2/3 DB clone. The `IF NOT EXISTS` / `IF EXISTS` guards make this idempotent.

[ASSUMED — `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` is PostgreSQL 9.6+; confirmed available in Postgres 16]

---

## Pattern 5: GET /traces — Keyset Cursor Pagination

**What:** Cursor-paginated list of traces. Cursor encodes `(started_at, id)` as base64 JSON. Single-table query against `traces` with denormalized filter columns.

**SQL pattern:**
```sql
-- Without cursor (first page):
SELECT id, started_at, query_text, latency_ms, faithfulness, feedback_rating
FROM traces
WHERE
  (query_text ILIKE '%' || $1 || '%' OR $1 IS NULL)
  AND (started_at >= $2 OR $2 IS NULL)
  AND (started_at <= $3 OR $3 IS NULL)
  AND (feedback_rating = $4 OR $4 IS NULL)
  AND (faithfulness >= $5 OR $5 IS NULL)
  AND (latency_ms <= $6 OR $6 IS NULL)
ORDER BY started_at DESC, id DESC
LIMIT $7;

-- With cursor (subsequent pages) — D-4.19 row-value comparison:
... AND (started_at, id) < ($cursor_started_at, $cursor_id)
ORDER BY started_at DESC, id DESC
LIMIT $limit;
```

**Cursor encode/decode:**
```python
import base64, json
from datetime import datetime
from uuid import UUID

def encode_cursor(started_at: datetime, trace_id: UUID) -> str:
    payload = {"started_at": started_at.isoformat(), "id": str(trace_id)}
    return base64.b64encode(json.dumps(payload).encode()).decode()

def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    payload = json.loads(base64.b64decode(cursor).decode())
    return datetime.fromisoformat(payload["started_at"]), UUID(payload["id"])
```

**Note on row-value comparison with partitioned table:** Postgres supports `(a, b) < ($1, $2)` row-value comparisons on any table including partitioned parents. The `traces_started_at_idx ON traces (started_at DESC)` index from `0001_initial.py` is used for the `ORDER BY` + keyset filter. A composite index `(started_at DESC, id DESC)` would be more efficient but is a Phase 7 polish item — the single-column index suffices for Phase 4 single-user load. [ASSUMED — row-value comparison on partitioned parent table; Postgres 16 supports this. Composite index missing is an accepted gap.]

**Feedback filter mapping:**
```python
# "up" → feedback_rating = 1; "down" → feedback_rating = -1
feedback_value: int | None = None
if filters.feedback == "up":
    feedback_value = 1
elif filters.feedback == "down":
    feedback_value = -1
```

---

## Pattern 6: GET /traces/{trace_id} — Two-Query Pattern

**What:** Two async queries in the same acquired connection: (1) fetch trace row, (2) fetch spans with LEFT JOIN to span_payloads.

```python
# tracer_ai/api/traces.py (excerpt)
async with pool.acquire() as conn:
    trace_row = await conn.fetchrow(
        "SELECT id, started_at, query_text, latency_ms, faithfulness, feedback_rating "
        "FROM traces WHERE id = $1",
        trace_id,
    )
    if trace_row is None:
        raise HTTPException(status_code=404, detail={"error_code": "TRACE_NOT_FOUND"})

    span_rows = await conn.fetch(
        "SELECT s.id, s.parent_span_id, s.name, s.started_at, s.ended_at, s.attrs, "
        "       sp.payload "
        "FROM spans s "
        "LEFT JOIN span_payloads sp ON sp.span_id = s.id "
        "WHERE s.trace_id = $1 "
        "ORDER BY s.started_at ASC",
        trace_id,
    )
```

**Note:** `spans` is a partitioned table. The `WHERE s.trace_id = $1` query uses the `spans_y2026m05_trace_id_idx` (and equivalent per-partition indexes) for a partition-pruned scan. Without a `started_at` range filter, Postgres scans all partitions — acceptable for Phase 4 (few partitions). [ASSUMED — Postgres partition pruning without started_at filter results in cross-partition scan; accepted for Phase 4 volume]

**`attrs` deserialization:** asyncpg returns `jsonb` columns as Python `dict` automatically when using default connection settings. [VERIFIED: Context7 /magicstack/asyncpg — asyncpg handles JSONB natively]

---

## Pattern 7: Up-Front traces INSERT in pipeline.py

**What:** Before `embedder.embed_batch`, pipeline calls a synchronous DB INSERT to create the `traces` row. Uses the shared pool from `app.state.db_pool`.

**Complication:** `pipeline.py` lives in `tracer/` dependency tree and must NOT import from `api/`. Per module-deps DAG (D-2.27), `tracer/` must not import `api/`. Solution: pass the pool (or a `traces_writer` callable) as a constructor argument to `Pipeline`, the same way `TraceWriter` is injected.

```python
# tracer_ai/rag/pipeline.py — Phase 4 addition
# Pipeline.__init__ adds optional pool parameter:
def __init__(
    self,
    embedder: Embedder,
    retriever: Retriever,
    llm: LLMProtocol,
    writer: TraceWriter,
    *,
    top_k: int = 5,
    db_pool: asyncpg.Pool | None = None,  # NEW
) -> None:
    ...
    self._db_pool = db_pool

# Inside _orchestrate, before embed_batch:
if self._db_pool is not None:
    async with self._db_pool.acquire(timeout=2.0) as conn:
        await conn.execute(
            "INSERT INTO traces (id, started_at, query_text, root_span_id) "
            "VALUES ($1, $2, $3, $4) "
            "ON CONFLICT (id) DO NOTHING",
            str(trace_id),
            root_started,
            query[:4000],  # max query_text length per api.md
            str(root_span_id),
        )
```

**lifespan.py** passes `db_pool=pool` when constructing Pipeline. The `ON CONFLICT DO NOTHING` guard prevents errors if the same trace_id is somehow re-submitted (defensive; in practice UUIDs don't collide).

[ASSUMED — passing pool to Pipeline as optional kwarg; no module-deps violation since asyncpg is already a tracer_ai dep and Pool lives in asyncpg, not api/]

---

## Pattern 8: pipeline.py UPDATE traces SET latency_ms

**What:** After `_emit_root`, the pipeline UPDATEs `traces.latency_ms`. The `latency_ms` value is already computed in `_emit_root` as `int((time.perf_counter() - t0) * 1000)`.

```python
# tracer_ai/rag/pipeline.py — _emit_root addition
async def _emit_root(self, trace_id, root_span_id, root_started, root_attrs, t0):
    latency_ms = int((time.perf_counter() - t0) * 1000)
    root_attrs[_ATTR_LATENCY_MS] = latency_ms
    await self.writer.emit(Span(...))
    # Phase 4 addition: UPDATE traces
    if self._db_pool is not None:
        async with self._db_pool.acquire(timeout=2.0) as conn:
            await conn.execute(
                "UPDATE traces SET latency_ms = $1, ended_at = $2 WHERE id = $3",
                latency_ms,
                _now(),
                str(trace_id),
            )
    log.info("pipeline_run_complete", ...)
```

This write is synchronous on the request path. The two synchronous DB writes (up-front INSERT + end UPDATE) each take < 5ms at local Postgres — total overhead < 10ms for the synchronous portion. This is within the 100ms p95 budget for trace write overhead. [ASSUMED — < 5ms per indexed local Postgres write; consistent with D-4.01 tradeoff analysis]

---

## Pattern 9: feedback.py UPDATE traces SET feedback_rating

**What:** Phase 3's `post_feedback` already does `INSERT INTO feedback`. Phase 4 adds `UPDATE traces SET feedback_rating = ? WHERE id = ?` in the same DB connection (not same transaction by default — use explicit transaction for atomicity).

```python
# tracer_ai/api/feedback.py — Phase 4 addition
async with pool.acquire(timeout=1.0) as conn:
    async with conn.transaction():  # atomic: both or neither
        row = await conn.fetchrow(
            "INSERT INTO feedback (trace_id, rating, comment, diagnosis_tag) "
            "VALUES ($1, $2, $3, $4) RETURNING id, created_at",
            body.trace_id, body.rating, body.comment, body.diagnosis_tag,
        )
        await conn.execute(
            "UPDATE traces SET feedback_rating = $1 WHERE id = $2",
            body.rating,
            body.trace_id,
        )
```

[VERIFIED: Context7 /magicstack/asyncpg — `async with conn.transaction()` is the canonical pattern]

---

## Pattern 10: SpanWaterfall Component

**What:** Hand-rolled React component rendering one row per span with absolute-positioned bar. No JS animation — pure Tailwind CSS classes for visual rendering.

**Core layout math:**
- Root span has `started_at = t0`, `ended_at = t_root`. `root_duration = t_root - t0` in ms.
- Each span bar: `left = (span.started_at - t0) / root_duration * 100%`, `width = span_duration / root_duration * 100%`.
- Min-width: 4px absolute (not percentage) to ensure very-fast spans are visible. Use `style={{ left: `${left}%`, width: `max(4px, ${width}%)` }}`.
- Parent-line glyph: `├─` for non-last children; `└─` for last sync child; `└╌╌` (dashed) for `rag.eval` async child (Phase 5 surface; hidden in Phase 4 per D-4.16).

**Type definition:**
```typescript
// frontend/src/components/SpanWaterfall.tsx
interface WaterfallSpan {
  span_id: string;
  parent_span_id: string | null;
  name: string;
  started_at: string;  // ISO8601
  ended_at: string | null;
  attrs: Record<string, unknown>;
}

interface SpanWaterfallProps {
  spans: WaterfallSpan[];
  root_duration_ms: number;
}
```

**Bar rendering:**
```tsx
function SpanRow({ span, rootStartedAt, rootDurationMs }: SpanRowProps) {
  const spanStart = new Date(span.started_at).getTime();
  const spanEnd = span.ended_at ? new Date(span.ended_at).getTime() : spanStart;
  const rootStart = new Date(rootStartedAt).getTime();

  const leftPct = Math.max(0, (spanStart - rootStart) / rootDurationMs) * 100;
  const widthPct = Math.max(0, (spanEnd - spanStart) / rootDurationMs) * 100;
  const durationMs = spanEnd - spanStart;

  return (
    <div className="relative flex items-center h-8 border-b border-border last:border-0">
      {/* Glyph */}
      <span className="font-mono text-xs text-muted-foreground w-36 shrink-0 pl-2">
        {span.name}
      </span>
      {/* Bar track */}
      <div className="relative flex-1 h-4 bg-muted/30 rounded-sm mx-2">
        <div
          className="absolute h-full bg-blue-500 rounded-sm"
          style={{
            left: `${leftPct}%`,
            width: `max(4px, ${widthPct}%)`,
          }}
        />
      </div>
      {/* Duration label */}
      <span className="text-xs text-muted-foreground w-16 text-right pr-2 shrink-0">
        {durationMs}ms
      </span>
    </div>
  );
}
```

**Click-to-expand attrs:** controlled by `useState<Set<string>>` of expanded span_ids. On click, toggle membership. Render `<pre className="text-xs font-mono bg-muted p-2 rounded overflow-auto">` with `JSON.stringify(span.attrs, null, 2)`.

[ASSUMED — specific CSS class choices; pattern is standard for waterfall visualizations]

---

## Pattern 11: TanStack Query Wiring for Dashboard

**What:** `useQuery` for trace list with filter dependencies in queryKey; cursor-based `fetchNextPage` pattern via manual "Load more" button.

**List page:**
```typescript
// frontend/src/pages/Dashboard.tsx
const { data, isLoading, isError } = useQuery({
  queryKey: ["traces", filters],  // re-fetches when filters change
  queryFn: () => ky.get("/traces", {
    searchParams: {
      ...(filters.query ? { query: filters.query } : {}),
      ...(filters.since ? { since: filters.since } : {}),
      limit: 50,
      ...(cursor ? { cursor } : {}),
    }
  }).json<TraceListResponse>(),
  staleTime: 0,  // Always re-fetch on mount (dashboard shows real-time data)
});
```

[VERIFIED: Context7 /tanstack/query — queryKey array, staleTime, queryFn pattern]

**"Load more" pattern (manual cursor append):** Use `useState<string | null>` for cursor. On "Load more" click, set cursor to `data.next_cursor` and call `queryClient.fetchQuery(["traces", filters, cursor])` OR use `useInfiniteQuery`. For Phase 4, the simpler approach is `useState<TraceListItem[]>` that accumulates across cursor calls. [ASSUMED — simple cursor accumulation is cleaner than useInfiniteQuery for a "Load more" button]

**Detail page (one-shot refetch for eval-pending):**
```typescript
// frontend/src/pages/TraceDetail.tsx
const { data } = useQuery({
  queryKey: ["trace", traceId],
  queryFn: () => ky.get(`/traces/${traceId}`).json<TraceDetailResponse>(),
});

// One-shot refetch after 5s if rag.eval is pending (D-4.18 / forward-compat only)
const evalSpan = data?.spans.find(s => s.name === "rag.eval");
const evalPending = evalSpan && !evalSpan.ended_at;

useEffect(() => {
  if (!evalPending) return;
  const timer = setTimeout(() => {
    queryClient.invalidateQueries({ queryKey: ["trace", traceId] });
  }, 5000);
  return () => clearTimeout(timer);
}, [evalPending, traceId, queryClient]);
```

[VERIFIED: Context7 /tanstack/query — queryClient.invalidateQueries, useEffect with setTimeout]

---

## Pattern 12: Tremor v3 KpiCard + AreaChart (Dashboard List)

**What:** KPI strip using Tremor's `Card` component (Tremor v3 does not expose a dedicated `KpiCard` export in the raw library; the pattern is a `Card` with `Metric` + `Text` sub-components, OR using `@tremor/react`'s layout blocks).

**Tremor v3 AreaChart:**
```tsx
import { AreaChart } from "@tremor/react";

const chartData = [
  { date: "2026-05-01", faithfulness: 0.82, relevance: 0.91 },
  // ... derived from trace list items
];

<AreaChart
  data={chartData}
  index="date"
  categories={["faithfulness", "relevance"]}
  colors={["emerald", "blue"]}
  valueFormatter={(v) => v.toFixed(2)}
  showLegend
  showGridLines={false}
/>
```

**Empty-data placeholder (Phase 4: no faithfulness data):** When `chartData` has all-null faithfulness values, pass an empty array or `data` with zeroed values. Tremor `AreaChart` renders an empty chart gracefully with axes visible. [VERIFIED: Context7 /tremorlabs/tremor — AreaChart accepts empty data array]

**KPI card pattern:**
```tsx
// Tremor v3 raw uses Card as the container; no dedicated KpiCard component in raw
import { Card } from "@tremor/react";

<Card>
  <p className="text-sm text-muted-foreground">Avg Latency</p>
  <p className="text-2xl font-semibold">{avgLatencyMs}ms</p>
</Card>
```

[ASSUMED — Tremor v3 raw `Card` for KPI; the CLAUDE.md references `KpiCard` from Tremor Blocks which is a separate package; Phase 4 can use raw `Card` + stat text unless Tremor Blocks is already installed]

---

## Pattern 13: shadcn Tabs + Table Wiring

**shadcn Tabs (verified API):**
```tsx
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"

<Tabs defaultValue="spans">
  <TabsList>
    <TabsTrigger value="spans">Spans</TabsTrigger>
    <TabsTrigger value="payloads">Payloads</TabsTrigger>
    <TabsTrigger value="feedback">Feedback</TabsTrigger>
  </TabsList>
  <TabsContent value="spans"><SpanWaterfall spans={data.spans} /></TabsContent>
  <TabsContent value="payloads">...</TabsContent>
  <TabsContent value="feedback">...</TabsContent>
</Tabs>
```

[VERIFIED: Context7 /shadcn-ui/ui — TabsTrigger must be inside TabsList; composition hierarchy confirmed]

**shadcn Table (verified API):**
```tsx
import {
  Table, TableHeader, TableBody, TableRow,
  TableHead, TableCell
} from "@/components/ui/table"

<Table>
  <TableHeader>
    <TableRow>
      <TableHead>Time</TableHead>
      <TableHead>Query</TableHead>
      <TableHead>Latency</TableHead>
      <TableHead>Cost</TableHead>
      <TableHead>Faithfulness</TableHead>
      <TableHead>Feedback</TableHead>
    </TableRow>
  </TableHeader>
  <TableBody>
    {items.map(item => (
      <TableRow key={item.trace_id} onClick={() => navigate(`/dashboard/traces/${item.trace_id}`)} className="cursor-pointer">
        <TableCell>...</TableCell>
      </TableRow>
    ))}
  </TableBody>
</Table>
```

[VERIFIED: Context7 /shadcn-ui/ui]

**shadcn Slider:**
```tsx
import { Slider } from "@/components/ui/slider"

<Slider
  defaultValue={[0]}
  max={1}
  step={0.05}
  onValueChange={([v]) => setMinFaithfulness(v)}
  className="w-48"
/>
```

[VERIFIED: Context7 /shadcn-ui/ui]

**shadcn Tooltip:**
```tsx
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"

<Tooltip>
  <TooltipTrigger asChild>
    <span>{item.faithfulness?.toFixed(2) ?? "—"}</span>
  </TooltipTrigger>
  <TooltipContent>Source span: {item.span_id}</TooltipContent>
</Tooltip>
```

[VERIFIED: Context7 /shadcn-ui/ui]

**shadcn Badge variants for feedback:**
```tsx
import { Badge } from "@/components/ui/badge"

<Badge variant={item.feedback_rating === 1 ? "default" : item.feedback_rating === -1 ? "destructive" : "outline"}>
  {item.feedback_rating === 1 ? "👍" : item.feedback_rating === -1 ? "👎" : "—"}
</Badge>
```

[VERIFIED: Context7 /shadcn-ui/ui — `Badge` has `default | outline | secondary | destructive` variants]

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Async connection pool | Custom connection management | `asyncpg.create_pool()` | Already in lifespan.py; handles health checks, max_inactive lifetime |
| Batch SQL | N individual `conn.execute()` calls | `conn.executemany()` | Atomic, significantly faster for batch inserts [VERIFIED] |
| JSON cursor serialization | Custom binary format | `base64(json.dumps({...}))` | Opaque to client, trivially decodable, reversible |
| Tab UI state management | Custom tab component | `shadcn Tabs` | Radix UI primitives; keyboard accessible; zero re-implementation |
| Table rendering | Raw `<table>` HTML | `shadcn Table` components | Consistent border/cell styling; already in stack |
| Chart rendering | Raw SVG/canvas | Tremor `AreaChart` | Recharts-backed; same `colors` API as rest of dashboard |
| Waterfall timing | `recharts BarChart` | Custom `SpanWaterfall` div | `BarChart` doesn't support absolute positioning within a shared timeline; custom is ~50 LOC |

**Key insight:** For Phase 4, the span waterfall is the one place where a custom component is genuinely better than a chart library — the waterfall requires absolute pixel positioning on a shared timeline axis, which Tremor/Recharts bar charts don't provide without substantial hacking.

---

## Common Pitfalls

### Pitfall 1: `spans` FK to `traces` requires up-front INSERT
**What goes wrong:** `SpanConsumer._flush()` inserts spans before `INSERT INTO traces` completes, violating the FK constraint `spans.trace_id REFERENCES traces(id) ON DELETE CASCADE`.
**Why it happens:** If the up-front INSERT is async (queued), the consumer may process span rows before the trace row exists.
**How to avoid:** D-4.01 mandates synchronous up-front INSERT. The FK is satisfied before any span flush. The INSERT uses `ON CONFLICT DO NOTHING` for idempotency.
**Warning signs:** `asyncpg.ForeignKeyViolationError` in consumer task logs.

### Pitfall 2: `span_payloads` INSERT order
**What goes wrong:** INSERT span_payloads before INSERT spans completes. `span_payloads.span_id` has no FK (intentional — partitioned table), but the INSERT must still happen after spans to ensure logical consistency.
**Why it happens:** `executemany` for spans and payloads are separate calls; if the payloads call is issued first, and spans INSERT fails, payloads are orphaned.
**How to avoid:** Always INSERT spans first, then payloads, in the same `pool.acquire()` block.
**Warning signs:** `span_payloads` rows with no corresponding `spans` row.

### Pitfall 3: asyncpg JSONB serialization
**What goes wrong:** Passing a Python dict to an `asyncpg.execute()` call for a `jsonb` column raises a type error or stores garbage.
**Why it happens:** asyncpg's default codec may not auto-serialize `dict` to `jsonb` without explicit codec registration.
**How to avoid:** Pass `json.dumps(span.attrs)` explicitly (string → jsonb coercion works in Postgres). OR register a JSON codec on pool creation: `init=lambda conn: conn.set_type_codec('jsonb', encoder=json.dumps, decoder=json.loads, schema='pg_catalog')`.
**Warning signs:** `asyncpg.InvalidTextRepresentationError` or attrs stored as `null`.

### Pitfall 4: Monthly partition routing for spans older than 2026-07
**What goes wrong:** A span with `started_at` after 2026-07-31 is inserted with no matching partition, raising `ERROR: no partition of relation "spans" found for row`.
**Why it happens:** `0001_initial.py` creates partitions for 2026-05, 2026-06, 2026-07 only.
**How to avoid:** Phase 4 Plan 1 should create an additional partition for 2026-08 (or use a `DEFAULT` partition). Alternatively, create a catch-all default partition in the migration.
**Warning signs:** `asyncpg.InvalidTextRepresentationError` or Postgres partition routing error in consumer logs.

**Mitigation (add to 0002 migration):**
```sql
CREATE TABLE IF NOT EXISTS spans_y2026m08 PARTITION OF spans
    FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');
CREATE INDEX IF NOT EXISTS spans_y2026m08_attrs_gin ON spans_y2026m08 USING gin (attrs);
CREATE INDEX IF NOT EXISTS spans_y2026m08_trace_id_idx ON spans_y2026m08 (trace_id);
```

### Pitfall 5: Row-value comparison `(started_at, id) < ($1, $2)` type mismatch
**What goes wrong:** asyncpg passes Python `datetime` and `UUID` objects; Postgres expects `TIMESTAMPTZ` and `UUID`. The comparison may fail or silently coerce incorrectly.
**Why it happens:** asyncpg handles `datetime` → `TIMESTAMPTZ` and `UUID` → `uuid` natively when types are annotated. Row-value comparison with `$1`, `$2` requires explicit cast or proper type hints.
**How to avoid:** Pass `(cursor_started_at, str(cursor_id))` with explicit `$1::timestamptz` and `$2::uuid` casts in the WHERE clause.
**Warning signs:** `asyncpg.PostgresError` on cursor queries; pagination returning all rows.

**SQL correction:**
```sql
WHERE (started_at, id) < ($1::timestamptz, $2::uuid)
```

### Pitfall 6: `Span.payload_id` field not removed
**What goes wrong:** `writer.py` still has `payload_id: UUID | None = None` after Phase 4 starts. Pipeline code that previously set `payload_id=uuid4()` and new code that sets `payload={}` co-exist; the writer splits on `payload`, not `payload_id`.
**Why it happens:** `Span` model in `writer.py` is modified in Plan 1; pipeline is modified in Plan 1. If execution is partial (Plan 1 partial), old pipeline code may still reference `payload_id`.
**How to avoid:** Atomic Plan 1: in the same task, remove `payload_id` from `Span`, add `payload`, update all pipeline.py `Span(...)` constructors.
**Warning signs:** `mypy --strict` errors on `payload_id` references; `extra="forbid"` Pydantic validation errors.

### Pitfall 7: TanStack Query stale cache on filter change
**What goes wrong:** Filter change re-uses cached `["traces", old_filters]` response because `queryKey` doesn't include all filter fields.
**Why it happens:** If `filters` is a mutable object compared by reference, `queryKey: ["traces", filters]` won't detect field-level changes.
**How to avoid:** Spread filter fields into queryKey: `queryKey: ["traces", filters.query, filters.since, filters.until, filters.feedback, filters.min_faithfulness, filters.max_latency_ms]`.
**Warning signs:** Filter bar changes but table doesn't re-fetch.

### Pitfall 8: Module-deps DAG violation — pipeline imports api/
**What goes wrong:** `pipeline.py` imports `asyncpg.Pool` directly or imports from `tracer_ai.api.*`, violating the DAG (`tracer/rag/` must not import `api/`).
**Why it happens:** Up-front traces INSERT requires DB access; naive solution is to import the pool from lifespan.
**How to avoid:** Pass `db_pool` as a constructor parameter to `Pipeline` (pattern documented above). `asyncpg` is a first-class dep of `tracer_ai/`; importing `asyncpg.Pool` type in `pipeline.py` is safe (it's in the dep graph, not in `api/`).
**Warning signs:** `import_cycle_guard.py` pre-commit hook fires; mypy import error.

### Pitfall 9: Cursor clock skew with multiple writers
**What goes wrong:** Two concurrent requests produce traces with identical `started_at` at millisecond resolution. Keyset pagination returns duplicate rows or skips rows.
**Why it happens:** `(started_at, id)` is not strictly unique if `started_at` values collide. The `id` UUID is unique, but the row-value comparison `(started_at, id) < (cursor.started_at, cursor.id)` may exclude rows with the same `started_at` but lower `id`.
**How to avoid:** Postgres UUID comparison is lexicographic by string representation, NOT by UUID version ordering. Use explicit `uuid_generate_v4()` or Python `uuid4()` which has sufficient randomness. For Phase 4 single-user volume, collisions are effectively zero. Add a comment documenting the limitation.
**Warning signs:** Dashboard shows fewer rows than expected after "Load more". [ASSUMED — clock skew analysis; impact negligible for single-user portfolio scope]

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `asyncio.Queue(maxsize=N)` bounded queue | Custom `collections.deque` + `asyncio.Lock` (D-4.06) | Phase 4 ADR | Eliminates race window in put_nowait retry pattern |
| Cursor-based pagination with integer offset | Keyset pagination on `(started_at, id)` | Standard practice for partitioned tables | O(1) cost regardless of page depth |
| Store payloads inline on span row | `span_payloads` JSONB side table (ADR 004) | Phase 1 design | Keeps `spans.attrs` GIN index lean; supports large payloads |
| `gen_ai.system` | `gen_ai.provider.name` (DEPRECATED migration) | OTel GenAI spec 2025 | `gen_ai.system` is deprecated; `gen_ai.provider.name = "anthropic"` is the current value |
| OpenTelemetry SDK runtime | Custom span dataclasses with OTel-named attrs (ADR 005) | Phase 1 ADR | No SDK overhead; portable naming; Phase 5 can add exporter without pipeline changes |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `asyncio.Queue put_nowait+retry` has a race window under concurrent producers | Pattern 1 (BoundedDropOldestQueue rationale) | D-4.06 is locked regardless; alternative queue impl may work but decision is not negotiable |
| A2 | asyncpg requires `json.dumps()` for JSONB columns OR codec registration | Pattern 2 | Consumer flushes fail with type error; fix is one-line codec registration or explicit json.dumps |
| A3 | Row-value comparison `(started_at, id) < ($1, $2)` works on partitioned `traces` table in Postgres 16 | Pattern 5 | Pagination query fails; workaround: separate WHERE clauses `started_at < $1 OR (started_at = $1 AND id < $2)` |
| A4 | `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` is available in Postgres 16 | Pattern 4 | Migration fails; remove `IF NOT EXISTS` guard (standard Alembic practice) |
| A5 | Tremor v3 raw does not expose `KpiCard` as a named export; use `Card` + stat text | Pattern 12 | Minor UI deviation; switch to Tremor Blocks if `@tremor/blocks` is already installed |
| A6 | `collections.deque` append/popleft under `asyncio.Lock` is safe from asyncio cancellation between lock acquire and item operation | Pattern 1 | Edge case: if task is cancelled inside the lock context manager, item may be lost; use `asyncio.shield()` if critical |
| A7 | `Pipeline.__init__` accepting `db_pool: asyncpg.Pool | None` does not violate module-deps DAG | Pattern 7 | import_cycle_guard fires; fix: pass a callable `traces_inserter: Callable | None` instead of the pool directly |
| A8 | Phase 4 spans table has enough partitions for all test dates | Pitfall 4 | Consumer task fails with partition routing error for dates past 2026-07-31; mitigation documented |

---

## Open Questions (RESOLVED)

1. **`estimated_cost_usd` column on `traces` table**
   - What we know: `TraceListItem` in `docs/api.md` exposes `estimated_cost_usd: float`. The current `traces` DDL (from `0001_initial.py`) does NOT have an `estimated_cost_usd` column.
   - What's unclear: Does D-4.02 add only the three documented columns, or should `estimated_cost_usd` also be added? The `TraceListItem` Pydantic schema requires it, but the column may not exist.
   - Recommendation: Add `estimated_cost_usd REAL NULL` to the 0002 migration. The value is computed in pipeline.py and should be written in the same up-front INSERT or the post-`_emit_root` UPDATE. This is a gap between the locked DDL baseline and the API schema — requires explicit resolution in Plan 1.
   - **RESOLVED:** Plan 04-01 Task 1 (0002 migration) adds `estimated_cost_usd REAL NULL`; Plan 04-01 Task 3 wires the `UPDATE traces SET estimated_cost_usd = $1 WHERE id = $2` in `_llm_text_iter`'s finally block, captured via closure on `trace_id` and verified by integration test asserting all three SQL ops fire.

2. **`feedback_rating` on `TraceListItem` vs. direct join**
   - What we know: `traces.feedback_rating` (D-4.02) is the denormalized copy of the most recent feedback. `GET /traces` reads it from `traces` directly. `POST /feedback` UPDATEs it.
   - What's unclear: If a trace receives multiple feedback events (e.g., user changes vote), the UPDATE overwrites the previous value. Is this the intended behavior?
   - Recommendation: Yes — the UPDATE overwrites. Single-user portfolio scope means this is a non-issue. Phase 5 can add history if needed. Document in feedback.py.
   - **RESOLVED:** Plan 04-04 Task 4 wires the UPDATE inside `async with conn.transaction()` for INSERT+UPDATE atomicity; behavior documented as overwrite-by-design in feedback.py module docstring.

3. **QueryClientProvider already wired in main.tsx?**
   - What we know: Phase 3 PATTERNS.md §"Frontend" lists `frontend/src/lib/queryClient.ts` as a Phase 3 deliverable.
   - What's unclear: The current `frontend/src/main.tsx` file was not read — needs verification.
   - Recommendation: Plan 5 Wave 0 should grep for `QueryClientProvider` in `main.tsx` and add it if missing.
   - **RESOLVED:** Plan 04-05 Task 1 includes a `grep -q "QueryClientProvider" frontend/src/main.tsx` check; if absent, Wave 0 wires it (with `<QueryClientProvider client={queryClient}>` from `frontend/src/lib/queryClient.ts`).

4. **`Select` shadcn component already installed?**
   - What we know: Not confirmed in `frontend/src/components/ui/` glob results.
   - What's unclear: Phase 3 may have installed it for admin form selects.
   - Recommendation: Plan 5 Wave 0 should check and run `npx shadcn@latest add select` if absent.
   - **RESOLVED:** Plan 04-05 Task 1 runs `npx shadcn@latest add tabs table slider tooltip select` (idempotent — shadcn CLI no-ops if a component is already installed); component file presence verified by acceptance criterion `test -f frontend/src/components/ui/select.tsx`.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Postgres 16 + pgvector | All trace persistence | ✓ (Phase 2) | 16.x | — |
| asyncpg pool | Consumer task, traces INSERT | ✓ (Phase 2 lifespan) | 0.29+ | — |
| `collections.deque` | BoundedDropOldestQueue | ✓ (Python stdlib) | Python 3.12 | — |
| `asyncio` | Consumer task, Lock, Event | ✓ (Python stdlib) | Python 3.12 | — |
| `base64`, `json` | Cursor encoding | ✓ (Python stdlib) | Python 3.12 | — |
| `@tanstack/react-query` | Dashboard fetching | ✓ (package.json Phase 2) | 5.x | — |
| `@tremor/react` | KpiCard, AreaChart | ✓ (package.json Phase 2) | 3.x | — |
| `shadcn Tabs, Table, Slider, Tooltip` | Detail page UI | NOT installed | — | Run `npx shadcn@latest add tabs table slider tooltip` in Plan 5 Wave 0 |
| `shadcn Select` | Filter bar | VERIFY | — | Run `npx shadcn@latest add select` if absent |

**Missing dependencies with no fallback:** None — all blocking components are either already present or can be added via CLI.
**Missing dependencies with fallback:** None needed — the `npx shadcn@latest add` commands are the standard install path.

---

## Security Domain

Security enforcement is enabled (`security_enforcement: true`). Phase 4 is single-user local deployment (no auth per V2-AUTH scope trim), but the following ASVS categories apply to the new endpoints.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No — single-user local; V2-AUTH-01 deferred | — |
| V3 Session Management | No — stateless JSON API | — |
| V4 Access Control | No — no auth in v1 | — |
| V5 Input Validation | Yes | Pydantic v2 `extra="forbid"` + `Field(ge=..., le=...)` on `TraceListQuery` |
| V6 Cryptography | No — cursor is opaque but not a security token; base64 is encoding not encryption | — |
| V7 Error Handling | Yes | `ErrorResponse` envelope on all 4xx/5xx; no stack traces in API responses |

### Known Threat Patterns for Phase 4 Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Cursor tampering (invalid base64 or JSON) | Tampering | Try/except around `decode_cursor()`; return 400 `INVALID_REQUEST` |
| Filter injection via ILIKE | Tampering | asyncpg parameterized query `$1`; ILIKE with `$1` is safe (not string concatenation) |
| Large `max_latency_ms` / `limit` DoS | DoS | `Field(ge=1, le=200)` on `limit`; `max_latency_ms: int | None` (no upper bound needed for single-user) |
| Trace ID spoofing in `GET /traces/{trace_id}` | Spoofing | asyncpg UUID type parameter; 404 on miss; no auth needed (single-user) |
| `span_payloads` payload XSS via JSON viewer | Tampering | Frontend renders payload inside `<pre>` block; browser treats content as text; no `dangerouslySetInnerHTML` |
| Consumer task crash silently drops traces | Denial of Service | `asyncio.create_task` has no auto-restart; lifespan should log consumer task exit; Phase 4 does not auto-restart (single-user tolerance) |

**Pre-commit anti-pattern enforcement (D-2.36..D-2.40) — all Phase 4 code must pass:**
- No `gen_ai.system` (use `gen_ai.provider.name`) — `span.py` already enforced
- No `:latest` Docker tags — not a Phase 4 concern (no new Docker images)
- No `class Config:` Pydantic v1 — all new schemas use `ConfigDict(extra="forbid")`
- No `print(...)` in `tracer_ai/` outside `cli/__main__.py` — use `structlog.get_logger()`
- No `from anthropic` outside `rag/llm.py` + `eval/llm_judge.py` — Phase 4 adds no Anthropic calls

---

## Sources

### Primary (HIGH confidence)
- Context7 `/magicstack/asyncpg` — `executemany` semantics, pool acquire pattern, transaction pattern, JSONB handling — [VERIFIED]
- Context7 `/tanstack/query` — `useQuery` queryKey, staleTime, `queryClient.invalidateQueries`, `enabled: false` + `refetch()` pattern — [VERIFIED]
- Context7 `/tremorlabs/tremor` — `AreaChart` data/categories/colors props, `BarChart` comparison — [VERIFIED]
- Context7 `/shadcn-ui/ui` — `Tabs`/`TabsList`/`TabsTrigger`/`TabsContent` composition rules, `Table` components, `Slider`, `Tooltip`, `Badge` variant API, install commands — [VERIFIED]
- `docs/api.md` (project canonical) — `GET /traces`, `GET /traces/{trace_id}` Pydantic schemas, cursor format, error envelope — [VERIFIED]
- `docs/data-model.md` (project canonical) — `traces`, `spans`, `span_payloads` DDL — [VERIFIED]
- `docs/trace-schema.md` (project canonical) — span attribute constants, payload examples — [VERIFIED]
- `docs/wireframes/dashboard-list.md` + `dashboard-detail.md` (project canonical) — component inventory, interaction spec — [VERIFIED]
- `docs/decisions/004-trace-storage.md` + `005-observability-strategy.md` (project canonical) — ADRs constraining implementation — [VERIFIED]
- `tracer_ai/tracer/writer.py` (existing source) — `Span` model with `payload_id` field to remove — [VERIFIED]
- `tracer_ai/rag/pipeline.py` (existing source) — 4-span emission pattern Phase 4 extends — [VERIFIED]
- `tracer_ai/api/lifespan.py` (existing source) — pool construction pattern Phase 4 modifies — [VERIFIED]
- `alembic/versions/0001_initial.py` (existing source) — `op.execute(sa.text(...))` migration pattern — [VERIFIED]

### Secondary (MEDIUM confidence)
- asyncpg official docs (via Context7) — JSONB codec registration pattern
- Postgres 16 documentation (assumed) — `ALTER TABLE ADD COLUMN IF NOT EXISTS`, row-value comparisons on partitioned tables

### Tertiary (LOW confidence)
- `asyncio.Queue` race window under concurrent producers — based on asyncio documentation reasoning; exact failure mode is theoretical for single-producer Phase 4

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already in project; versions verified in CLAUDE.md
- Architecture patterns: HIGH — pre-locked in CONTEXT.md; research confirms implementation mechanics
- asyncpg batch write: HIGH — verified via Context7
- TanStack Query wiring: HIGH — verified via Context7
- shadcn component APIs: HIGH — verified via Context7
- Tremor AreaChart: MEDIUM — verified BarChart; AreaChart props confirmed by same library pattern
- BoundedDropOldestQueue internals: MEDIUM — asyncio.Lock/Event pattern is standard; specific implementation details are [ASSUMED]
- Postgres row-value pagination on partitioned table: MEDIUM — standard Postgres feature; not verified against Postgres 16 docs directly

**Research date:** 2026-05-06
**Valid until:** 2026-06-06 (stable stack; no fast-moving deps)

---

## Project Constraints (from CLAUDE.md)

Per `CLAUDE.md` directives — all Phase 4 code must comply:

| Directive | Scope | Enforcement |
|-----------|-------|-------------|
| Python 3.12+, FastAPI, Pydantic v2 — LOCKED | All backend | No alternatives |
| No `from anthropic` outside `rag/llm.py` + `eval/llm_judge.py` | All backend | Pre-commit hook |
| No `opentelemetry-sdk` runtime dep | All backend | ADR 005; Phase 4 explicitly excluded |
| `ruff` + `mypy --strict` clean | All Python files | Pre-commit hook |
| Pydantic v2: `model_config = ConfigDict(extra="forbid")` | All API schemas | `mypy --strict` |
| No `class Config:` (Pydantic v1) | All Python files | Pre-commit grep |
| No `print(...)` in `tracer_ai/` outside `cli/__main__.py` | All backend | Pre-commit hook |
| No `:latest` Docker image tags | Compose/Dockerfiles | Pre-commit grep |
| No `gen_ai.system` anywhere (deprecated) | All Python + templates | Pre-commit grep |
| Module-deps DAG: `tracer/` must NOT import `api/` | All backend | `import_cycle_guard.py` |
| Vite + React 18 + TypeScript + Tailwind v3 + shadcn/ui — LOCKED | All frontend | `package.json` pins |
| React 18 pinned (`"react": "^18.3.1"`) | Frontend | `package.json` |
| Tailwind v3 pinned (`"tailwindcss": "^3.4.x"`) | Frontend | `package.json` |
| No `axios` — use `ky` or native `fetch` | Frontend | Convention (no hook) |
| Unit tests per adapter + tracer core | All new modules | `pytest` + `pytest-asyncio` |
| Async trace write adds ≤100ms p95 (TRCR-08) | `PostgresTraceWriter` | Benchmark in Plan 6 |
| Trace write must not add > 100ms (async-emit) | Tracer | Verified in Plan 6 |
| Observability of observability: tracer failures must NOT fail user requests | Consumer task | Exception handling in consumer |
| `docker compose up` starts entire stack; seed script ingests Claude docs | Compose | No Phase 4 changes needed |
| Modularity: every external dep behind typed Protocol | Tracer adapters | `TraceWriter` + `TraceStore` Protocols |
