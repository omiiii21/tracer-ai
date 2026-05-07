# Phase 5: Quality Layer + Feedback - Pattern Map

**Mapped:** 2026-05-07
**Files analyzed:** 22 (5 new backend, 1 new migration, 1 new frontend page, 13 modify, 2 new test files implied)
**Analogs found:** 22 / 22

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `tracer_ai/eval/llm_judge.py` (NEW) | Backend / Adapter | producer (calls Anthropic) | `tracer_ai/rag/llm.py` | exact (second `from anthropic` allowlist site) |
| `tracer_ai/eval/dispatcher.py` (NEW) | Backend / Background worker | dispatch site + producer | `tracer_ai/tracer/exporters/postgres.py` (SpanConsumer) | role-match (drain + try/except shape) |
| `tracer_ai/eval/calibrate.py` (NEW) | Backend / CLI | read-only + file producer | `tracer_ai/cli/__main__.py` | role-match (argparse subcommand pattern) |
| `tracer_ai/eval/protocols.py` (NEW) | Backend / Schema | passthrough | `tracer_ai/rag/protocols.py` (LLM Protocol) | exact |
| `tracer_ai/eval/prompts.py` (NEW) | Backend / Utility | passthrough | `tracer_ai/rag/prompt.py` (assemble) | role-match |
| `tracer_ai/tracer/context.py` (MODIFY — fill stub) | Backend / Tracer | passthrough (contextvar holder) | stdlib `contextvars`; in-repo: `tracer_ai/tracer/writer.py` Span model | partial (no exact analog — stub today) |
| `tracer_ai/api/feedback.py` (MODIFY — add PATCH) | Backend / API endpoint | mutation endpoint | existing `POST /feedback` in same file | exact |
| `tracer_ai/api/admin.py` (MODIFY — add GET /admin/eval-config) | Backend / API endpoint | query endpoint | existing GET /admin/corpus in same file | exact |
| `tracer_ai/api/traces.py` (MODIFY — add GET /traces/timeseries) | Backend / API endpoint | query endpoint | existing GET /traces in same file | exact |
| `tracer_ai/api/chat.py` (MODIFY — add ctx-snapshot + dispatch) | Backend / API endpoint | dispatch site | existing SSE generator in same file | exact (extended in place) |
| `tracer_ai/api/lifespan.py` (MODIFY — wire EvalDispatcher) | Backend / Config | dispatch site | existing PostgresTraceWriter wiring + drain | exact |
| `tracer_ai/api/schemas.py` (MODIFY — add 4 schemas) | Backend / Schema | passthrough | existing TraceListItem / FeedbackResponse | exact |
| `tracer_ai/rag/pipeline.py` (MODIFY — return ctx_snapshot) | Backend / Pipeline | producer | existing `_orchestrate` return tuple | exact (extension) |
| `tracer_ai/config.py` (MODIFY — add 4 fields) | Backend / Config | passthrough | existing Settings fields | exact |
| `tracer_ai/cli/__main__.py` (MODIFY — add calibrate subcommand) | Backend / CLI | dispatch site | existing `ingest` subcommand in same file | exact |
| `tracer_ai/tracer/store.py` (MODIFY — add timeseries() + ASC sort) | Backend / Tracer | query endpoint | existing `list_traces` SQL | exact |
| `tracer_ai/tracer/span.py` (MODIFY — add ERROR_TYPE const) | Backend / Schema | passthrough | existing constants | exact |
| `alembic/versions/0003_feedback_resolved.py` (NEW) | Backend / Migration | mutation | `alembic/versions/0002_traces_denorm.py` | exact |
| `frontend/src/pages/Queue.tsx` (NEW) | Frontend / Page | consumer (read-only) | `frontend/src/pages/Dashboard.tsx` | exact |
| `frontend/src/pages/Dashboard.tsx` (MODIFY — live timeseries + 5th KpiCard) | Frontend / Page | consumer | itself (KPI strip + AreaChart placeholder) | exact (in-place extension) |
| `frontend/src/pages/TraceDetail.tsx` (MODIFY — diagnosis-tag Select) | Frontend / Page | mutation client | itself (Feedback tab) | exact |
| `frontend/src/components/AppShell.tsx` (MODIFY — Queue nav link) | Frontend / Component | passthrough | itself (existing nav links) | exact |
| `frontend/src/api/traces.ts` (MODIFY — add 3 fns) | Frontend / API client | passthrough | existing `getTraces` / `getTrace` | exact |
| `frontend/src/types/trace.ts` (MODIFY — add 4 types) | Frontend / Schema | passthrough | existing TraceListItem mirror | exact |
| `frontend/src/router.tsx` (MODIFY — add /dashboard/queue route) | Frontend / Config | passthrough | existing routes | exact |
| `tests/test_llm_judge.py` (NEW — implied) | Tests / Unit | passthrough | `tests/test_llm_adapter.py` | exact (FakeAsyncAnthropic + tool_use shape) |
| `tests/integration/test_eval_dispatcher.py` (NEW — implied) | Tests / Integration | passthrough | `tests/integration/test_lifespan_drain.py` | exact |

---

## Pattern Assignments

### `tracer_ai/eval/llm_judge.py` (Backend / Adapter, producer)

**Analog:** `tracer_ai/rag/llm.py` (lines 1–148)

**Imports + module docstring pattern** (lines 1–38):

```python
"""Anthropic streaming LLM adapter (Phase 3 Plan 05, RAG-03 / CHAT-02).

Per D-2.38 / SDK isolation: this is the ONLY file in tracer_ai/ allowed to
``import anthropic`` (alongside tracer_ai/eval/llm_judge.py in Phase 5).
The anti-pattern test ``tests/test_anti_patterns.py`` enforces this gate via
git-grep at pre-commit time.
"""
from __future__ import annotations
from collections.abc import AsyncIterator
from typing import Any

import structlog
from anthropic import AsyncAnthropic

from tracer_ai.config import settings
from tracer_ai.rag.protocols import LLM
from tracer_ai.rag.types import Final, LLMResult, Message, StreamEvent, TextDelta

log = structlog.get_logger()
```

**SDK-boundary client construction** (lines 69–74):

```python
def __init__(self, name: str | None = None) -> None:
    self.name: str = name or settings.llm_bot_model
    # SDK boundary: unwrap SecretStr exactly once at construction time.
    self._client: AsyncAnthropic = AsyncAnthropic(
        api_key=settings.anthropic_api_key.get_secret_value()
    )
```

**Cost-picker by model name** (lines 41–59) — Phase 5 reuses this same `_cost_per_mtok` for `judge_cost_usd`:

```python
def _cost_per_mtok(model_name: str) -> tuple[float, float]:
    name = model_name.lower()
    if "haiku" in name:
        return (
            settings.pricing_claude_haiku_input_per_mtok,
            settings.pricing_claude_haiku_output_per_mtok,
        )
    return (
        settings.pricing_claude_sonnet_4_5_input_per_mtok,
        settings.pricing_claude_sonnet_4_5_output_per_mtok,
    )
```

**Required signature:**
```python
class AnthropicJudge:
    name: str = settings.llm_judge_model
    PROMPT_VERSION: ClassVar[str] = "v1.ragas-faithfulness-relevance"
    _judge_semaphore: ClassVar[asyncio.Semaphore] = asyncio.Semaphore(settings.judge_concurrency)

    def __init__(self) -> None:
        self._client = AsyncAnthropic(
            api_key=settings.anthropic_api_key.get_secret_value(),
            timeout=settings.judge_timeout_seconds,  # D-5.05: 10.0s
        )

    async def score(self, answer: str, chunks: list[RetrievedChunk]) -> EvalScores: ...
```

**Error-handling pattern to mirror:** Wrap the entire `messages.create(...)` call in try/except for `anthropic.RateLimitError`, `anthropic.APIConnectionError`, `anthropic.APITimeoutError` — sleep 500ms then retry once (D-5.05). Parse-shape errors (`KeyError`, `ValidationError` from `EvalScores(**tool_use.input)`) do NOT retry. The dispatcher (not this adapter) wraps `score()` in the failure-span emission per D-5.07.

**Test pattern:** `tests/test_llm_adapter.py` lines 30–119 — `_FakeAsyncAnthropic` factory + `monkeypatch.setattr(llm_mod, "AsyncAnthropic", _factory)` + autouse `_configured_env` fixture that pops `tracer_ai.config` before re-import. Phase 5 test mocks `client.messages.create(...)` returning a SimpleNamespace with `content=[SimpleNamespace(type="tool_use", input={"faithfulness": 0.8, "relevance": 0.9, "rationale": "..."})]` and `usage=SimpleNamespace(input_tokens=100, output_tokens=20)`.

**Deviations from analog:**
- This calls `messages.create(..., tools=[SUBMIT_EVAL_TOOL], tool_choice={"type":"tool","name":"submit_eval"})` — NOT `messages.stream(...)`. No streaming; one round-trip.
- Returns `EvalScores` (Pydantic model with faithfulness/relevance/rationale), not an `AsyncIterator[StreamEvent]`.
- Includes `PROMPT_VERSION` module/class constant per D-5.04 (analog has no equivalent).
- `_judge_semaphore` is a module-level singleton acquired around the API call (D-5.09).

