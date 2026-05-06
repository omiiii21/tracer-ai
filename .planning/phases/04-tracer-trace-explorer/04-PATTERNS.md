# Phase 4: Tracer + Trace Explorer — Pattern Map

**Mapped:** 2026-05-06
**Files analyzed:** 27 new/modified files (14 backend + 11 frontend + 2 alembic/test infrastructure)
**Analogs found:** 24 strong / 27 total

Conventions from Phase 3 that EVERY new module must follow (don't repeat per-file):
- Pydantic v2 — `model_config = ConfigDict(extra="forbid")`; never `class Config:`.
- structlog — `log = structlog.get_logger()` at module top; no `print()` inside `tracer_ai/`.
- SDK isolation (D-2.38) — `import anthropic` only in `tracer_ai/rag/llm.py`; `import voyageai` only in `tracer_ai/rag/embedder.py`.
- Import DAG (`config → tracer → rag → eval → api/cli`) enforced by pre-commit.
- mypy `--strict`, `ruff` clean.
- Frontend: `cn()` from `@/lib/utils`; `React.forwardRef` + `displayName` on UI primitives; path alias `@/*` is wired.

---

## File Classification

### Backend new/modified files

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `alembic/versions/0002_traces_denorm.py` | migration | batch (DDL) | `alembic/versions/0001_initial.py` | exact |
| `tracer_ai/tracer/writer.py` (MODIFY) | adapter model | event-driven | self (current writer.py) | exact — field swap |
| `tracer_ai/tracer/exporters/queue.py` | utility | event-driven (async producer/consumer) | none (first async queue) | no analog |
| `tracer_ai/tracer/exporters/postgres.py` (FILL) | adapter (write) | event-driven + batch | `tracer_ai/api/feedback.py` (asyncpg pool pattern) | role-match |
| `tracer_ai/tracer/store.py` (FILL) | repository (read) | CRUD | `tracer_ai/api/health.py` (asyncpg pool + fetchrow) | role-match |
| `tracer_ai/rag/pipeline.py` (MODIFY) | orchestrator | event-driven + CRUD | self (current pipeline.py) | exact — add INSERT + payload |
| `tracer_ai/api/lifespan.py` (MODIFY) | infra/lifecycle | event-driven | self (current lifespan.py) | exact — swap + task |
| `tracer_ai/api/feedback.py` (MODIFY) | controller | request-response | self (current feedback.py) | exact — add UPDATE |
| `tracer_ai/api/main.py` (MODIFY) | app entry | n/a | self (current main.py) | exact — add router |
| `tracer_ai/api/schemas.py` (VERIFY/ADD) | types | n/a | self (current schemas.py) | exact — add trace shapes |
| `tracer_ai/api/traces.py` (NEW) | controller (read) | request-response (cursor pagination) | `tracer_ai/api/feedback.py` | role-match |

### Backend test files

| File | Role | Data Flow | Closest Analog | Match Quality |
|------|------|-----------|----------------|---------------|
| `tests/unit/tracer/test_queue.py` | unit | async | `tests/test_writer_protocol.py` | role-match |
| `tests/unit/tracer/test_postgres_writer.py` | unit | async + batch | `tests/test_feedback_route.py` (_FakePool/_FakeConn pattern) | exact |
| `tests/integration/test_traces_api.py` | integration | request-response | `tests/test_feedback_route.py` | exact |
| `tests/integration/test_pipeline_with_postgres_writer.py` | integration | event-driven | `tests/test_pipeline.py` | exact |
| `tests/perf/test_trace_write_p95.py` | perf benchmark | async | none | no analog |
| `tests/e2e/test_dashboard_flow.py` | e2e (playwright) | browser | none | no analog |

### Frontend new/modified files

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `frontend/src/router.tsx` (MODIFY) | infra | n/a | self (current router.tsx) | exact — add routes |
| `frontend/src/components/AppShell.tsx` (MODIFY) | layout | n/a | self (current AppShell.tsx) | exact — add NavLink |
| `frontend/src/components/MetadataStrip.tsx` (MODIFY) | component | n/a | self (current MetadataStrip.tsx) | exact — change link target |
| `frontend/src/pages/Dashboard.tsx` (NEW) | page | request-response | `frontend/src/pages/Admin.tsx` | exact role |
| `frontend/src/pages/TraceDetail.tsx` (NEW) | page | request-response | `frontend/src/pages/Admin.tsx` | role-match |
| `frontend/src/components/SpanWaterfall.tsx` (NEW) | component | transform | none (first positioned-div chart) | no analog |
| `frontend/src/api/traces.ts` (NEW) | lib (typed client) | request-response | `frontend/src/lib/api.ts` | exact pattern |
| `frontend/src/types/trace.ts` (NEW) | types | n/a | `frontend/src/lib/api.ts` (TS interface block) | exact pattern |

---

## Pattern Assignments

### `alembic/versions/0002_traces_denorm.py` (migration, DDL)

**Analog:** `alembic/versions/0001_initial.py`

**Revision header pattern** (0001_initial.py:1-34):
```python
"""add latency_ms, faithfulness, feedback_rating to traces (Phase 4 D-4.02)

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-06

Never edit 0001_initial.py (D-2.17). This revision is additive-only.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
```

**Core DDL pattern** — raw SQL via `op.execute(sa.text(...))` (0001_initial.py:40-51):
```python
def upgrade() -> None:
    op.execute(sa.text("ALTER TABLE traces ADD COLUMN IF NOT EXISTS latency_ms INT NULL;"))
    op.execute(sa.text("ALTER TABLE traces ADD COLUMN IF NOT EXISTS faithfulness REAL NULL;"))
    op.execute(sa.text("ALTER TABLE traces ADD COLUMN IF NOT EXISTS feedback_rating SMALLINT NULL;"))
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

**Adaptation notes:** Copy the `op.execute(sa.text(...))` raw-SQL pattern verbatim — do NOT use `op.add_column()` (Alembic ORM API doesn't support partitioned parents cleanly). `IF NOT EXISTS` / `IF EXISTS` guards make upgrade/downgrade idempotent.

---

### `tracer_ai/tracer/writer.py` (MODIFY — field swap on `Span`)

**Analog:** self — `tracer_ai/tracer/writer.py` (lines 26-46)

**Current `Span` model** (writer.py:26-46):
```python
class Span(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: UUID
    span_id: UUID
    parent_span_id: UUID | None = None
    name: str
    started_at: datetime
    ended_at: datetime | None = None
    attrs: dict[str, Any] = Field(default_factory=dict)
    payload_id: UUID | None = None   # <-- REMOVE this line (D-4.13)
```

**Phase 4 change:** Remove `payload_id` field; add `payload: dict[str, Any] | None = None` (D-4.11/D-4.13). The `TraceWriter` Protocol (writer.py:48-52) is UNCHANGED — no modification needed there.

**Adaptation notes:** This is a targeted field swap. The `model_config`, all other fields, `TraceWriter` Protocol, `NoopTraceWriter`, and `StdoutTraceWriter` are preserved verbatim. The test `tests/test_writer_protocol.py` constructs `_valid_span()` with `payload_id=None` — update that fixture to use `payload=None` after the field swap.

---

### `tracer_ai/tracer/exporters/queue.py` (NEW — BoundedDropOldestQueue)

**No analog** — first custom async queue in the codebase.

**Full implementation pattern** (from RESEARCH.md Pattern 1, verbatim — this is the canonical D-4.06 shape):
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
        self._dropped_count: int = 0
        self._last_log_at: float = 0.0

    async def put(self, item: Any) -> bool:
        """Returns True if queued, False if an old item was dropped."""
        dropped = False
        async with self._lock:
            if len(self._deque) >= self._maxsize:
                self._deque.popleft()
                self._dropped_count += 1
                dropped = True
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
        while True:
            await self._not_empty.wait()
            async with self._lock:
                if self._deque:
                    item = self._deque.popleft()
                    if not self._deque:
                        self._not_empty.clear()
                    return item

    def qsize(self) -> int:
        return len(self._deque)
```

**Adaptation notes:** `_not_empty.clear()` MUST happen under the lock AFTER confirming the deque is empty — the lock-release ordering is load-bearing for correctness. The `structlog` logger follows the shared pattern from `tracer_ai/api/health.py:23`.

---

### `tracer_ai/tracer/exporters/postgres.py` (FILL — PostgresTraceWriter + SpanConsumer)

**Analog:** `tracer_ai/api/feedback.py` for the asyncpg pool + transaction pattern; `tracer_ai/api/lifespan.py` for the `asyncio.Task` lifecycle pattern.

**Module preamble + structlog** (health.py:1-23 idiom):
```python
"""Postgres+JSONB trace exporter (TRCR-06). Fills Phase 2 stub."""

from __future__ import annotations

import asyncio
import json
import time
from typing import TYPE_CHECKING

import asyncpg
import structlog

from tracer_ai.tracer.writer import Span

if TYPE_CHECKING:
    from tracer_ai.tracer.exporters.queue import BoundedDropOldestQueue

log = structlog.get_logger()

_BATCH_SIZE = 50
_FLUSH_INTERVAL = 0.250  # seconds (D-4.09)
```

**PostgresTraceWriter class** — satisfies `TraceWriter` Protocol (writer.py:48-52):
```python
class PostgresTraceWriter:
    """Enqueues spans to BoundedDropOldestQueue; consumer flushes to Postgres."""

    def __init__(self, queue: "BoundedDropOldestQueue") -> None:
        self._queue = queue

    async def emit(self, span: Span) -> None:
        await self._queue.put(span)
```

**SpanConsumer.run() loop** — batch flush logic (RESEARCH.md Pattern 2):
```python
async def run(self) -> None:
    batch: list[Span] = []
    batch_started_at: float = time.monotonic()
    while True:
        elapsed = time.monotonic() - batch_started_at
        remaining = max(0.0, _FLUSH_INTERVAL - elapsed)
        try:
            span = await asyncio.wait_for(self._queue.get(), timeout=remaining)
            batch.append(span)
        except asyncio.TimeoutError:
            pass
        should_flush = (
            len(batch) >= _BATCH_SIZE
            or (batch and time.monotonic() - batch_started_at >= _FLUSH_INTERVAL)
        )
        if should_flush and batch:
            await self._flush(batch)
            batch = []
            batch_started_at = time.monotonic()
```

**SpanConsumer._flush() asyncpg executemany** — INSERT pattern from feedback.py:41-51 extended to executemany:
```python
async def _flush(self, spans: list[Span]) -> None:
    span_rows = [
        (str(s.span_id), str(s.trace_id),
         str(s.parent_span_id) if s.parent_span_id else None,
         s.name, s.started_at, s.ended_at,
         json.dumps(s.attrs))          # explicit json.dumps for jsonb
        for s in spans
    ]
    payload_rows = [
        (str(s.span_id), json.dumps(s.payload))
        for s in spans if s.payload is not None
    ]
    root_spans = [s for s in spans if s.parent_span_id is None and s.name == "rag.request"]
    async with self._pool.acquire() as conn:  # feedback.py:42 idiom
        await conn.executemany(
            "INSERT INTO spans (id, trace_id, parent_span_id, name, started_at, ended_at, attrs) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7) ON CONFLICT (id, started_at) DO NOTHING",
            span_rows,
        )
        if payload_rows:
            await conn.executemany(
                "INSERT INTO span_payloads (span_id, payload) VALUES ($1, $2) "
                "ON CONFLICT (span_id) DO NOTHING",
                payload_rows,
            )
        for root in root_spans:
            latency = root.attrs.get("rag.latency_ms")
            if latency is not None:
                await conn.execute(
                    "UPDATE traces SET latency_ms = $1 WHERE id = $2",
                    int(latency), str(root.trace_id),
                )
```

**Adaptation notes:** `attrs` must be `json.dumps(s.attrs)` (string), not a raw dict — asyncpg JSONB dict-direct requires codec registration which is not configured in this stack. The `async with self._pool.acquire()` pattern is from `feedback.py:42`; do NOT use `pool.acquire(timeout=...)` in the consumer (batch flushes are not time-critical; blocking is acceptable). `span_payloads` INSERT must come AFTER `spans` INSERT (application-layer ordering per D-4.11; no FK constraint at DDL level).

---

### `tracer_ai/tracer/store.py` (FILL — TraceStore Protocol + PostgresTraceStore)

**Analog:** `tracer_ai/api/health.py` for asyncpg `pool.acquire()` + `fetchrow`/`fetch`; `tracer_ai/tracer/writer.py` for the Protocol shape.

**TraceStore Protocol** — mirrors `TraceWriter` Protocol shape (writer.py:48-52):
```python
from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

import asyncpg
import structlog

log = structlog.get_logger()


class TraceStore(Protocol):
    """Read-side persistence abstraction for traces (TRCR-05)."""

    async def get_trace(self, trace_id: UUID) -> dict[str, Any] | None: ...
    async def list_traces(
        self, *, filters: dict[str, Any], cursor: str | None, limit: int
    ) -> dict[str, Any]: ...
```

**PostgresTraceStore two-query pattern** — GET /traces/{trace_id} (RESEARCH.md Pattern 6):
```python
class PostgresTraceStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def get_trace(self, trace_id: UUID) -> dict[str, Any] | None:
        async with self._pool.acquire() as conn:  # health.py:46 idiom
            trace_row = await conn.fetchrow(
                "SELECT id, started_at, ended_at, query_text, latency_ms, "
                "faithfulness, feedback_rating FROM traces WHERE id = $1",
                str(trace_id),
            )
            if trace_row is None:
                return None
            span_rows = await conn.fetch(
                "SELECT s.id, s.parent_span_id, s.name, s.started_at, s.ended_at, "
                "s.attrs, sp.payload "
                "FROM spans s LEFT JOIN span_payloads sp ON sp.span_id = s.id "
                "WHERE s.trace_id = $1 ORDER BY s.started_at ASC",
                str(trace_id),
            )
        return {"trace": dict(trace_row), "spans": [dict(r) for r in span_rows]}
```

**list_traces cursor pattern** (RESEARCH.md Pattern 5 — encode/decode):
```python
import base64, json
from datetime import datetime

def encode_cursor(started_at: datetime, trace_id: UUID) -> str:
    payload = {"started_at": started_at.isoformat(), "id": str(trace_id)}
    return base64.b64encode(json.dumps(payload).encode()).decode()

def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    payload = json.loads(base64.b64decode(cursor).decode())
    return datetime.fromisoformat(payload["started_at"]), UUID(payload["id"])
```

**Adaptation notes:** `conn.fetchrow` returns `asyncpg.Record | None` — the `if trace_row is None` guard (feedback.py:53-55 pattern) is mandatory for type narrowing. `dict(trace_row)` converts asyncpg Record to plain dict for Pydantic model construction. JSONB `attrs` columns are returned as Python `dict` automatically by asyncpg (verified in RESEARCH.md).

---

### `tracer_ai/rag/pipeline.py` (MODIFY — up-front INSERT + payload= + latency UPDATE)

**Analog:** self — `tracer_ai/rag/pipeline.py`

**Up-front traces INSERT** — add `db_pool: asyncpg.Pool | None = None` to `Pipeline.__init__` (pipeline.py:109-118 shape):
```python
def __init__(
    self,
    embedder: Embedder,
    retriever: Retriever,
    llm: LLMProtocol,
    writer: TraceWriter,
    *,
    top_k: int = 5,
    db_pool: asyncpg.Pool | None = None,   # NEW (D-4.01/RESEARCH Pattern 7)
) -> None:
    ...
    self._db_pool = db_pool
```

**In `_orchestrate`, before `embedder.embed_batch`** (pipeline.py:160-161 insertion point):
```python
# D-4.01: up-front INSERT before embed_batch (FK target must exist before spans insert)
if self._db_pool is not None:
    async with self._db_pool.acquire(timeout=2.0) as conn:
        await conn.execute(
            "INSERT INTO traces (id, started_at, query_text, root_span_id) "
            "VALUES ($1, $2, $3, $4) ON CONFLICT (id) DO NOTHING",
            str(trace_id), root_started, query[:4000], str(root_span_id),
        )
```

**payload= arg on each Span constructor** — existing Span(...) calls (pipeline.py:188-196 shape):
```python
# Before (Phase 3):
await self.writer.emit(
    Span(trace_id=trace_id, span_id=retrieve_span_id, ..., attrs=retrieve_attrs)
)
# After (Phase 4 D-4.11/D-4.12):
await self.writer.emit(
    Span(
        trace_id=trace_id, span_id=retrieve_span_id, ...,
        attrs=retrieve_attrs,
        payload={"retrieved_chunks": [
            {"chunk_id": str(c.id), "content": c.content,
             "score": c.score, "doc_id": c.doc_id, "doc_section": c.doc_section}
            for c in chunks
        ]},
    )
)
```

**`_emit_root` UPDATE latency_ms** — add after `writer.emit` call (pipeline.py:288-314 area):
```python
async def _emit_root(self, trace_id, root_span_id, root_started, root_attrs, t0):
    latency_ms = int((time.perf_counter() - t0) * 1000)
    root_attrs[_ATTR_LATENCY_MS] = latency_ms
    await self.writer.emit(Span(...))  # existing line
    # Phase 4 addition (D-4.03/RESEARCH Pattern 8):
    if self._db_pool is not None:
        async with self._db_pool.acquire(timeout=2.0) as conn:
            await conn.execute(
                "UPDATE traces SET latency_ms = $1, ended_at = $2 WHERE id = $3",
                latency_ms, _now(), str(trace_id),
            )
    log.info("pipeline_run_complete", ...)  # existing line
```

**Adaptation notes:** `payload=` for `rag.request` (root span) is `None` per D-4.11 spec. `payload=` for `rag.prompt_assemble` carries `{"messages": [...], "prompt_template_id": "..."}`. `payload=` for `rag.llm_call` is captured inside `_llm_text_iter()` after the LLM final event (access `final_event.result`). Follow the existing try/finally span-emit-on-cancel pattern (pipeline.py:172-199) — do NOT move `payload=` outside the `finally` block.

---

### `tracer_ai/api/lifespan.py` (MODIFY — swap writer + consumer task)

**Analog:** self — `tracer_ai/api/lifespan.py` (entire file)

**New imports** (add to existing import block, lifespan.py:25-40):
```python
from tracer_ai.tracer.exporters.postgres import PostgresTraceWriter, SpanConsumer
from tracer_ai.tracer.exporters.queue import BoundedDropOldestQueue
```

**Swap NoopTraceWriter → PostgresTraceWriter** — replace lifespan.py:110 area:
```python
# Before (Phase 3, lifespan.py:110):
writer: TraceWriter = NoopTraceWriter()

# After (Phase 4, RESEARCH Pattern 3):
_queue = BoundedDropOldestQueue(maxsize=1000)
writer: TraceWriter = PostgresTraceWriter(queue=_queue)
consumer = SpanConsumer(queue=_queue, pool=pool)
consumer_task = asyncio.create_task(consumer.run(), name="tracer-consumer")
app.state.consumer = consumer
app.state.consumer_task = consumer_task
```

**Shutdown drain** — replace the existing `finally` block (lifespan.py:125-129):
```python
try:
    yield
finally:
    # D-4.10: 5s drain before pool close
    consumer.stop_accepting = True
    try:
        await asyncio.wait_for(consumer.drain(), timeout=5.0)
    except asyncio.TimeoutError:
        log.warning("tracer.shutdown_drain_incomplete", remaining=_queue.qsize())
    consumer_task.cancel()
    try:
        await consumer_task
    except asyncio.CancelledError:
        pass
    await app.state.db_pool.close()
    log.info("db_pool_closed")
```

**Pass db_pool to Pipeline** — update the Pipeline constructor call (lifespan.py:115):
```python
# Before:
app.state.pipeline = Pipeline(embedder, retriever, llm, writer, top_k=5)
# After:
app.state.pipeline = Pipeline(embedder, retriever, llm, writer, top_k=5, db_pool=pool)
```

**Adaptation notes:** `asyncio.create_task` must be called INSIDE the `async with` lifespan block (after the pool exists). The consumer task is started even inside the `try` block that wraps pipeline construction — it belongs to pool lifecycle, not pipeline lifecycle.

---

### `tracer_ai/api/feedback.py` (MODIFY — add UPDATE traces SET feedback_rating)

**Analog:** self — `tracer_ai/api/feedback.py` (entire file, lines 33-61)

**Current pattern** (feedback.py:41-55):
```python
pool: asyncpg.Pool = request.app.state.db_pool
async with pool.acquire(timeout=1.0) as conn:
    row = await conn.fetchrow(
        "INSERT INTO feedback (trace_id, rating, comment, diagnosis_tag) "
        "VALUES ($1, $2, $3, $4) RETURNING id, created_at",
        body.trace_id, body.rating, body.comment, body.diagnosis_tag,
    )
```

**Phase 4 replacement** — wrap in explicit transaction (RESEARCH.md Pattern 9):
```python
async with pool.acquire(timeout=1.0) as conn:
    async with conn.transaction():   # atomic INSERT + UPDATE
        row = await conn.fetchrow(
            "INSERT INTO feedback (trace_id, rating, comment, diagnosis_tag) "
            "VALUES ($1, $2, $3, $4) RETURNING id, created_at",
            body.trace_id, body.rating, body.comment, body.diagnosis_tag,
        )
        await conn.execute(           # D-4.03: denorm update
            "UPDATE traces SET feedback_rating = $1 WHERE id = $2",
            body.rating, body.trace_id,
        )
```

**Adaptation notes:** `async with conn.transaction()` is the canonical asyncpg pattern (verified Context7). The UPDATE is a best-effort denorm write — if `trace_id` FK is absent (orphan feedback per T-03-06-07), the UPDATE is a no-op (0 rows affected is not an error). Keep the existing `if row is None: raise RuntimeError(...)` guard unchanged.

---

### `tracer_ai/api/main.py` (MODIFY — add traces router)

**Analog:** self — `tracer_ai/api/main.py` (lines 35-40)

**Current import + register block** (main.py:35-40):
```python
from tracer_ai.api import admin, chat, feedback, health  # noqa: E402

app.include_router(health.router)
app.include_router(chat.router)
app.include_router(feedback.router)
app.include_router(admin.router)
```

**Phase 4 addition** — add `traces` to both lines:
```python
from tracer_ai.api import admin, chat, feedback, health, traces  # noqa: E402

app.include_router(health.router)
app.include_router(chat.router)
app.include_router(feedback.router)
app.include_router(admin.router)
app.include_router(traces.router)
```

**Adaptation notes:** Order of `include_router` calls has no runtime effect. Add `traces` at the end to minimize diff.

---

### `tracer_ai/api/schemas.py` (VERIFY/ADD — trace list + detail shapes)

**Analog:** self — `tracer_ai/api/schemas.py` (existing models, e.g., `FeedbackResponse` lines 99-105 and `IngestStatus` lines 205-218)

**TraceListItem** — follows the `extra="forbid"` pattern (schemas.py:27-32 shape):
```python
class TraceListItem(BaseModel):
    """One row in GET /traces response (docs/api.md §4)."""
    model_config = ConfigDict(extra="forbid")

    trace_id: UUID
    started_at: datetime
    query_text: str
    latency_ms: int | None = None
    faithfulness: float | None = None
    feedback_rating: Literal[-1, 1] | None = None
```

**TraceListResponse** — cursor pagination envelope:
```python
class TraceListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[TraceListItem]
    next_cursor: str | None = None
    total: int | None = None
```

**SpanInResponse** — per-span shape in detail response:
```python
class SpanInResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    span_id: UUID
    parent_span_id: UUID | None = None
    name: str
    started_at: datetime
    ended_at: datetime | None = None
    attrs: dict[str, Any]
    payload: dict[str, Any] | None = None
```

**TraceDetailResponse**:
```python
class TraceDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace: TraceListItem
    spans: list[SpanInResponse]
```

**Adaptation notes:** `feedback_rating: Literal[-1, 1] | None` mirrors the DB CHECK constraint (alembic 0001:127 — same cross-layer integrity pattern as `FeedbackRequest.rating`). `payload` field on `SpanInResponse` must be `dict[str, Any] | None` (not a typed union) per D-4.11.

---

### `tracer_ai/api/traces.py` (NEW — GET /traces + GET /traces/{trace_id})

**Analog:** `tracer_ai/api/feedback.py` — exact role + data flow match for the asyncpg pool DI pattern and router/endpoint shape.

**Module preamble + router** (feedback.py:19-30 shape):
```python
"""GET /traces + GET /traces/{trace_id} — trace explorer read endpoints (EXPL-01/02)."""

from __future__ import annotations

import asyncpg
import structlog
from fastapi import APIRouter, HTTPException, Query, Request

from tracer_ai.api.schemas import TraceDetailResponse, TraceListResponse
from tracer_ai.tracer.store import PostgresTraceStore  # read-side

log = structlog.get_logger()
router = APIRouter()
```

**GET /traces** — pool DI + single-table query (health.py:44-47 DI pattern):
```python
@router.get("/traces", response_model=TraceListResponse)
async def list_traces(
    request: Request,
    query: str | None = Query(default=None),
    since: str | None = Query(default=None),
    until: str | None = Query(default=None),
    feedback: str | None = Query(default=None),
    min_faithfulness: float | None = Query(default=None),
    max_latency_ms: int | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> TraceListResponse:
    pool: asyncpg.Pool = request.app.state.db_pool   # health.py:44 idiom
    store = PostgresTraceStore(pool)
    ...
```

**GET /traces/{trace_id}** — 404 error envelope (health.py:48-51 error shape):
```python
@router.get("/traces/{trace_id}", response_model=TraceDetailResponse)
async def get_trace(trace_id: str, request: Request) -> TraceDetailResponse:
    pool: asyncpg.Pool = request.app.state.db_pool
    store = PostgresTraceStore(pool)
    result = await store.get_trace(UUID(trace_id))
    if result is None:
        raise HTTPException(status_code=404, detail={"error_code": "TRACE_NOT_FOUND"})
    ...
```

**Adaptation notes:** `UUID(trace_id)` will raise `ValueError` on malformed UUIDs — wrap in `try/except ValueError` and raise `HTTPException(400)`. The `TraceStore` is instantiated per-request (cheap dataclass with pool ref). All filter composition follows RESEARCH.md Pattern 5 SQL.

---

### `tests/unit/tracer/test_queue.py` (NEW — BoundedDropOldestQueue unit tests)

**Analog:** `tests/test_writer_protocol.py` for async unit test shape; `tests/test_feedback_route.py` for fixture + `_configured_env` pattern.

**Module preamble + async fixture** (test_writer_protocol.py:1-28 shape):
```python
"""Unit tests for BoundedDropOldestQueue (Phase 4 D-4.06/TRCR-06)."""

from __future__ import annotations

import asyncio
import pytest


@pytest.mark.asyncio
async def test_put_returns_true_when_queue_has_space() -> None:
    from tracer_ai.tracer.exporters.queue import BoundedDropOldestQueue
    q = BoundedDropOldestQueue(maxsize=3)
    result = await q.put("item")
    assert result is True
    assert q.qsize() == 1


@pytest.mark.asyncio
async def test_put_drops_oldest_and_returns_false_when_full() -> None:
    from tracer_ai.tracer.exporters.queue import BoundedDropOldestQueue
    q = BoundedDropOldestQueue(maxsize=2)
    await q.put("first")
    await q.put("second")
    result = await q.put("third")   # drops "first"
    assert result is False
    assert q.qsize() == 2
    item = await q.get()
    assert item == "second"         # oldest remaining
```

**Adaptation notes:** Tests must be `@pytest.mark.asyncio` (pytest-asyncio already in stack). No `monkeypatch` or `_configured_env` needed — queue has no env dependency. Test the rate-limited logging by patching `time.monotonic` or injecting a fake clock.

---

### `tests/unit/tracer/test_postgres_writer.py` (NEW)

**Analog:** `tests/test_feedback_route.py` — exact `_FakePool` / `_FakeConn` / `_FakeAcquireCtx` + recorder pattern.

**FakePool pattern** (test_feedback_route.py:35-67):
```python
class _FakeConn:
    def __init__(self, recorder: list[tuple[str, tuple[Any, ...]]]) -> None:
        self._recorder = recorder

    async def executemany(self, query: str, args: list[tuple[Any, ...]]) -> None:
        self._recorder.append(("executemany", query, args))

    async def execute(self, query: str, *args: Any) -> None:
        self._recorder.append(("execute", query, args))

    def transaction(self) -> "_FakeTxn":
        return _FakeTxn()


class _FakeAcquireCtx:
    def __init__(self, recorder: list[tuple[str, ...]]) -> None:
        self._recorder = recorder

    async def __aenter__(self) -> _FakeConn:
        return _FakeConn(self._recorder)

    async def __aexit__(self, *exc: Any) -> None:
        return None


class _FakePool:
    def __init__(self) -> None:
        self.executed: list[tuple[str, ...]] = []

    def acquire(self, timeout: float = 1.0) -> _FakeAcquireCtx:
        return _FakeAcquireCtx(self.executed)
```

**Adaptation notes:** Test that `_flush` calls `executemany` with `"INSERT INTO spans"` first, then `"INSERT INTO span_payloads"` second (application-layer ordering). Test that `latency_ms` UPDATE fires only when root span with `rag.latency_ms` attr is in the batch.

---

### `tests/integration/test_traces_api.py` (NEW)

**Analog:** `tests/test_feedback_route.py` — exact `_build_app` + `TestClient` + `_configured_env` pattern.

**_build_app fixture** (test_feedback_route.py:69-78):
```python
def _build_app(pool: Any) -> Any:
    from fastapi import FastAPI
    from tracer_ai import __version__
    from tracer_ai.api import traces

    app = FastAPI(title="tracer-ai-test", version=__version__)
    app.state.db_pool = pool
    app.include_router(traces.router)
    return app
```

**Test shape for GET /traces/:
```python
def test_list_traces_returns_200_with_empty_items() -> None:
    from fastapi.testclient import TestClient
    pool = _FakePool()  # fetchrow returns None; fetch returns []
    app = _build_app(pool)
    client = TestClient(app)
    resp = client.get("/traces")
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert isinstance(body["items"], list)
```

**Adaptation notes:** The `_FakeConn` for traces.py needs `fetch` (not `fetchrow`) for the list endpoint. Add `_configured_env` autouse fixture identical to test_feedback_route.py:22-29 (monkeypatch env vars + sys.modules.pop).

---

### `tests/integration/test_pipeline_with_postgres_writer.py` (NEW)

**Analog:** `tests/test_pipeline.py` — `_CapturingWriter` + `_FakeEmbedder` + `_FakeRetriever` + `_FakeLLM` stubs.

**_CapturingWriter from test_pipeline.py:39-47** (copy verbatim):
```python
class _CapturingWriter:
    def __init__(self) -> None:
        from tracer_ai.tracer.writer import Span
        self.spans: list[Span] = []

    async def emit(self, span: Any) -> None:
        self.spans.append(span)
```

**Adaptation notes:** Phase 4 integration test additionally checks that `span.payload` is populated for `rag.retrieve`, `rag.prompt_assemble`, `rag.llm_call` spans, and is `None` for `rag.request`. Test that `db_pool.acquire()` was called twice (once for up-front INSERT, once for latency UPDATE) using a recorder-equipped `_FakePool`.

---

## Pattern Assignments — Frontend

### `frontend/src/router.tsx` (MODIFY — add /dashboard routes)

**Analog:** self — `frontend/src/router.tsx` (entire file)

**Current file** (router.tsx:1-17):
```tsx
import { createBrowserRouter, Navigate } from "react-router-dom";
import { AppShell } from "@/components/AppShell";
import { Chat } from "@/pages/Chat";
import { Admin } from "@/pages/Admin";
import { TraceStub } from "@/pages/TraceStub";

export const router = createBrowserRouter([
  { path: "/", element: <Navigate to="/chat" replace /> },
  {
    element: <AppShell />,
    children: [
      { path: "/chat", element: <Chat /> },
      { path: "/admin", element: <Admin /> },
    ],
  },
  { path: "/traces/:trace_id", element: <TraceStub /> },
]);
```

**Phase 4 replacement:**
```tsx
import { Dashboard } from "@/pages/Dashboard";
import { TraceDetail } from "@/pages/TraceDetail";
// Remove: TraceStub import (file deleted per D-4.17)

export const router = createBrowserRouter([
  { path: "/", element: <Navigate to="/chat" replace /> },
  {
    element: <AppShell />,
    children: [
      { path: "/chat", element: <Chat /> },
      { path: "/admin", element: <Admin /> },
      { path: "/dashboard", element: <Dashboard /> },
      { path: "/dashboard/traces/:trace_id", element: <TraceDetail /> },
    ],
  },
  // Remove: /traces/:trace_id route
]);
```

**Adaptation notes:** `/dashboard` and `/dashboard/traces/:trace_id` are placed INSIDE the `AppShell` children so they inherit the nav header. The old `/traces/:trace_id` (outside AppShell) is removed. `TraceStub.tsx` is deleted after this change.

---

### `frontend/src/components/AppShell.tsx` (MODIFY — add Dashboard NavLink)

**Analog:** self — `frontend/src/components/AppShell.tsx` (lines 22-38)

**Existing NavLink pattern** (AppShell.tsx:17-38):
```tsx
<NavLink
  to="/chat"
  className={({ isActive }) =>
    cn(
      isActive
        ? "font-medium text-foreground"
        : "text-muted-foreground hover:text-foreground",
    )
  }
>
  Chat
</NavLink>
```

**Phase 4 addition** — copy the NavLink shape verbatim, changing `to` and label:
```tsx
<NavLink
  to="/dashboard"
  className={({ isActive }) =>
    cn(
      isActive
        ? "font-medium text-foreground"
        : "text-muted-foreground hover:text-foreground",
    )
  }
>
  Dashboard
</NavLink>
```

**Adaptation notes:** Insert between `Chat` and `Admin` NavLinks. The `isActive` pattern and `cn()` usage are load-bearing — copy exactly.

---

### `frontend/src/components/MetadataStrip.tsx` (MODIFY — update "View trace" link target)

**Analog:** self — `frontend/src/components/MetadataStrip.tsx` (line 37)

**Current link** (MetadataStrip.tsx:36-40):
```tsx
<Link
  to={`/traces/${traceId}`}
  className="hover:underline ml-auto"
>
  trace ↗
```

**Phase 4 replacement** (D-4.17):
```tsx
<Link
  to={`/dashboard/traces/${traceId}`}
  className="hover:underline ml-auto"
>
  trace ↗
```

**Adaptation notes:** One-line change. The `className` and `sr-only` span are unchanged.

---

### `frontend/src/pages/Dashboard.tsx` (NEW — trace list page)

**Analog:** `frontend/src/pages/Admin.tsx` — exact role (TanStack Query page with Tremor KPI cards + shadcn Table)

**Page structure** (Admin.tsx:21-40 shape):
```tsx
import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { AreaChart, Card, Metric, Text, Title } from "@tremor/react";
import { useNavigate } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { getTraces, type TraceListResponse } from "@/api/traces";

export function Dashboard(): React.ReactElement {
  const [filters, setFilters] = React.useState<Record<string, string>>({});
  const { data, isLoading, isError } = useQuery<TraceListResponse, Error>({
    queryKey: ["traces", filters],
    queryFn: () => getTraces(filters),
    staleTime: 0,   // D-4.18: always re-fetch (real-time dashboard)
  });

  if (isLoading) {
    return (
      <div className="max-w-7xl mx-auto p-8 space-y-6">
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
        {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-32 w-full" />)}
      </div>
    );
  }
  ...
}
```

**Tremor KPI card pattern** (CorpusCards.tsx:25-34 shape — use identical Card/Title/Metric/Text):
```tsx
// Copy from CorpusCards.tsx:25-34
<Card>
  <Title>TRACES</Title>
  <Metric>{data?.items.length ?? 0}</Metric>
  <Text>in current view</Text>
</Card>
```

**shadcn Table with navigate** (RESEARCH.md Pattern 13):
```tsx
const navigate = useNavigate();
<TableRow
  key={item.trace_id}
  onClick={() => navigate(`/dashboard/traces/${item.trace_id}`)}
  className="cursor-pointer hover:bg-muted/50"
>
  <TableCell>...</TableCell>
</TableRow>
```

**Adaptation notes:** The loading/error states follow Admin.tsx:29-60 exactly — `isLoading` shows Skeleton grid; `isError` shows a `Card` with `border-rose-300 bg-rose-50`. `staleTime: 0` is the only deviation from the queryClient default (`staleTime: 30_000`). The Tremor `AreaChart` for the mini quality-drift chart will have empty data in Phase 4 (no faithfulness values) — pass an empty array and let Tremor render the empty chart gracefully.

---

### `frontend/src/pages/TraceDetail.tsx` (NEW — trace detail page with Tabs)

**Analog:** `frontend/src/pages/Admin.tsx` for TanStack Query + loading/error shell; `frontend/src/pages/TraceStub.tsx` for `useParams<{ trace_id: string }>()` + back-link pattern.

**useParams + useQuery pattern** (TraceStub.tsx:10 + Admin.tsx:23-27):
```tsx
import { useParams, Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { SpanWaterfall } from "@/components/SpanWaterfall";
import { getTrace, type TraceDetailResponse } from "@/api/traces";

export function TraceDetail(): React.ReactElement {
  const { trace_id } = useParams<{ trace_id: string }>();
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery<TraceDetailResponse, Error>({
    queryKey: ["trace", trace_id],
    queryFn: () => getTrace(trace_id!),
  });
```

**Back-link pattern** (TraceStub.tsx:13-16):
```tsx
<Link
  to="/dashboard"
  className="text-sm text-muted-foreground hover:underline mb-4 inline-block"
>
  ← Back to dashboard
</Link>
```

**Tabs wiring** (RESEARCH.md Pattern 13):
```tsx
<Tabs defaultValue="spans">
  <TabsList>
    <TabsTrigger value="spans">Spans</TabsTrigger>
    <TabsTrigger value="payloads">Payloads</TabsTrigger>
    <TabsTrigger value="feedback">Feedback</TabsTrigger>
  </TabsList>
  <TabsContent value="spans">
    {data && (
      <SpanWaterfall
        spans={data.spans}
        root_duration_ms={data.trace.latency_ms ?? 1000}
      />
    )}
  </TabsContent>
  <TabsContent value="payloads">
    {data?.spans.filter(s => s.payload).map(s => (
      <div key={s.span_id}>
        <p className="text-xs font-mono font-semibold mb-1">{s.name}</p>
        <pre className="text-xs font-mono bg-muted p-2 rounded overflow-auto">
          {JSON.stringify(s.payload, null, 2)}
        </pre>
      </div>
    ))}
  </TabsContent>
</Tabs>
```

**One-shot eval-pending refetch** (D-4.18, RESEARCH.md Pattern 11):
```tsx
const evalSpan = data?.spans.find(s => s.name === "rag.eval");
const evalPending = evalSpan && !evalSpan.ended_at;
React.useEffect(() => {
  if (!evalPending) return;
  const timer = setTimeout(() => {
    queryClient.invalidateQueries({ queryKey: ["trace", trace_id] });
  }, 5000);
  return () => clearTimeout(timer);
}, [evalPending, trace_id, queryClient]);
```

**Adaptation notes:** In Phase 4, `rag.eval` spans never exist — the `useEffect` is a no-op but forward-compatible. The Payloads tab `<pre>` JSON viewer is intentionally unstyled per D-4.11 (raw JSONB; no typed schema).

---

### `frontend/src/components/SpanWaterfall.tsx` (NEW — hand-rolled waterfall)

**No close analog** — first positioned-div visualization component. The closest structural analog is the `cn()` + conditional style composition in `frontend/src/components/MessageBubble.tsx`.

**TypeScript interface** (RESEARCH.md Pattern 10):
```tsx
interface WaterfallSpan {
  span_id: string;
  parent_span_id: string | null;
  name: string;
  started_at: string;    // ISO8601
  ended_at: string | null;
  attrs: Record<string, unknown>;
}

interface SpanWaterfallProps {
  spans: WaterfallSpan[];
  root_duration_ms: number;
}
```

**Bar rendering math** (RESEARCH.md Pattern 10):
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
      <span className="font-mono text-xs text-muted-foreground w-36 shrink-0 pl-2">
        {span.name}
      </span>
      <div className="relative flex-1 h-4 bg-muted/30 rounded-sm mx-2">
        <div
          className="absolute h-full bg-blue-500 rounded-sm"
          style={{ left: `${leftPct}%`, width: `max(4px, ${widthPct}%)` }}
        />
      </div>
      <span className="text-xs text-muted-foreground w-16 text-right pr-2 shrink-0">
        {durationMs}ms
      </span>
    </div>
  );
}
```

**Click-to-expand attrs** — `useState<Set<string>>` for expanded span IDs:
```tsx
const [expanded, setExpanded] = React.useState<Set<string>>(new Set());
// On click: setExpanded(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; })
// When expanded: render <pre className="text-xs font-mono bg-muted p-2 rounded overflow-auto">{JSON.stringify(span.attrs, null, 2)}</pre>
```

**rag.eval forward-compat** (D-4.16): filter with `spans.filter(s => s.name !== "rag.eval" || !s.ended_at === false)` — in Phase 4 `rag.eval` never appears so waterfall always shows 4 rows.

**Adaptation notes:** `style={{ width: \`max(4px, ${widthPct}%)\` }}` — the `max()` CSS function is load-bearing (ensures very-fast spans are visible). The component does NOT use `React.forwardRef` (it's not a primitive UI element), but does use `React.useState` and accepts `className` via `cn()` if the container div needs an override.

---

### `frontend/src/api/traces.ts` (NEW — typed API client for /traces)

**Analog:** `frontend/src/lib/api.ts` — exact pattern (typed fetch wrappers returning typed shapes)

**Pattern** (api.ts:133-149 shape — copy getCorpus/getIngestStatus idiom):
```typescript
// frontend/src/api/traces.ts
import ky from "ky";   // ky already in package.json (Phase 3 addition)
import type { TraceListResponse, TraceDetailResponse } from "@/types/trace";

export async function getTraces(
  filters: Record<string, string | number | undefined>,
): Promise<TraceListResponse> {
  return ky.get("/traces", {
    searchParams: Object.fromEntries(
      Object.entries(filters).filter(([, v]) => v !== undefined),
    ) as Record<string, string | number>,
  }).json<TraceListResponse>();
}

export async function getTrace(traceId: string): Promise<TraceDetailResponse> {
  return ky.get(`/traces/${traceId}`).json<TraceDetailResponse>();
}

export type { TraceListResponse, TraceDetailResponse };
```

**Adaptation notes:** Phase 3's `lib/api.ts` uses native `fetch`; Phase 4's `api/traces.ts` uses `ky` per D-4.18. The `searchParams` filter strips `undefined` values so optional query params are not sent as `"undefined"` strings. The `api/` directory is NEW in Phase 4 — create `frontend/src/api/` directory alongside the existing `frontend/src/lib/`.

---

### `frontend/src/types/trace.ts` (NEW — TS mirrors of API response shapes)

**Analog:** `frontend/src/lib/api.ts` — the TS interface block pattern (api.ts:5-31 shape)

**Pattern** (api.ts:5-25 ChatFinal/Citation shape):
```typescript
// frontend/src/types/trace.ts
export interface TraceListItem {
  trace_id: string;
  started_at: string;
  query_text: string;
  latency_ms: number | null;
  faithfulness: number | null;
  feedback_rating: 1 | -1 | null;
}

export interface SpanInDetail {
  span_id: string;
  parent_span_id: string | null;
  name: string;
  started_at: string;
  ended_at: string | null;
  attrs: Record<string, unknown>;
  payload: Record<string, unknown> | null;
}

export interface TraceListResponse {
  items: TraceListItem[];
  next_cursor: string | null;
  total: number | null;
}

export interface TraceDetailResponse {
  trace: TraceListItem;
  spans: SpanInDetail[];
}
```

**Adaptation notes:** These are TS mirrors of `tracer_ai/api/schemas.py` at runtime. `attrs` and `payload` are `Record<string, unknown>` (not typed further) per D-4.11. `feedback_rating: 1 | -1 | null` mirrors the Pydantic `Literal[-1, 1] | None`.

---

## Shared Patterns

### Pattern: structlog logger at module top
**Source:** `tracer_ai/api/health.py:23` + `tracer_ai/api/feedback.py:29`
**Apply to:** `tracer_ai/tracer/exporters/queue.py`, `tracer_ai/tracer/exporters/postgres.py`, `tracer_ai/tracer/store.py`, `tracer_ai/api/traces.py`
```python
import structlog
log = structlog.get_logger()
```

### Pattern: Pydantic v2 strict-mode model
**Source:** `tracer_ai/api/health.py:27-33` — `model_config = ConfigDict(extra="forbid")`
**Apply to:** All new schemas in `tracer_ai/api/schemas.py` (`TraceListItem`, `TraceListResponse`, `SpanInResponse`, `TraceDetailResponse`)
```python
from pydantic import BaseModel, ConfigDict
class TraceListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ...
```

### Pattern: asyncpg pool DI from `request.app.state`
**Source:** `tracer_ai/api/health.py:44-47` + `tracer_ai/api/feedback.py:41-42`
**Apply to:** `tracer_ai/api/traces.py` (both endpoints)
```python
pool: asyncpg.Pool = request.app.state.db_pool
async with pool.acquire(timeout=0.5) as conn:
    ...
```

### Pattern: asyncpg explicit transaction for multi-statement atomicity
**Source:** `tracer_ai/api/feedback.py` (Phase 4 modified version, RESEARCH.md Pattern 9)
**Apply to:** `tracer_ai/api/feedback.py` UPDATE + INSERT atomicity
```python
async with conn.transaction():
    row = await conn.fetchrow("INSERT ... RETURNING ...")
    await conn.execute("UPDATE traces SET feedback_rating = $1 WHERE id = $2", ...)
```

### Pattern: FakePool / FakeConn / recorder for unit tests
**Source:** `tests/test_feedback_route.py:35-67` + `tests/test_healthz.py:17-35`
**Apply to:** `tests/unit/tracer/test_postgres_writer.py`, `tests/integration/test_traces_api.py`
```python
class _FakeConn:
    def __init__(self, recorder: list) -> None:
        self._recorder = recorder
    async def executemany(self, query: str, args: list) -> None:
        self._recorder.append(("executemany", query, args))
    async def execute(self, query: str, *args: Any) -> None:
        self._recorder.append(("execute", query, args))
```

### Pattern: _configured_env autouse fixture
**Source:** `tests/test_feedback_route.py:22-29`
**Apply to:** Every new test module that imports `tracer_ai.*` (env vars + `sys.modules.pop`)
```python
@pytest.fixture(autouse=True)
def _configured_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://t:t@db:5432/t")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("VOYAGE_API_KEY", "pa-test")
    sys.modules.pop("tracer_ai.config", None)
    sys.modules.pop("tracer_ai.api.traces", None)  # adjust per module under test
```

### Pattern: TanStack Query page shell (loading + error + data)
**Source:** `frontend/src/pages/Admin.tsx:21-60`
**Apply to:** `frontend/src/pages/Dashboard.tsx`, `frontend/src/pages/TraceDetail.tsx`
```tsx
const { data, isLoading, isError } = useQuery<T, Error>({
  queryKey: ["...", deps],
  queryFn: apiFn,
});
if (isLoading) return <SkeletonLayout />;
if (isError || !data) return <ErrorCard message={error?.message} />;
return <DataView data={data} />;
```

### Pattern: Tremor Card/Title/Metric/Text KPI card
**Source:** `frontend/src/components/CorpusCards.tsx:25-34`
**Apply to:** `frontend/src/pages/Dashboard.tsx` KPI strip
```tsx
import { Card, Metric, Text, Title } from "@tremor/react";
<Card>
  <Title>LABEL</Title>
  <Metric>{value}</Metric>
  <Text>description</Text>
</Card>
```

### Pattern: NavLink with isActive + cn()
**Source:** `frontend/src/components/AppShell.tsx:17-38`
**Apply to:** Dashboard nav entry in `AppShell.tsx`
```tsx
<NavLink
  to="/dashboard"
  className={({ isActive }) =>
    cn(isActive ? "font-medium text-foreground" : "text-muted-foreground hover:text-foreground")
  }
>
  Dashboard
</NavLink>
```

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `tracer_ai/tracer/exporters/queue.py` | utility (async queue) | event-driven | First custom bounded async queue in repo; `asyncio.Queue` was explicitly rejected (D-4.06); RESEARCH.md Pattern 1 is the canonical implementation |
| `frontend/src/components/SpanWaterfall.tsx` | component | transform (visual) | First positioned-div visualization; no chart library covers this shape (D-4.15); RESEARCH.md Pattern 10 is the canonical implementation |
| `tests/perf/test_trace_write_p95.py` | perf benchmark | async | No performance benchmark precedent in repo; requires two pipeline runs (NoopTraceWriter vs PostgresTraceWriter) with p95 delta assertion |
| `tests/e2e/test_dashboard_flow.py` | e2e (playwright) | browser | No existing Playwright test in repo; Phase 3 had no e2e tests |

---

## Metadata

**Analog search scope:** `tracer_ai/`, `frontend/src/`, `alembic/versions/`, `tests/`
**Files scanned:** 22 live source files (11 backend, 7 frontend, 2 alembic, 2 test fixture files)
**Pattern extraction date:** 2026-05-06
**Phase 3 delta:** Phase 3 shipped all the load-bearing patterns Phase 4 extends — asyncpg pool DI (`health.py`, `feedback.py`), `TraceWriter` Protocol + `Span` model (`writer.py`), 4-stage span emission with try/finally (`pipeline.py`), TanStack Query page shell (`Admin.tsx`), Tremor KPI cards (`CorpusCards.tsx`), typed fetch wrappers (`lib/api.ts`). Phase 4 has STRONG analogs for ~89% of files. The three files with no analog (`queue.py`, `SpanWaterfall.tsx`, perf/e2e tests) have verbatim implementation patterns in RESEARCH.md that the planner should reference directly.