---

### `tracer_ai/eval/dispatcher.py` (Backend / Background worker, dispatch site)

**Analog:** `tracer_ai/tracer/exporters/postgres.py` lines 57–132 (`SpanConsumer` class) for the drain pattern + Phase 4 lifespan finally block (`tracer_ai/api/lifespan.py:148-167`) for the orchestration shape.

**Drain-with-timeout pattern** (`postgres.py:112-132`):

```python
async def drain(self) -> None:
    """Flush remaining items. Called by lifespan during shutdown (D-4.10)."""
    batch: list[Span] = []
    while self._queue.qsize() > 0:
        try:
            span = await asyncio.wait_for(self._queue.get(), timeout=0.1)
            batch.append(span)
        except TimeoutError:
            break
        if len(batch) >= _BATCH_SIZE:
            try:
                await self._flush(batch)
            except Exception as exc:
                log.exception("tracer.drain_flush_failed", error=str(exc))
            batch = []
```

**Lifespan integration shape** (`lifespan.py:148-167`):

```python
finally:
    # D-4.10: 5s drain -> cancel consumer task -> close pool.
    if consumer is not None and queue_obj is not None:
        consumer.stop_accepting = True
        try:
            await asyncio.wait_for(consumer.drain(), timeout=5.0)
        except TimeoutError:
            log.warning(
                "tracer.shutdown_drain_incomplete",
                remaining=queue_obj.qsize(),
            )
```

**Never-raise emit pattern** (`postgres.py:45-54`):

```python
async def emit(self, span: Span) -> None:
    """Enqueue a span. Fire-and-forget -- saturation handled by queue itself.
    T-04-03-04: emit() must NEVER raise back into pipeline.
    """
    try:
        await self._queue.put(span)
    except Exception as exc:
        log.warning("tracer.emit_swallowed", error=str(exc), span_name=span.name)
```

**Required signature:**
```python
class EvalDispatcher:
    def __init__(self, judge: Judge, writer: TraceWriter, pool: asyncpg.Pool) -> None:
        self._judge = judge
        self._writer = writer
        self._pool = pool
        self._pending: set[asyncio.Task[None]] = set()

    def enqueue(
        self,
        trace_id: UUID,
        ctx_snapshot: contextvars.Context,
        answer: str,
        chunks: list[RetrievedChunk],
    ) -> None:
        """Dispatch judge call as background task. Must NOT block, NOT await, NOT raise."""
        task = asyncio.create_task(
            self._run_in_context(trace_id, ctx_snapshot, answer, chunks),
            name=f"eval-{trace_id}",
        )
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    async def drain(self, timeout: float = 5.0) -> None:
        """Await all pending tasks; warn-log surviving on timeout."""
        if not self._pending:
            return
        try:
            await asyncio.wait_for(
                asyncio.gather(*self._pending, return_exceptions=True),
                timeout=timeout,
            )
        except TimeoutError:
            log.warning("eval.dispatcher_drain_incomplete", remaining=len(self._pending))
```

**Error-handling pattern to mirror:** Every layer of `_run_in_context` wrapped in try/except — Pitfall #3 (eval failures NEVER re-raise into request path). On `TimeoutError`, `RateLimitError`, `ToolUseParseError`: emit a `rag.eval` span with `attrs["error.type"] = type(exc).__name__` and `RAG_EVAL_FAITHFULNESS = None` per D-5.07. The `UPDATE traces SET faithfulness = $1` runs only on success.

**Test pattern:** Mirror `tests/integration/test_lifespan_drain.py` — fake judge that sleeps 6s; dispatcher.enqueue() returns immediately; lifespan drain's `asyncio.wait_for(dispatcher.drain(), timeout=5.0)` produces `eval.dispatcher_drain_incomplete remaining=1` warning log.

**Deviations from analog:**
- SpanConsumer drains a queue; EvalDispatcher drains a `set[asyncio.Task]`.
- SpanConsumer runs as one long-lived consumer task; EvalDispatcher creates one task per request (`asyncio.create_task` from inside the SSE generator).
- Drain MUST run BEFORE consumer drain in lifespan (eval emits spans into the consumer's queue, so consumer must outlive dispatcher per CONTEXT.md).

---

### `tracer_ai/eval/calibrate.py` (Backend / CLI, read-only + file producer)

**Analog:** `tracer_ai/cli/__main__.py` lines 35–125 (argparse subcommand pattern). RESEARCH.md flagged that CONTEXT.md mentioned "Click" but no Click dep exists; this codebase uses argparse — Phase 5 must follow.

**Subparser construction pattern** (`cli/__main__.py:35-65`):

```python
def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tracer-ai",
        description="tracer-ai CLI: ingest, query, and admin operations",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    ingest = sub.add_parser("ingest", help="Ingest a corpus into the chunks table")
    src_group = ingest.add_mutually_exclusive_group(required=True)
    src_group.add_argument("--source", type=Path, help="Filesystem directory ...")
    src_group.add_argument("--urls", type=Path, help="Text file with one URL per line")
    ingest.add_argument("--batch-size", type=int, default=64, help="...")
    return parser
```

**Async-runner-with-pool pattern** (`cli/__main__.py:67-91`):

```python
async def _run_ingest_async(
    *,
    source: Path | None,
    urls: list[str] | None,
    batch_size: int,
) -> IngestResult:
    """Build deps + open pool + run ingest + close pool."""
    asyncpg_dsn = str(settings.database_url).replace("+asyncpg", "")
    pool = await asyncpg.create_pool(dsn=asyncpg_dsn, min_size=1, max_size=4)
    try:
        return await run_ingest(source=source, urls=urls, ...)
    finally:
        await pool.close()
```

**Print allowlist** (`cli/__main__.py:122-125`):

```python
# ``print`` allowlist: cli/__main__.py is the only tracer_ai/ file that
# may emit raw print(); per-D-2.37.
print(result.model_dump_json(indent=2))
```

**Required signatures:**
```python
# In tracer_ai/eval/calibrate.py:
async def run_label(*, n: int, strategy: Literal["recent","random","stratified"]) -> None:
    """Walk N traces from DB; prompt [g/b/s] + notes; append to docs/eval/calibration_set.yaml."""
async def run_threshold(*, calibration_set: Path) -> None:
    """Read YAML, run best-F1 sweep over [0.3..0.9] step 0.05, print sweep table + suggested env."""

# In tracer_ai/cli/__main__.py: add subparser
calibrate = sub.add_parser("calibrate", help="...")
cal_sub = calibrate.add_subparsers(dest="cal_command", required=True)
label = cal_sub.add_parser("label")
label.add_argument("--n", type=int, default=30)
label.add_argument("--strategy", choices=["recent","random","stratified"], default="recent")
threshold = cal_sub.add_parser("threshold")
```

**Error-handling pattern to mirror:** Match `cli/__main__.py:107-110` — file-not-found returns `print(..., file=sys.stderr); return 2`. CLI may use `print()` (D-2.37 allowlist explicitly extends to `cli/__main__.py`; calibrate.py is invoked FROM that file so its stdout/stderr is operator-facing — but per safety, emit user-facing output via the CLI module's `print` call site, not from inside `eval/calibrate.py`).

**Module-deps DAG constraint:** `eval/` may import `tracer/`, `rag/`, `config/`, `errors/` but MUST NOT import `api/` (D-2.27). The asyncpg pool is constructed inside `calibrate.py`'s async runner — does NOT reuse `app.state.db_pool`.

**Test pattern:** Subprocess invocation pattern (see `cli/__main__.py:128 # pragma: no cover -- exercised via subprocess in tests`). Tests patch the asyncpg pool factory + DB rows.

**Deviations from analog:**
- Two subcommands (`label`, `threshold`) under one `calibrate` subparser (analog has flat `ingest` only).
- `label` is interactive (reads stdin); analog is fire-and-forget. Use `input()` for the [g/b/s] prompt; allowed since `cli/` is the print allowlist.

---

### `tracer_ai/eval/protocols.py` (Backend / Schema, passthrough)

**Analog:** `tracer_ai/rag/protocols.py` lines 1–63 (LLM Protocol shape).

**Protocol declaration pattern** (lines 50–63):

```python
@runtime_checkable
class LLM(Protocol):
    """Stream tokens from an LLM provider.

    Phase 3 adapter: ``AnthropicLLM`` wrapping ``AsyncAnthropic.messages.stream()``.
    Yields ``TextDelta(text=...)`` events followed by exactly one
    ``Final(result=LLMResult)`` event.
    """

    name: str

    async def stream(
        self, messages: list[Message], *, max_tokens: int = 1024
    ) -> AsyncIterator[StreamEvent]: ...
```

**Required signature:**
```python
@runtime_checkable
class Judge(Protocol):
    """Score an answer + retrieved chunks for faithfulness + relevance.

    Phase 5 adapter: ``AnthropicJudge`` wrapping
    ``AsyncAnthropic.messages.create(..., tools=[SUBMIT_EVAL_TOOL])``.
    Returns one ``EvalScores`` per call (no streaming).
    """

    name: str

    async def score(
        self, answer: str, chunks: list[RetrievedChunk]
    ) -> EvalScores: ...
```

**Test pattern:** `tests/test_rag_protocols.py` — runtime `isinstance(adapter, LLM)` check. Phase 5 adds `assert isinstance(AnthropicJudge(), Judge)` and `assert isinstance(MockJudge(), Judge)`.

**Deviations:** None of substance — this is a pure analog application.

---

### `tracer_ai/tracer/context.py` (Backend / Tracer, passthrough)

**Analog:** No exact in-repo analog (file is currently a 7-line stub); closest reference is `tracer_ai/tracer/writer.py:26-50` for the `Span` Pydantic model that this module references. Pattern derives from stdlib `contextvars` and the docstring already in `context.py` referencing Pitfall #1.

**Existing stub** (`context.py:1-7`):

```python
"""Context propagation helpers (Phase 2 stub; Phase 4 TRCR-04 fills).

Per docs/sequence-diagrams.md (Pitfall #1 mitigation): the eval branch will
snapshot OTel context BEFORE rag.request root span ends so rag.eval becomes
a child span, not an orphan root.
"""
```

**Required signature** (D-5.06; ~40 LOC):

```python
"""Hand-rolled contextvar helpers for cross-task span parentage (D-5.06).

Closes TRCR-04 with zero ``opentelemetry-*`` runtime deps — preserves ADR 005's
"OTel-compatible naming, no OTel runtime" thesis.

Per Pitfall #1 (docs/sequence-diagrams.md): capture context snapshot BEFORE
rag.request root span ends. Per D-5.10: the snapshot is taken by the SSE
generator immediately after the `final` frame yields, then passed to
``EvalDispatcher.enqueue(...)`` so the rag.eval span becomes a child of
rag.request rather than an orphan root.
"""
from __future__ import annotations
import contextvars
from typing import Final
from tracer_ai.tracer.writer import Span

_current_span: Final[contextvars.ContextVar[Span | None]] = contextvars.ContextVar(
    "_current_span", default=None,
)

def current_span() -> Span | None:
    """Return the active span in this context (None at the root)."""
    return _current_span.get()

def set_current_span(span: Span | None) -> contextvars.Token[Span | None]:
    """Set the active span; returns a token for ``reset()``."""
    return _current_span.set(span)

def capture_context() -> contextvars.Context:
    """Snapshot the current contextvars Context (Pitfall #1 ordering matters)."""
    return contextvars.copy_context()
```

**Error-handling pattern:** None — these are pure stdlib wrappers; `ContextVar.get()` cannot raise on a defaulted var.

**Test pattern:** Match `tests/unit/tracer/test_queue.py` shape — pytest-asyncio + minimal in-process test. Assert: (1) `current_span() is None` at module entry; (2) inside `set_current_span(span)` block `current_span() == span`; (3) `capture_context()` snapshot called inside a `set_current_span` block, then `ctx.run(current_span)` from a different task returns the original span (cross-task propagation).

**Deviations from analog:** No close in-repo analog — this is essentially a clean room implementation against the stdlib contract. Module-deps DAG: `tracer/` may import `tracer/writer.py` only; this module sits at the same DAG layer as `writer.py`.

---

### `tracer_ai/api/feedback.py` (MODIFY — add PATCH /feedback/{trace_id}/resolved)

**Analog (in same file):** existing `POST /feedback` handler at lines 43–81.

**Atomic-transaction pattern to copy** (lines 51–71):

```python
pool: asyncpg.Pool = request.app.state.db_pool
async with (
    pool.acquire(timeout=1.0) as conn,
    conn.transaction(),  # Phase 4 D-4.03: atomic INSERT + UPDATE
):
    row = await conn.fetchrow(
        "INSERT INTO feedback (trace_id, rating, comment, diagnosis_tag) "
        "VALUES ($1, $2, $3, $4) "
        "RETURNING id, created_at",
        body.trace_id,
        body.rating,
        body.comment,
        body.diagnosis_tag,
    )
    await conn.execute(
        "UPDATE traces SET feedback_rating = $1 WHERE id = $2",
        body.rating,
        body.trace_id,
    )
```

**Logging pattern** (lines 76–80):

```python
log.info(
    "feedback_recorded",
    trace_id=str(body.trace_id),
    rating=body.rating,
)
```

**Required signature for new route:**

```python
@router.patch("/feedback/{trace_id}/resolved", response_model=FeedbackResolveResponse)
async def patch_feedback_resolved(
    trace_id: UUID, request: Request,
) -> FeedbackResolveResponse:
    """Mark all feedback rows for ``trace_id`` as resolved (D-5.15)."""
    pool: asyncpg.Pool = request.app.state.db_pool
    async with pool.acquire(timeout=1.0) as conn:
        result = await conn.execute(
            "UPDATE feedback SET resolved_at = now() "
            "WHERE trace_id = $1 AND resolved_at IS NULL",
            trace_id,
        )
    # asyncpg returns "UPDATE N" command tag; parse N.
    rows_affected = int(result.split()[-1]) if result.startswith("UPDATE") else 0
    log.info("feedback_resolved", trace_id=str(trace_id), rows_affected=rows_affected)
    return FeedbackResolveResponse(trace_id=trace_id, resolved_at=datetime.now(UTC))
```

**Error-handling pattern to mirror:** Existing handler doesn't raise on 0 rows affected (orphan trace_id is accepted per T-03-06-07 logic). Mirror: 0 rows affected = success with `rows_affected=0` in log. No 404.

**Test pattern:** `tests/test_feedback_route.py` (verify exists) — TestClient + asyncpg fixture. Phase 5 adds: insert one feedback row with `resolved_at IS NULL`, PATCH the endpoint, assert `resolved_at IS NOT NULL` after.

**Deviations from analog:** PATCH (not POST), 200 response (not 201), no body (path param only), no transaction needed (single UPDATE).

---

### `tracer_ai/api/admin.py` (MODIFY — add GET /admin/eval-config)

**Analog (in same file):** existing `GET /admin/corpus` at lines 95–117.

**Read-only handler pattern** (lines 95–117):

```python
@router.get("/corpus", response_model=CorpusState)
async def get_corpus(request: Request) -> CorpusState:
    pool: asyncpg.Pool = request.app.state.db_pool
    state = await list_corpus(pool)
    log.info("corpus_listed", doc_count=state["doc_count"], chunk_count=state["chunk_count"])
    return CorpusState(...)
```

**Required signature:**

```python
@router.get("/eval-config", response_model=EvalConfigResponse)
async def get_eval_config() -> EvalConfigResponse:
    """Return the current eval thresholds + judge model + prompt version (D-5.13).

    Single source of truth for the bad-answer-queue threshold; avoids drift
    between calibrated value (in env) and what the frontend filters on.
    """
    from tracer_ai.eval.llm_judge import AnthropicJudge  # local import keeps eval/ optional
    return EvalConfigResponse(
        threshold=settings.bad_answer_faithfulness_threshold,
        judge_prompt_version=AnthropicJudge.PROMPT_VERSION,
        judge_model=settings.llm_judge_model,
        calibration_date=settings.calibration_date,
    )
```

**Error-handling pattern to mirror:** None needed — pure read of `settings`. Module-level. No DB.

**Test pattern:** Match `tests/test_admin_routes.py` shape — TestClient + assert response shape matches `EvalConfigResponse` schema.

**Deviations from analog:** No DB access, no log line needed (responses are deterministic from settings).

---

### `tracer_ai/api/traces.py` (MODIFY — add GET /traces/timeseries)

**Analog (in same file):** `GET /traces` at lines 56–99 + `tracer_ai/tracer/store.py:list_traces` lines 214–298.

**Filter-validated query handler pattern** (lines 56–99):

```python
@router.get("/traces", response_model=TraceListResponse)
async def list_traces(
    request: Request,
    query: Annotated[str | None, Query(description="ILIKE substring on traces.query_text")] = None,
    since: Annotated[datetime | None, Query()] = None,
    until: Annotated[datetime | None, Query()] = None,
    feedback: Annotated[Literal["up", "down"] | None, Query()] = None,
    min_faithfulness: Annotated[float | None, Query(ge=0.0, le=1.0)] = None,
    ...
) -> TraceListResponse:
    pool: asyncpg.Pool = request.app.state.db_pool
    writer = request.app.state.trace_writer
    store = PostgresTraceStore(pool, writer)
    filters = TraceListFilters(...)
    try:
        items_dict, next_cursor = await store.list_traces(filters=filters, cursor=cursor, limit=limit)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_err("INVALID_REQUEST", str(exc)),
        ) from exc
```

**Parameterized SQL with `$N IS NULL` guards pattern** (`store.py:246-272`):

```python
sql = (
    "SELECT id, started_at, query_text, latency_ms, ... "
    "FROM traces "
    "WHERE latency_ms IS NOT NULL "
    "  AND ($1::text IS NULL OR query_text ILIKE '%' || $1 || '%') "
    "  AND ($2::timestamptz IS NULL OR started_at >= $2) "
    ...
)
params: tuple[Any, ...] = (
    filters.query, filters.since, filters.until, ...
)
async with self._pool.acquire() as conn:
    rows = await conn.fetch(sql, *params)
```

**Required signature for new route:**

```python
@router.get("/traces/timeseries", response_model=TimeseriesResponse)
async def get_traces_timeseries(
    request: Request,
    window: Annotated[Literal["1h","24h","7d","30d"], Query()] = "24h",
) -> TimeseriesResponse:
    """Adaptive-bucket time-series for dashboard charts (D-5.17, DASH-01..04)."""
    pool: asyncpg.Pool = request.app.state.db_pool
    writer = request.app.state.trace_writer
    store = PostgresTraceStore(pool, writer)
    buckets = await store.timeseries(window=window)
    return TimeseriesResponse(window=window, buckets=[TimeseriesBucket(**b) for b in buckets])
```

**Bucket-resolution rule** (D-5.17):

```python
# In tracer_ai/tracer/store.py:
_BUCKET_BY_WINDOW: dict[str, tuple[str, str]] = {
    # window -> (DATE_TRUNC unit, INTERVAL string for GENERATE_SERIES)
    "1h":  ("minute",  "1 minute"),
    "24h": ("minute",  "5 minutes"),  # uses date_bin() not date_trunc for 5-min
    "7d":  ("hour",    "1 hour"),
    "30d": ("day",     "1 day"),
}
```

**Error-handling pattern to mirror:** Same `_err("INVALID_REQUEST", ...)` envelope (lines 46–53) for 400 cases. Window literal validation handled by FastAPI 422 before SQL runs.

**Test pattern:** Match `tests/integration/test_traces_api.py` shape — fixture seeds traces across multiple buckets; assert response has expected bucket count and ordering.

**Deviations from analog:** No cursor pagination (windowed time-series is bounded by SQL `GENERATE_SERIES`). Returns aggregations (`AVG`, `PERCENTILE_CONT`, `COUNT`), not raw rows. Adds new `timeseries()` method to `PostgresTraceStore` — preserve module-deps DAG (returns `list[dict[str, Any]]` not Pydantic).

---

### `tracer_ai/api/chat.py` (MODIFY — add ctx-snapshot capture + dispatcher.enqueue after final yields)

**Analog (in same file):** existing SSE generator at lines 52–87.

**Extension point — after the `final` frame yields** (current shape lines 64–77):

```python
async def gen() -> AsyncIterator[bytes]:
    try:
        async for ev in pipeline.run_chat_stream(body.question):
            if isinstance(ev, TextDelta):
                frame = f"event: token\ndata: {json.dumps({'text': ev.text})}\n\n"
                yield frame.encode("utf-8")
            elif isinstance(ev, ChatFinalEvent):
                payload = ev.model_dump(mode="json")
                frame = f"event: final\ndata: {json.dumps(payload)}\n\n"
                yield frame.encode("utf-8")
                # Phase 5 D-5.10: dispatch judge AFTER yielding final frame.
                # ctx_snapshot must have been captured BEFORE rag.request ended
                # (Pitfall #1) — handled by pipeline.run_chat_stream returning
                # the snapshot in ev.ctx_snapshot or via app.state pattern.
    except Exception as exc:
        log.exception("chat_stream_error", error=str(exc))
        err_frame = f"event: error\ndata: {json.dumps({'message': str(exc)})}\n\n"
        yield err_frame.encode("utf-8")
```

**Required signature for the dispatch site:**

```python
elif isinstance(ev, ChatFinalEvent):
    payload = ev.model_dump(mode="json")
    frame = f"event: final\ndata: {json.dumps(payload)}\n\n"
    yield frame.encode("utf-8")
    # D-5.10: dispatch judge after final frame; never blocks, never raises.
    dispatcher = request.app.state.eval_dispatcher
    if dispatcher is not None:
        try:
            dispatcher.enqueue(
                trace_id=ev.trace_id,
                ctx_snapshot=ev.ctx_snapshot,   # captured by Pipeline._orchestrate
                answer=ev.answer,                # NEW field on ChatFinalEvent
                chunks=ev.chunks_for_judge,      # NEW field on ChatFinalEvent
            )
        except Exception as exc:
            # CLAUDE.md: tracer/eval failures must NEVER fail user requests.
            log.warning("eval.enqueue_swallowed", error=str(exc), trace_id=str(ev.trace_id))
```

**Error-handling pattern to mirror:** Existing `try/except Exception` at line 74 stays unchanged. The dispatcher.enqueue() must be inside its own try/except so its failure never reaches the outer except (Pitfall #3).

**Test pattern:** `tests/test_chat_route.py` — assert: (1) final frame is yielded; (2) `dispatcher.enqueue` was called with `trace_id` matching the final frame; (3) when dispatcher.enqueue raises, response still completes successfully.

**Deviations from analog:** This is the dispatch site (D-5.10). The capture-context-snapshot step happens INSIDE `Pipeline._orchestrate` (Pitfall #1: BEFORE `_emit_root` ends rag.request); the snapshot is propagated out via the `ChatFinalEvent` (which gets new fields per below).

---

### `tracer_ai/api/lifespan.py` (MODIFY — wire EvalDispatcher + drain BEFORE consumer drain)

**Analog (in same file):** Phase 4 PostgresTraceWriter + SpanConsumer wiring at lines 99–167.

**Construction-with-fallback pattern** (lines 99–144):

```python
try:
    embedder = VoyageEmbedder()
    retriever = PgvectorRetriever(pool)
    llm: LLM = cast(LLM, AnthropicLLM())
    queue_obj = BoundedDropOldestQueue(maxsize=1000)
    writer: TraceWriter = PostgresTraceWriter(queue=queue_obj)
    consumer = SpanConsumer(queue=queue_obj, pool=pool)
    consumer_task = asyncio.create_task(consumer.run(), name="tracer-consumer")
    app.state.embedder = embedder
    ...
    app.state.pipeline = Pipeline(embedder, retriever, llm, writer, top_k=5, db_pool=pool)
    log.info("pipeline_ready", embedder=embedder.name, llm=llm.name, writer="PostgresTraceWriter")
except Exception as exc:
    log.warning("pipeline_construction_skipped", error=str(exc))
    app.state.pipeline = None
    ...
```

**Drain ordering pattern** (lines 148–167):

```python
finally:
    # D-4.10: 5s drain -> cancel consumer task -> close pool.
    if consumer is not None and queue_obj is not None:
        consumer.stop_accepting = True
        try:
            await asyncio.wait_for(consumer.drain(), timeout=5.0)
        except TimeoutError:
            log.warning("tracer.shutdown_drain_incomplete", remaining=queue_obj.qsize())
    if consumer_task is not None:
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            pass
    await app.state.db_pool.close()
```

**Required additions:**

```python
# In the try block, after writer/consumer construction:
from tracer_ai.eval.dispatcher import EvalDispatcher
from tracer_ai.eval.llm_judge import AnthropicJudge

try:
    judge = AnthropicJudge()  # may raise on missing settings
except Exception as exc:
    log.warning("eval.judge_construction_skipped", error=str(exc))
    judge = None

if judge is not None:
    eval_dispatcher = EvalDispatcher(judge=judge, writer=writer, pool=pool)
    app.state.eval_dispatcher = eval_dispatcher
else:
    app.state.eval_dispatcher = None

# In the finally block, BEFORE consumer drain:
if getattr(app.state, "eval_dispatcher", None) is not None:
    try:
        await asyncio.wait_for(app.state.eval_dispatcher.drain(timeout=5.0), timeout=5.0)
    except TimeoutError:
        log.warning("eval.dispatcher_drain_incomplete")
# Then existing consumer drain (eval may have emitted spans into the consumer queue,
# so consumer must outlive dispatcher).
```

**Error-handling pattern to mirror:** Same as Phase 4 — outer try/except around construction lets api boot when `ANTHROPIC_API_KEY` is missing in dev; `app.state.eval_dispatcher = None` and chat handler checks for None.

**Test pattern:** `tests/integration/test_lifespan_drain.py` — extend the slow-pool test to also assert dispatcher drain timeout produces `eval.dispatcher_drain_incomplete` warning. Critical: drain ORDER (eval before consumer).

**Deviations from analog:** **Drain order is REVERSED** — eval drain MUST run before consumer drain (eval produces spans into the consumer's queue).

---

### `tracer_ai/api/schemas.py` (MODIFY — add 4 schemas)

**Analog (in same file):** existing `TraceListItem`, `FeedbackResponse`, `CorpusState` schemas.

**Strict-mode pattern** (lines 99–105):

```python
class FeedbackResponse(BaseModel):
    """POST /feedback response body."""
    model_config = ConfigDict(extra="forbid")
    id: UUID
    created_at: datetime
```

**Required new schemas:**

```python
# After FeedbackResponse:
class FeedbackResolveResponse(BaseModel):
    """PATCH /feedback/{trace_id}/resolved response body (D-5.15)."""
    model_config = ConfigDict(extra="forbid")
    trace_id: UUID
    resolved_at: datetime

# After CorpusState block:
class EvalConfigResponse(BaseModel):
    """GET /admin/eval-config response body (D-5.13)."""
    model_config = ConfigDict(extra="forbid")
    threshold: Annotated[float, Field(ge=0.0, le=1.0)]
    judge_prompt_version: str
    judge_model: str
    calibration_date: datetime | None = None

# After TraceDetailResponse:
class TimeseriesBucket(BaseModel):
    """One bucket in GET /traces/timeseries response (D-5.17)."""
    model_config = ConfigDict(extra="forbid")
    bucket_start: datetime
    latency_p50: float | None = None
    latency_p95: float | None = None
    cost_sum: float
    faithfulness_mean: float | None = None     # NULL when no eval-scored traces in bucket
    feedback_down_ratio: float | None = None    # NULL when no rated traces in bucket
    request_count: Annotated[int, Field(ge=0)]

class TimeseriesResponse(BaseModel):
    """GET /traces/timeseries response envelope (DASH-01..04)."""
    model_config = ConfigDict(extra="forbid")
    window: Literal["1h","24h","7d","30d"]
    buckets: list[TimeseriesBucket]
```

**Error-handling pattern to mirror:** No special handling — Pydantic v2 strict-mode + `extra="forbid"` rejects unknown fields automatically (D-2.39).

**Test pattern:** `tests/test_api_schemas.py` — assert each new schema rejects extra fields with `pydantic.ValidationError`.

**Deviations from analog:** None — pure pattern application.

---

### `tracer_ai/rag/pipeline.py` (MODIFY — return ctx_snapshot from _orchestrate)

**Analog (in same file):** `_orchestrate` and `run_chat_stream` at lines 127–478.

**Capture-before-end pattern** (Pitfall #1 — must capture BEFORE `_emit_root` ends rag.request):

The current `_orchestrate` returns `tuple[UUID, list[RetrievedChunk], AsyncIterator[str], dict[str, int|float]]`. Phase 5 extends this to capture the contextvar snapshot BEFORE the inner `_llm_text_iter`'s finally block calls `_emit_root`.

**Existing `_emit_root` call site** (lines 374–377):

```python
finally:
    # Always emit the root rag.request span -- even if a stage
    # raised mid-flight or the consumer cancelled iteration.
    await self._emit_root(trace_id, root_span_id, root_started, root_attrs, t0)
```

**Required signature change:**

```python
# Inside _llm_text_iter, BEFORE the writer.emit / _emit_root sequence:
from tracer_ai.tracer.context import set_current_span, capture_context

# Set the rag.request span as current BEFORE final frame yield logic, so the
# snapshot taken below has rag.request as parent. Use a token so the var is
# reset on exit.
root_span_for_ctx = Span(
    trace_id=trace_id, span_id=root_span_id, parent_span_id=None,
    name=_SPAN_REQUEST, started_at=root_started, attrs=root_attrs,
)
token = set_current_span(root_span_for_ctx)
try:
    ctx_snapshot = capture_context()  # Pitfall #1: BEFORE root.end()
    # store on instance so run_chat_stream can read after iter exits
    self._last_ctx_snapshot = ctx_snapshot
    self._last_answer = "".join(answer_parts)  # need to thread through
    self._last_chunks = chunks
finally:
    pass  # Token reset on root span emit below
```

**Error-handling pattern to mirror:** Same try/finally cancellation safety pattern (Pitfall 7.8) — context capture lives inside the same try-block envelope.

**Test pattern:** `tests/test_pipeline.py` — assert that `Pipeline.run_chat_stream(...)` produces a `ChatFinalEvent` with a captured ctx_snapshot, and that running `ctx_snapshot.run(current_span)` returns the rag.request span.

**Deviations from analog:** This is an EXTENSION of `_orchestrate`'s return shape — the planner may extend `ChatFinalEvent` (in `tracer_ai/rag/types.py`) with optional `ctx_snapshot: Any | None = None`, `answer: str = ""`, `chunks_for_judge: list[RetrievedChunk] = []` fields, OR thread these via `app.state.last_request_context` (CONTEXT.md flagged both options for planner discretion).

---

### `tracer_ai/config.py` (MODIFY — add 4 fields)

**Analog (in same file):** existing Settings field declarations at lines 59–119.

**Field declaration pattern** (lines 59–73):

```python
llm_judge_model: str = Field(
    default="claude-haiku-4-5-20251001",
    validation_alias="LLM_JUDGE_MODEL",
    description="Anthropic dated snapshot for the judge (Phase 5+)",
)
log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
    default="INFO",
    validation_alias="LOG_LEVEL",
    description="structlog level -- Literal rejects out-of-enum injection at validation time",
)
```

**Bounded numeric field pattern** (lines 106–119):

```python
chunking_default_size: int = Field(
    default=900,
    ge=100,
    le=4000,
    validation_alias="CHUNKING_DEFAULT_SIZE",
    description="Default chunk size in tokens; admin-tunable via PATCH /admin/chunking-config",
)
```

**Required additions:**

```python
# === Eval / Quality Layer (Phase 5; D-5.13 / D-5.09 / D-5.05 / D-5.14) ===
bad_answer_faithfulness_threshold: float = Field(
    default=0.6,
    ge=0.0,
    le=1.0,
    validation_alias="BAD_ANSWER_FAITHFULNESS_THRESHOLD",
    description="Threshold below which faithfulness flags a trace for the bad-answer queue (D-5.13)",
)
judge_concurrency: int = Field(
    default=4,
    ge=1,
    le=32,
    validation_alias="JUDGE_CONCURRENCY",
    description="Max in-flight judge calls (asyncio.Semaphore bound; D-5.09)",
)
judge_timeout_seconds: float = Field(
    default=10.0,
    gt=0.0,
    le=60.0,
    validation_alias="JUDGE_TIMEOUT_SECONDS",
    description="Per-call AsyncAnthropic judge timeout; total wall budget budget=21s (D-5.05)",
)
calibration_date: datetime | None = Field(
    default=None,
    validation_alias="CALIBRATION_DATE",
    description="ISO timestamp of last calibration; renders Tremor AreaChart annotation (D-5.14)",
)
```

**Error-handling pattern to mirror:** Pydantic Settings `extra="forbid"` (line 36) — no extra handling needed; `calibration_date` parses ISO automatically; bounded numerics raise `ValidationError` at import time (D-2.21 fail-fast).

**Test pattern:** `tests/test_config_failfast.py` — assert that out-of-bounds env values raise at import time.

**Deviations from analog:** None — pure pattern application. Add `from datetime import datetime` to imports if not already present.

---

### `tracer_ai/cli/__main__.py` (MODIFY — add `calibrate` subcommand group)

**Analog (in same file):** existing `ingest` subparser at lines 35–125.

**Subparser registration** (lines 45–63):

```python
sub = parser.add_subparsers(dest="command", required=True)
ingest = sub.add_parser("ingest", help="Ingest a corpus into the chunks table")
src_group = ingest.add_mutually_exclusive_group(required=True)
src_group.add_argument("--source", type=Path, ...)
src_group.add_argument("--urls", type=Path, ...)
ingest.add_argument("--batch-size", type=int, default=64, ...)
```

**Command-dispatch pattern** (lines 99–125):

```python
if args.command != "ingest":
    parser.error("only 'ingest' is supported in Phase 3")
    return 2

# Build args; call async runner
result = asyncio.run(
    _run_ingest_async(
        source=args.source,
        urls=urls_list,
        batch_size=args.batch_size,
    )
)
print(result.model_dump_json(indent=2))
return 1 if result.errors else 0
```

**Required additions:**

```python
# In _build_parser, after ingest:
calibrate = sub.add_parser("calibrate", help="Calibrate bad-answer threshold against hand-labeled traces")
cal_sub = calibrate.add_subparsers(dest="cal_command", required=True)

label = cal_sub.add_parser("label", help="Walk N traces interactively; append labels to YAML")
label.add_argument("--n", type=int, default=30, help="Number of traces to label (default: 30)")
label.add_argument("--strategy", choices=["recent","random","stratified"], default="recent")
label.add_argument("--out", type=Path, default=Path("docs/eval/calibration_set.yaml"))

threshold = cal_sub.add_parser("threshold", help="Run best-F1 sweep and print suggested env value")
threshold.add_argument("--in", dest="in_path", type=Path, default=Path("docs/eval/calibration_set.yaml"))

# In main(), after the ingest branch:
if args.command == "calibrate":
    from tracer_ai.eval import calibrate as cal_mod
    if args.cal_command == "label":
        asyncio.run(cal_mod.run_label(n=args.n, strategy=args.strategy, out_path=args.out))
        return 0
    if args.cal_command == "threshold":
        asyncio.run(cal_mod.run_threshold(in_path=args.in_path))
        return 0
```

**Error-handling pattern to mirror:** Lines 99–110 — `parser.error(...)` exits 2 on bad commands; `print(..., file=sys.stderr); return 2` for file-not-found. Match exactly.

**Test pattern:** Subprocess test (per the `pragma: no cover` note at line 128) — invoke `python -m tracer_ai.cli calibrate threshold --in <fixture>`; assert stdout contains the sweep table.

**Deviations from analog:** Two-level subparser nesting (`calibrate label` / `calibrate threshold`); analog has only one level.

---

### `tracer_ai/tracer/store.py` (MODIFY — add timeseries() method)

**Analog (in same file):** `list_traces` at lines 214–298.

**Parameterized SQL + dict-return pattern** (lines 246–298):

```python
sql = (
    "SELECT id, started_at, query_text, latency_ms, estimated_cost_usd, "
    "faithfulness, feedback_rating "
    "FROM traces "
    "WHERE latency_ms IS NOT NULL "
    "  AND ($1::text IS NULL OR query_text ILIKE '%' || $1 || '%') "
    ...
    "ORDER BY started_at DESC, id DESC "
    "LIMIT $9::int"
)
async with self._pool.acquire() as conn:
    rows = await conn.fetch(sql, *params)

items: list[dict[str, Any]] = []
for row in rows[:limit]:
    items.append({
        "trace_id": row["id"], "started_at": row["started_at"],
        ...
    })
return items, next_cursor
```

**Required signature:**

```python
async def timeseries(self, *, window: Literal["1h","24h","7d","30d"]) -> list[dict[str, Any]]:
    """Adaptive-bucket time-series aggregation (D-5.17).

    Returns one dict per bucket shaped to match TimeseriesBucket fields.
    """
    bucket_unit, interval, since_offset = _BUCKET_BY_WINDOW[window]
    sql = f"""
        WITH buckets AS (
          SELECT generate_series(
            date_trunc('{bucket_unit}', now() - interval '{since_offset}'),
            date_trunc('{bucket_unit}', now()),
            interval '{interval}'
          ) AS bucket_start
        )
        SELECT
          b.bucket_start,
          PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY t.latency_ms) AS latency_p50,
          PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY t.latency_ms) AS latency_p95,
          COALESCE(SUM(t.estimated_cost_usd), 0.0) AS cost_sum,
          AVG(t.faithfulness) AS faithfulness_mean,
          (COUNT(*) FILTER (WHERE t.feedback_rating = -1))::float
            / NULLIF(COUNT(*) FILTER (WHERE t.feedback_rating IS NOT NULL), 0)
            AS feedback_down_ratio,
          COUNT(t.id) AS request_count
        FROM buckets b
        LEFT JOIN traces t
          ON date_trunc('{bucket_unit}', t.started_at) = b.bucket_start
          AND t.latency_ms IS NOT NULL
        GROUP BY b.bucket_start
        ORDER BY b.bucket_start ASC
    """
    async with self._pool.acquire() as conn:
        rows = await conn.fetch(sql)
    return [dict(row) for row in rows]
```

**Error-handling pattern to mirror:** None — read-only query; FastAPI 422 already validates `window` Literal upstream.

**Module-deps DAG constraint:** Returns `list[dict[str, Any]]` not Pydantic — preserves `tracer/` not importing `api/` (D-2.27).

**Test pattern:** `tests/integration/test_traces_api.py` — seed traces across multiple bucket boundaries; assert response bucket count matches expected count for the window.

**Deviations from analog:** Aggregation (not list); LEFT JOIN against generated bucket series so empty buckets render as rows with NULL faithfulness_mean (load-bearing for D-5.07 `connectNulls=false`).

---

### `tracer_ai/tracer/span.py` (MODIFY — add ERROR_TYPE constant)

**Analog (in same file):** existing constants at lines 21–39.

**Constant declaration pattern** (lines 32–37):

```python
RAG_EVAL_FAITHFULNESS: str = "rag.eval.faithfulness"
RAG_EVAL_RELEVANCE: str = "rag.eval.relevance"
RAG_EVAL_JUDGE_MODEL: str = "rag.eval.judge_model"
RAG_EVAL_JUDGE_PROMPT_VERSION: str = "rag.eval.judge_prompt_version"
RAG_EVAL_JUDGE_COST_USD: str = "rag.eval.judge_cost_usd"
```

**Required additions:**

```python
# Phase 5 D-5.07: failure-span error type marker.
ERROR_TYPE: str = "error.type"

# Phase 5 EVAL-04: rag.eval span-name constant + judge_latency_ms.
RAG_EVAL_JUDGE_LATENCY_MS: str = "rag.eval.judge_latency_ms"
```

**Error-handling pattern to mirror:** None — pure constant declarations.

**Test pattern:** Existing `tests/test_imports.py` covers structural sanity; no new test required.

**Deviations from analog:** None.

---

### `alembic/versions/0003_feedback_resolved.py` (NEW)

**Analog:** `alembic/versions/0002_traces_denorm.py` (entire file, 81 lines).

**Migration shape pattern** (lines 1–81):

```python
"""add latency_ms, faithfulness, feedback_rating, estimated_cost_usd to traces.

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-06

Never edit 0001_initial.py (D-2.17). This revision is additive-only and reversible.
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
    ...
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS traces_faithfulness_idx ON traces (faithfulness);"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS traces_faithfulness_idx;"))
    op.execute(sa.text("ALTER TABLE traces DROP COLUMN IF EXISTS latency_ms;"))
```

**Required content:**

```python
"""add feedback.resolved_at column for FBCK-04 mark-resolved action (Phase 5 D-5.15).

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-08

Never edit 0001_initial.py / 0002_traces_denorm.py (D-2.17). This revision is
additive-only and reversible.
"""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE feedback ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ NULL;"
    ))
    # Partial index for the bad-answer-queue exclusion filter (FBCK-03):
    # WHERE resolved_at IS NULL is the hot-path predicate.
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS feedback_unresolved_idx "
        "ON feedback (trace_id) WHERE resolved_at IS NULL;"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS feedback_unresolved_idx;"))
    op.execute(sa.text("ALTER TABLE feedback DROP COLUMN IF EXISTS resolved_at;"))
```

**Error-handling pattern to mirror:** `IF NOT EXISTS` / `IF EXISTS` everywhere — analog uses this throughout for re-runnability.

**Test pattern:** `tests/integration/test_alembic_reversibility.py` — assert `alembic upgrade head` then `alembic downgrade -1` then `alembic upgrade head` is idempotent.

**Deviations from analog:** Single-column add (analog adds 4 cols + 1 partition + 2 indexes). No partition extension — Phase 5 may add a separate `0004_2026_09_partition.py` if rolling partition discipline (D-51) requires it by ship date.

---

### `frontend/src/pages/Queue.tsx` (NEW)

**Analog:** `frontend/src/pages/Dashboard.tsx` (entire file, 326 lines).

**Imports + page-component shape** (lines 1–34):

```typescript
import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, Metric, Text, Title } from "@tremor/react";
import { useNavigate } from "react-router-dom";

import { getTraces } from "@/api/traces";
import { Badge } from "@/components/ui/badge";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import type { TraceListItem, TraceListResponse } from "@/types/trace";
```

**TanStack Query pattern with spread queryKey** (lines 56–75):

```typescript
const queryKey = React.useMemo(
  () => [
    "traces",
    filters.query ?? "",
    filters.since ?? "",
    filters.until ?? "",
    filters.feedback ?? "",
    filters.min_faithfulness ?? "",
    filters.max_latency_ms ?? "",
  ],
  [filters],
);
const { data, isLoading, isError, error } = useQuery<
  TraceListResponse,
  Error
>({
  queryKey,
  queryFn: () => getTraces(filters),
  staleTime: 0,                  // D-4.18: dashboard always re-fetches
});
```

**Loading / error skeleton pattern** (lines 90–114):

```typescript
if (isLoading) {
  return (
    <div className="max-w-7xl mx-auto p-8 space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
      <div className="grid grid-cols-4 gap-4">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-24 w-full" />
        ))}
      </div>
    </div>
  );
}
if (isError) {
  return (
    <Card className="border-rose-300 bg-rose-50">
      <Title>Failed to load traces</Title>
      <Text>{error?.message ?? "Unknown error"}</Text>
    </Card>
  );
}
```

**Required signature:**

```typescript
export function Queue(): React.ReactElement {
  const navigate = useNavigate();
  const [tab, setTab] = React.useState<"user" | "judge">("user");

  // Pull current threshold from /admin/eval-config; falls back to 0.6
  const { data: cfg } = useQuery({
    queryKey: ["eval-config"],
    queryFn: () => getEvalConfig(),
    staleTime: 30_000,  // config rarely changes
  });
  const threshold = cfg?.threshold ?? 0.6;

  // User-flagged tab: feedback=down; sorted started_at DESC (server default)
  const userQuery = useQuery<TraceListResponse>({
    queryKey: ["queue", "user"],
    queryFn: () => getTraces({ feedback: "down" }),
    staleTime: 0,         // D-4.18 + FBCK-02: thumbs-down lands within seconds
    enabled: tab === "user",
  });

  // Judge-flagged tab: min_faithfulness < threshold; sorted faithfulness ASC
  const judgeQuery = useQuery<TraceListResponse>({
    queryKey: ["queue", "judge", threshold],
    queryFn: () => getTraces({ max_faithfulness: threshold }),  // NEW filter param needed
    staleTime: 0,
    enabled: tab === "judge",
  });
  // ... render Tabs with table per tab; "Mark resolved" mutation calls markResolved(trace_id)
}
```

**Error-handling pattern to mirror:** Lines 105–113 — same Card error envelope.

**Test pattern:** `frontend/src/pages/__tests__/Queue.test.tsx` if test infra exists (Phase 4 may have defined one). Otherwise, Vitest + React Testing Library + MSW for network mocks.

**Deviations from analog:**
- Uses Tabs component (Dashboard does not).
- Two parallel useQuery calls gated by `enabled: tab === "user"`.
- The Judge-flagged sort is `faithfulness ASC` — requires either a new query param or client-side sort (CONTEXT.md says server-side via existing `GET /traces`; planner may need to add `sort_by=faithfulness_asc` filter to `list_traces`).
- "Mark resolved" mutation invalidates `queryKey: ["queue", ...]` on success.

---

### `frontend/src/pages/Dashboard.tsx` (MODIFY — live timeseries + 5th KpiCard)

**Analog (in same file):** existing KPI strip at lines 121–142 + AreaChart placeholder at lines 145–159.

**KPI grid pattern** (lines 121–142):

```typescript
<div className="grid grid-cols-4 gap-4">
  <Card>
    <Title>TRACES</Title>
    <Metric>{items.length}</Metric>
    <Text>in current view</Text>
  </Card>
  <Card>
    <Title>AVG LATENCY</Title>
    <Metric>{Math.round(totalLatency)}ms</Metric>
    <Text>across visible</Text>
  </Card>
  ...
</div>
```

**AreaChart placeholder shape** (lines 145–159):

```typescript
<Card>
  <Title>Quality drift</Title>
  <Text>faithfulness over the visible window — populates in Phase 5</Text>
  <AreaChart
    data={chartData}
    index="time"
    categories={["faithfulness"]}
    colors={["emerald"]}
    showLegend={false}
    showGridLines={false}
    className="h-32 mt-4"
  />
</Card>
```

**Required additions:**

```typescript
// 1. Change grid-cols-4 -> grid-cols-5 (D-5.16); add 5th KpiCard:
<div className="grid grid-cols-5 gap-4">
  ... (existing 4 cards) ...
  <Card>
    <Title>QUEUE HEALTH</Title>
    <Metric>{queueData?.size ?? 0}</Metric>
    <Text>{queueData?.resolvedThisWeek ?? 0} resolved this week</Text>
  </Card>
</div>

// 2. Replace placeholder with live time-series — 4 charts:
const { data: ts } = useQuery({
  queryKey: ["timeseries", windowSel],
  queryFn: () => getTimeseries(windowSel),
});

<LineChart
  data={ts?.buckets ?? []}
  index="bucket_start"
  categories={["latency_p50", "latency_p95"]}
  colors={["blue", "rose"]}
  connectNulls={false}            // D-5.07 / DASH-03 critical prop
/>
<LineChart data={ts?.buckets ?? []} index="bucket_start" categories={["cost_sum"]} colors={["emerald"]} />
<AreaChart data={ts?.buckets ?? []} index="bucket_start" categories={["faithfulness_mean"]} colors={["emerald"]} connectNulls={false} />
<LineChart data={ts?.buckets ?? []} index="bucket_start" categories={["feedback_down_ratio"]} colors={["rose"]} />
```

**Error-handling pattern to mirror:** Existing `isError` guard renders the same Card-with-rose-border envelope.

**Test pattern:** None new — extends existing Dashboard test if one exists.

**Deviations from analog:** Grid changes from 4 to 5 columns — verify Tailwind breakpoint behavior (CONTEXT.md says Tremor wraps to 3+2 on narrow viewports; planner verifies).

---

### `frontend/src/pages/TraceDetail.tsx` (MODIFY — diagnosis-tag Select)

**Analog (in same file):** Feedback tab at lines 172–186.

**Existing tab content** (lines 172–186):

```typescript
<TabsContent value="feedback" className="mt-4">
  <Card>
    <Title>Feedback for this trace</Title>
    <Text>
      {trace.feedback_rating === 1 ? "User gave thumbs up."
        : trace.feedback_rating === -1 ? "User gave thumbs down."
        : "No feedback recorded yet."}
    </Text>
    <Text className="mt-2 text-xs text-muted-foreground">
      Phase 5 FBCK-05 will surface diagnosis tag + comment here.
    </Text>
  </Card>
</TabsContent>
```

**Required additions:**

```typescript
// Allowed values per FBCK-05 / Phase 1 contract:
const DIAGNOSIS_TAGS = ["Retrieval","PromptAssembly","LLM","CorpusStale","Other"] as const;
type DiagnosisTag = typeof DIAGNOSIS_TAGS[number];

const [tag, setTag] = React.useState<DiagnosisTag | null>(
  (trace.diagnosis_tag as DiagnosisTag | null) ?? null,
);

// Inside the feedback tab Card:
<Select value={tag ?? "none"} onValueChange={(v) => {
  const newTag = v === "none" ? null : (v as DiagnosisTag);
  setTag(newTag);
  // POST /feedback with diagnosis_tag (re-uses existing endpoint; idempotent)
  postFeedback({ trace_id, rating: trace.feedback_rating ?? -1, diagnosis_tag: newTag });
}}>
  <SelectTrigger className="w-48"><SelectValue placeholder="Tag diagnosis" /></SelectTrigger>
  <SelectContent>
    <SelectItem value="none">— none —</SelectItem>
    {DIAGNOSIS_TAGS.map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}
  </SelectContent>
</Select>
```

**Error-handling pattern to mirror:** Existing `useMutation` patterns elsewhere in app (e.g., ThumbsFeedback). On error: toast notification.

**Test pattern:** None — UI extension; functional smoke covered by manual test.

**Deviations from analog:** Adds Select component (already in shadcn-ui). Calls existing `POST /feedback` (no new endpoint).

---

### `frontend/src/components/AppShell.tsx` (MODIFY — Queue nav link)

**Analog (in same file):** existing nav links at lines 16–51.

**NavLink pattern** (lines 28–39):

```typescript
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

**Required addition:** Add a new NavLink between Dashboard and Admin:

```typescript
<NavLink
  to="/dashboard/queue"
  className={({ isActive }) =>
    cn(
      isActive
        ? "font-medium text-foreground"
        : "text-muted-foreground hover:text-foreground",
    )
  }
>
  Queue
</NavLink>
```

**Deviations from analog:** None — straight copy with `/dashboard/queue` path + "Queue" label.

---

### `frontend/src/api/traces.ts` (MODIFY — add 3 fns)

**Analog (in same file):** existing `getTraces` and `getTrace` at lines 21–39.

**ky-based GET pattern** (lines 21–35):

```typescript
export async function getTraces(
  filters: TraceListFilters,
): Promise<TraceListResponse> {
  const searchParams: Record<string, string | number> = {};
  if (filters.query) searchParams.query = filters.query;
  if (filters.since) searchParams.since = filters.since;
  ...
  return _api.get("traces", { searchParams }).json<TraceListResponse>();
}

export async function getTrace(traceId: string): Promise<TraceDetailResponse> {
  return _api.get(`traces/${traceId}`).json<TraceDetailResponse>();
}
```

**Required additions:**

```typescript
export async function getTimeseries(
  window: "1h" | "24h" | "7d" | "30d" = "24h",
): Promise<TimeseriesResponse> {
  return _api.get("traces/timeseries", { searchParams: { window } })
    .json<TimeseriesResponse>();
}

export async function getEvalConfig(): Promise<EvalConfigResponse> {
  return _api.get("admin/eval-config").json<EvalConfigResponse>();
}

export async function markResolved(traceId: string): Promise<FeedbackResolveResponse> {
  return _api.patch(`feedback/${traceId}/resolved`).json<FeedbackResolveResponse>();
}
```

**Error-handling pattern to mirror:** ky's default `retry: { limit: 1 }` (line 17). markResolved is idempotent so retry is safe.

**Test pattern:** None — typed API client; tested transitively through page tests.

**Deviations from analog:** PATCH method (analog only does GET); planner verifies the ky `.patch()` shape.

---

### `frontend/src/types/trace.ts` (MODIFY — add 4 types)

**Analog (in same file):** existing `TraceListItem`, `TraceDetailResponse` at lines 5–47.

**Interface declaration pattern** (lines 5–18):

```typescript
export interface TraceListItem {
  trace_id: string;
  started_at: string;       // ISO8601
  query_text: string;
  latency_ms: number;
  estimated_cost_usd: number;
  faithfulness: number | null;
  feedback_rating: 1 | -1 | null;
}
```

**Required additions:**

```typescript
export interface TimeseriesBucket {
  bucket_start: string;                 // ISO8601
  latency_p50: number | null;
  latency_p95: number | null;
  cost_sum: number;
  faithfulness_mean: number | null;     // null = no eval-scored traces in bucket
  feedback_down_ratio: number | null;   // null = no rated traces in bucket
  request_count: number;
}

export interface TimeseriesResponse {
  window: "1h" | "24h" | "7d" | "30d";
  buckets: TimeseriesBucket[];
}

export interface EvalConfigResponse {
  threshold: number;
  judge_prompt_version: string;
  judge_model: string;
  calibration_date: string | null;
}

export interface FeedbackResolveResponse {
  trace_id: string;
  resolved_at: string;
}
```

**Deviations from analog:** None — pure mirror of new Pydantic schemas.

---

### `frontend/src/router.tsx` (MODIFY — add /dashboard/queue route)

**Analog (in same file):** existing routes at lines 9–20.

**Route declaration pattern** (lines 9–20):

```typescript
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
]);
```

**Required addition:** insert between dashboard and trace detail:

```typescript
{ path: "/dashboard/queue", element: <Queue /> },
```

Plus import: `import { Queue } from "@/pages/Queue";`

**Deviations from analog:** None.

---

## Shared Patterns

### Pattern: `extra="forbid"` strict-mode on every Pydantic schema

**Source:** `tracer_ai/api/schemas.py:39` (`ChatRequest`) — every BaseModel includes `model_config = ConfigDict(extra="forbid")`.
**Apply to:** All new schemas in Phase 5 (`FeedbackResolveResponse`, `EvalConfigResponse`, `TimeseriesBucket`, `TimeseriesResponse`, `EvalScores`).

```python
model_config = ConfigDict(extra="forbid")
```

Rationale (D-2.39 + docs/api.md D-25): unknown fields are a Tampering bug class; reject at validation time.

---

### Pattern: SDK isolation + allowlist enforcement

**Source:** `tracer_ai/rag/llm.py` module docstring (lines 1–7) + `tests/test_llm_adapter.py:213-239` (anti-pattern grep).
**Apply to:** `tracer_ai/eval/llm_judge.py` — only second permitted `from anthropic` site.

Pattern excerpt (`tests/test_llm_adapter.py:226-229`):

```python
allowlist = {
    (pkg / "rag" / "llm.py").resolve(),
    (pkg / "eval" / "llm_judge.py").resolve(),
}
```

The pre-commit `tests/test_anti_patterns.py` grep gate already includes both files — Phase 5 just lights up the second slot.

---

### Pattern: structlog event names + structured kwargs

**Source:** `tracer_ai/api/feedback.py:76-80` and `tracer_ai/tracer/exporters/postgres.py:175-179`.
**Apply to:** All Phase 5 modules. NO `print()` outside `tracer_ai/cli/__main__.py` (D-2.37 anti-pattern grep).

```python
log.info(
    "feedback_recorded",
    trace_id=str(body.trace_id),
    rating=body.rating,
)
```

Phase 5 event names to add: `eval.scored`, `eval.judge_failed`, `eval.dispatcher_drain_incomplete`, `eval.enqueue_swallowed`, `feedback_resolved`, `calibration.label_appended`, `calibration.threshold_swept`.

---

### Pattern: try/finally cancellation safety per stage

**Source:** `tracer_ai/rag/pipeline.py:192-237` — every span emit lives inside try/finally; root span emitted in outermost finally.
**Apply to:** `tracer_ai/eval/dispatcher.py` — judge call wrapped in try/except/finally; failure span emit lives in the finally block per D-5.07.

```python
try:
    chunks = await self.retriever.retrieve(q_emb, self.top_k)
except BaseException:
    retrieve_failed = True
    raise
finally:
    # always emit the span, even on cancellation
    try:
        await self.writer.emit(Span(...))
    finally:
        if retrieve_failed:
            await self._emit_root(...)
```

---

### Pattern: never-raise emit (CLAUDE.md "tracer failures must NEVER fail user requests")

**Source:** `tracer_ai/tracer/exporters/postgres.py:45-54` (`PostgresTraceWriter.emit`).
**Apply to:** All Phase 5 dispatcher / judge code paths. Every layer wraps in try/except (Pitfall #3).

```python
try:
    await self._queue.put(span)
except Exception as exc:
    log.warning("tracer.emit_swallowed", error=str(exc), span_name=span.name)
```

---

### Pattern: TanStack Query queryKey spread for filter invalidation

**Source:** `frontend/src/pages/Dashboard.tsx:56-67`.
**Apply to:** `frontend/src/pages/Queue.tsx` (queue tab + threshold), Dashboard (timeseries window).

```typescript
const queryKey = React.useMemo(
  () => ["traces", filters.query ?? "", filters.since ?? "", ...],
  [filters],
);
```

D-4.18 invariant: `staleTime: 0` for any view where freshness drives the user story (queue, dashboard); spread filter primitives as separate array members (RESEARCH Pitfall 7).

---

### Pattern: Mock fixtures via SimpleNamespace + monkeypatch.setattr

**Source:** `tests/test_llm_adapter.py:42-119`.
**Apply to:** `tests/test_llm_judge.py` (NEW) — same `_FakeAsyncAnthropic`, but `messages.create(...)` returns a SimpleNamespace with `.content=[SimpleNamespace(type="tool_use", input={...})]` and `.usage=SimpleNamespace(input_tokens=N, output_tokens=N)`.

```python
def _patch_async_anthropic(monkeypatch: pytest.MonkeyPatch, stream: _FakeStream) -> None:
    import tracer_ai.rag.llm as llm_mod
    def _factory(*_args: Any, **_kwargs: Any) -> _FakeAsyncAnthropic:
        return _FakeAsyncAnthropic(stream)
    monkeypatch.setattr(llm_mod, "AsyncAnthropic", _factory)
```

Phase 5 test mocks the `tools` parameter being honored: tool_choice forced, response.content[0].input is the dict.

---

### Pattern: autouse env fixture for module-level fail-fast settings

**Source:** `tests/test_llm_adapter.py:30-36`.
**Apply to:** All Phase 5 unit tests that import any module touching `tracer_ai.config`.

```python
@pytest.fixture(autouse=True)
def _configured_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://t:t@db:5432/t")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("VOYAGE_API_KEY", "pa-test")
    sys.modules.pop("tracer_ai.config", None)
    sys.modules.pop("tracer_ai.rag.llm", None)
```

---

### Pattern: dict-return from store layer + Pydantic construction at route layer

**Source:** `tracer_ai/tracer/store.py:1-46` module docstring + `tracer_ai/api/traces.py:96-99`.
**Apply to:** `tracer_ai/tracer/store.py:timeseries()` (NEW) — returns `list[dict[str, Any]]`; `tracer_ai/api/traces.py` constructs `TimeseriesBucket(**row)`.

Module-deps DAG (D-2.27): `tracer_ai/tracer/` MUST NOT import `tracer_ai/api/`. Pre-commit `import_cycle_guard.py` enforces.

---

### Pattern: alembic migration shape (additive + reversible)

**Source:** `alembic/versions/0002_traces_denorm.py` (entire file).
**Apply to:** `alembic/versions/0003_feedback_resolved.py` (NEW).

- `revision: str = "NNNN"`, `down_revision = "PREV"`, `branch_labels = None`, `depends_on = None`.
- `IF NOT EXISTS` / `IF EXISTS` everywhere.
- Indexes created in upgrade; dropped in downgrade in reverse order.
- D-2.17: never edit prior migrations.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `tracer_ai/eval/prompts.py` (NEW judge prompt builder) | Backend / Utility | passthrough | `tracer_ai/rag/prompt.py` (assemble) is structurally similar but the XML-delimited untrusted-content pattern (ADR 008) and tool-use schema declaration are new — RESEARCH.md §"Pattern 1" provides a concrete skeleton planner can use. |
| `tracer_ai/tracer/context.py` (full implementation) | Backend / Tracer | passthrough | Currently a 7-line stub; no in-repo analog. Pattern derives from stdlib `contextvars` directly. RESEARCH.md §"Pattern 3" provides the reference implementation. |
| `docs/eval/calibration_set.yaml` (NEW labeled-trace YAML) | Docs / Data | passthrough | No YAML data files exist in repo today. RESEARCH.md §"Pattern 7: Calibration YAML Format" provides the schema. |

---

## Metadata

**Analog search scope:**
- `tracer_ai/` (all subdirs)
- `tests/` (all subdirs, especially `tests/integration/` and `tests/unit/tracer/`)
- `alembic/versions/`
- `frontend/src/`

**Files scanned:** 38 backend Python files, 38 frontend TS/TSX files, 2 alembic migrations, 35 test files.

**Pattern extraction date:** 2026-05-07

## PATTERN MAPPING COMPLETE
