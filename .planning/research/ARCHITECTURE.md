# Architecture Research

**Domain:** Observable RAG chatbot with custom OTel-aligned semantic observability
**Researched:** 2026-05-04
**Confidence:** HIGH (OTel GenAI conventions verified via Context7; FastAPI BackgroundTasks verified; Python OTel SDK verified)

## Standard Architecture

### System Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                 FRONTEND  (Vite + React 18 + TS)                 │
│  ┌─────────────┐  ┌──────────────────┐  ┌──────────────────────┐ │
│  │   Chat UI   │  │  Trace Explorer  │  │  Corpus Admin / Eval │ │
│  └──────┬──────┘  └────────┬─────────┘  └──────────┬───────────┘ │
└─────────┼──────────────────┼─────────────────────────┼───────────┘
          │  HTTP/JSON       │  HTTP/JSON              │  HTTP/JSON
          ▼                  ▼                         ▼
┌──────────────────────────────────────────────────────────────────┐
│                      FASTAPI BACKEND                             │
│  api/                                                            │
│  ┌────────────┐  ┌──────────────┐  ┌────────────┐  ┌──────────┐ │
│  │  chat.py   │  │  traces.py   │  │ feedback.py│  │ admin.py │ │
│  └─────┬──────┘  └──────────────┘  └─────┬──────┘  └─────┬────┘ │
│        │  calls                          │               │       │
│        ▼                                 │               ▼       │
│  rag/pipeline.py  (sync request path)    │          corpus/      │
│  ┌──────────────────────────────────┐    │          ingest       │
│  │ retrieve → prompt_assemble       │    │                       │
│  │         → llm_call               │    │                       │
│  │         (each step emits a span) │    │                       │
│  └────────────┬─────────────────────┘    │                       │
│               │ emit spans               │                       │
│               ▼                          │                       │
│  tracer/  (context propagation + store)  │                       │
│  ┌──────────────────────────────────┐    │                       │
│  │ span.py  context.py  store.py    │◄───┘                       │
│  │ exporters/postgres.py            │                            │
│  └──────────────────────────────────┘                            │
│               │ asyncio.Queue.put_nowait (non-blocking)          │
│               │ + background_tasks.add_task (post-response eval) │
│               ▼                                                  │
│  eval/llm_judge.py  (async, post-response)                       │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │ Writes rag.eval span onto existing trace  (Haiku call)   │    │
│  └──────────────────────────────────────────────────────────┘    │
└────────────┬───────────────────────────────────────┬─────────────┘
             │  vector query                          │  SQL (JSONB)
             ▼                                        ▼
┌───────────────────────┐              ┌──────────────────────────┐
│  Vector Store         │              │  Trace DB (Postgres)     │
│  (pgvector or Qdrant) │              │  traces / spans /        │
│                       │              │  feedback / regression   │
└───────────────────────┘              └──────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| `api/chat.py` | Accept POST /chat, own sync request path, fire async eval after response | FastAPI route + `BackgroundTasks` |
| `api/traces.py` | Read-side for dashboard (list + filter, detail) | FastAPI route + Pydantic response models |
| `api/feedback.py` | Ingest user thumbs-up/down + free-text comments | FastAPI route + `eval/feedback.py` |
| `api/admin.py` | Corpus listing, re-index trigger, chunking config | FastAPI route + `corpus/` |
| `rag/pipeline.py` | Orchestrate retrieve → prompt_assemble → llm_call; wrap each in child span | Async orchestration; pure Python |
| `rag/retriever.py` | `Retriever` Protocol + pgvector/Qdrant adapter | Typed Protocol + adapter |
| `rag/embedder.py` | `Embedder` Protocol + Voyage/sentence-transformers adapter | Typed Protocol + adapter |
| `rag/prompt.py` | Assemble final prompt (citation formatting) | Pure function |
| `rag/llm.py` | `LLM` Protocol + Anthropic SDK adapter; return usage/cost | Typed Protocol + adapter |
| `tracer/span.py` | Span dataclass with OTel-aligned + RAG-specific attributes | Frozen dataclass + attribute name constants |
| `tracer/context.py` | `start_span`, `current_span`, `set_span_in_context`; root span lifecycle | Wraps OTel `opentelemetry-api` context |
| `tracer/store.py` | `TraceStore` Protocol: `write_span`, `get_trace`, `list_traces` | Typed Protocol |
| `tracer/exporters/postgres.py` | Async JSONB writes via `asyncio.Queue` buffer | Async batch consumer |
| `eval/llm_judge.py` | Faithfulness + relevance via Haiku; async; writes `rag.eval` span | Anthropic SDK call wrapped in span |
| `eval/feedback.py` | Persist user feedback against `trace_id` | Postgres insert |
| `eval/regression.py` | Load curated query set, run pipeline, report pass/fail | Async iteration over query set |
| `corpus/loader.py` | Pull/parse Claude docs (markdown + HTML) | Custom parser |
| `corpus/chunker.py` | Configurable chunking (markdown-header-aware default) | Markdown AST walker |
| `corpus/ingest_cli.py` | Batch ingest entry point | Click/Typer CLI |
| `cli/__main__.py` | Operator CLI: `eval`, `ingest`, ops | Click/Typer |
| `config.py` | Pydantic Settings; all tunables; imported by all modules | `pydantic-settings` |
| `errors.py` (**ADDITION vs PRD §8**) | Custom exception hierarchy; prevents raw SDK exceptions reaching api/ | Exception classes |

## Recommended Project Structure

```
tracer_ai/
├── tracer/                # Core observability primitives
│   ├── span.py            # Span dataclass + OTel attribute name constants
│   ├── context.py         # Context propagation, span emission helpers
│   ├── store.py           # TraceStore Protocol
│   └── exporters/
│       ├── __init__.py    # Protocol-based exporter loading (ADDITION)
│       └── postgres.py    # Async-queue-backed JSONB exporter
├── rag/                   # The RAG pipeline (every step is a span)
│   ├── retriever.py       # Retriever Protocol + adapter
│   ├── embedder.py        # Embedder Protocol + Voyage/local adapter
│   ├── prompt.py          # Prompt assembly with citation formatting
│   ├── llm.py             # LLM Protocol + Anthropic adapter
│   └── pipeline.py        # Orchestration (the single instrumented path)
├── eval/                  # Quality measurement
│   ├── llm_judge.py       # Faithfulness + relevance via Claude Haiku
│   ├── feedback.py        # Manual feedback ingestion
│   └── regression.py      # Curated query set runner
├── corpus/                # Document ingestion + indexing
│   ├── loader.py          # Pull/parse Claude docs
│   ├── chunker.py         # Configurable chunking
│   └── ingest_cli.py
├── api/                   # FastAPI app
│   ├── main.py
│   ├── chat.py
│   ├── traces.py
│   ├── feedback.py
│   └── admin.py
├── cli/                   # Operator CLI (eval, ingest, ops)
│   └── __main__.py
├── errors.py              # ADDITION: exception hierarchy
└── config.py              # Pydantic Settings, env-driven

frontend/                  # Vite + React + TS + Tailwind + shadcn/ui
├── src/
│   ├── routes/
│   │   ├── chat/
│   │   ├── dashboard/
│   │   └── admin/
│   ├── components/
│   ├── api/               # Typed client for FastAPI
│   └── lib/

infra/
├── docker-compose.yml
├── Dockerfile.backend
└── Dockerfile.frontend
```

### Structure Rationale

- **`tracer/`:** Foundation — imports only `config`. All instrumentation primitives live here. Centralizes OTel attribute name constants (since all GenAI conventions are experimental and may rename, one file to update if the spec changes).
- **`rag/`:** Imports `tracer/` and `config`. Each pipeline component lives behind a typed `Protocol`, satisfying PRD modularity constraint.
- **`eval/`:** Imports `rag/`, `tracer/`. Async eval runs after request; failure must not affect user response.
- **`corpus/`:** Imports `rag/embedder` only. Document ingestion is independent of request-time path.
- **`api/`:** Outermost layer. Imports `rag/`, `eval/`, `tracer/`, `corpus/`. Owns request lifecycle and `BackgroundTasks` dispatch.
- **`errors.py`:** Cross-cutting. Wraps SDK exceptions before they reach `api/`. Prevents leaking provider-specific error types to clients.

### Dependency Graph (no cycles)

```
config.py               (leaf)
    ▲
tracer/                 (foundation — imports config only)
    ▲
rag/                    (imports tracer/, config)
    ▲
eval/                   (imports rag/, tracer/, config)
corpus/                 (imports rag/embedder, config)
    ▲
api/                    (outermost — imports rag/, eval/, tracer/, corpus/)
cli/                    (imports eval/, corpus/, config)
```

## Architectural Patterns

### Pattern 1: OTel-aligned span dataclass with custom backend

**What:** Use OTel Python SDK (`opentelemetry-api` for context propagation; `opentelemetry-sdk` for `Tracer`/`Span` API), but write to a custom Postgres exporter rather than an OTel collector.

**When to use:** When you need OTel portability (export to Langfuse, Phoenix, Datadog later) but want full control over storage schema and dashboard during the build.

**Trade-offs:**
- ✅ Portable to OTel collectors with one exporter swap
- ✅ Full control over storage schema and indexing
- ⚠️ All GenAI conventions are Development/Experimental — naming may shift; centralize all attribute names as constants in `tracer/span.py`

**Example:**
```python
# tracer/span.py
GEN_AI_PROVIDER_NAME = "gen_ai.provider.name"   # USE THIS
# GEN_AI_SYSTEM = "gen_ai.system"               # DEPRECATED — do not use
GEN_AI_OPERATION_NAME = "gen_ai.operation.name"
GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
GEN_AI_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
GEN_AI_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"

# Custom RAG namespace (no official rag.* namespace exists)
RAG_RETRIEVED_CHUNKS = "rag.retrieved_chunks"
RAG_RETRIEVAL_SCORE_MEAN = "rag.retrieval.score.mean"
RAG_PROMPT_TEMPLATE_ID = "rag.prompt_template.id"
RAG_EVAL_FAITHFULNESS = "rag.eval.faithfulness"
RAG_EVAL_RELEVANCE = "rag.eval.relevance"
```

### Pattern 2: Non-blocking trace write via asyncio.Queue

**What:** In hot path, `queue.put_nowait(span)` (microseconds). A background consumer drains the queue and writes batched JSONB upserts to Postgres.

**When to use:** When you have a strict trace-overhead budget (≤100ms) and can tolerate a small probability of span loss on crash.

**Trade-offs:**
- ✅ Sub-millisecond hot path
- ✅ Batched writes amortize Postgres latency
- ⚠️ Span loss on crash — acceptable for portfolio/dev; mitigated by `maxsize` guard and lifespan flush

**Example:**
```python
# tracer/exporters/postgres.py
class PostgresExporter:
    def __init__(self, dsn: str, maxsize: int = 1000):
        self._queue: asyncio.Queue[Span] = asyncio.Queue(maxsize=maxsize)
        self._task: asyncio.Task | None = None

    def emit(self, span: Span) -> None:
        try:
            self._queue.put_nowait(span)
        except asyncio.QueueFull:
            logger.warning("trace queue full — dropping span", extra={"trace_id": span.trace_id})

    async def _consume(self) -> None:
        batch: list[Span] = []
        while True:
            span = await self._queue.get()
            batch.append(span)
            if len(batch) >= 50 or self._queue.empty():
                await self._flush(batch)
                batch.clear()
```

### Pattern 3: Async LLM-as-judge via FastAPI BackgroundTasks

**What:** Capture OTel context snapshot before ending the root span. Pass the snapshot to a `BackgroundTasks` handler that re-attaches it, runs the Haiku call, and emits a `rag.eval` span as a child of the root span.

**When to use:** When eval must run after the response is flushed and must NEVER block or fail user requests.

**Trade-offs:**
- ✅ Eval failure cannot reach the user
- ✅ Single Docker service (no Celery/Redis)
- ⚠️ Race risk: eval writes before root trace record committed → mitigate by writing root span via the same queue, before adding the BackgroundTask
- ⚠️ Context propagation breaks across `asyncio.create_task` — `BackgroundTasks` is the idiomatic FastAPI pattern that handles this cleanly

**Example:**
```python
# api/chat.py
@router.post("/chat")
async def chat(req: ChatRequest, background_tasks: BackgroundTasks) -> ChatResponse:
    with start_root_span("rag.request") as root:
        result = await pipeline.run(req.query)
        ctx_snapshot = otel_context.get_current()  # capture BEFORE root.end()
    # root span ended; trace_id committed via queue flush
    background_tasks.add_task(
        run_eval_async, trace_id=root.trace_id, ctx=ctx_snapshot,
        query=req.query, answer=result.answer, chunks=result.chunks,
    )
    return ChatResponse(answer=result.answer, trace_id=root.trace_id, ...)
```

## Data Flow

### Request Flow

```
Browser → POST /chat
    ▼ api/chat.py
    start_root_span("rag.request")   [token = context.attach(ctx)]
    ▼ rag/pipeline.py
    ├── start_as_current_span("rag.retrieve")    → embed query → vector search
    ├── start_as_current_span("rag.prompt_assemble") → build final prompt
    └── start_as_current_span("rag.llm_call")   → Anthropic API → answer + usage
    ▼ api/chat.py (back from pipeline)
    ctx_snapshot = otel_context.get_current()   [BEFORE root.end()]
    root.end(); context.detach(token)
    queue.put_nowait(span_batch)                 [non-blocking, ≤100ms]
    background_tasks.add_task(run_eval_async, trace_id, ..., ctx_snapshot)
    ▼ HTTP 200 → Browser
    [Background, after response flushed]
    run_eval_async:
        context.attach(ctx_snapshot)
        start_as_current_span("rag.eval")  [parents to rag.request via snapshot]
        Haiku API call → faithfulness + relevance
        queue.put_nowait(eval_span)
        store.update_eval_scores(trace_id, scores)
        context.detach(token)
        [on exception: log + suppress; never re-raise]
```

### Feedback Flow

```
Browser → POST /feedback {trace_id, rating, comment}
    ▼ api/feedback.py → eval/feedback.py
    INSERT INTO feedback (...); if rating='down' flag trace
    ▼ HTTP 201
```

### Key Data Flows

1. **Sync request path:** Browser → FastAPI → pipeline (3 instrumented stages) → Anthropic API → response.
2. **Async eval path:** After response flush, BackgroundTask attaches captured context, calls Haiku, writes `rag.eval` span as child of `rag.request`.
3. **Async trace write path:** Every span goes through `queue.put_nowait()`; a single consumer task drains to Postgres in batches.
4. **Feedback path:** Independent of trace pipeline; writes to `feedback` table keyed by `trace_id`.
5. **Eval CLI path:** Reads curated regression set → calls `pipeline.run()` for each query (which emits its own traces) → aggregates pass/fail.

## OTel GenAI Semantic Conventions — Status as of 2026

**ALL GenAI semantic conventions are Development/Experimental.** No stable GenAI attributes exist.

| Attribute | Status | Notes |
|-----------|--------|-------|
| `gen_ai.operation.name` | Development | `"chat"` on llm_call; `"embeddings"` on embed; `"retrieval"` on retrieve |
| `gen_ai.provider.name` | Development | `"anthropic"` — USE THIS, not `gen_ai.system` |
| `gen_ai.system` | **DEPRECATED** | Replaced by `gen_ai.provider.name` |
| `gen_ai.request.model` | Development | `"claude-sonnet-4-5"` / `"claude-haiku-*"` |
| `gen_ai.response.model` | Development | From response, may differ from request |
| `gen_ai.usage.input_tokens` | Development | int |
| `gen_ai.usage.output_tokens` | Development | int |
| `gen_ai.retrieval.query.text` | Development | Opt-in; embedding query text |
| `gen_ai.retrieval.documents` | Development | Opt-in; JSON array `[{id, score, ...}]` |

**No official `rag.*` namespace exists.** Custom attributes required for `rag.retrieved_chunks`, `rag.retrieval.score.{mean,min}`, `rag.prompt_template.id`, `rag.eval.{faithfulness,relevance,judge_model,judge_cost_usd}`.

**Span attribute size limit:** OTel backends limit attributes to 4–16KB. Full prompt text (8K+ tokens) must NOT be stored as span attributes — use OTel span events (`gen_ai.client.inference.operation.details`) for full payloads, plus an unlimited Postgres JSONB column.

## Async Eval Architecture Decision

**Chosen: FastAPI `BackgroundTasks`.**

| Option | Verdict |
|--------|---------|
| **FastAPI BackgroundTasks** | ✅ USE — runs after response in same event loop; zero added Docker services; eval failure cannot touch the request |
| `asyncio.create_task` | Valid but `BackgroundTasks` is the idiomatic FastAPI pattern and runs reliably after response flush |
| Celery + Redis | ❌ Overkill for local Compose; adds two services; no retry semantics needed for best-effort eval |
| RQ + Redis | ❌ Same objection as Celery |
| asyncio.Queue for the eval call | ❌ Queue is right for trace WRITE path (microsecond cost); wrong for eval (Haiku call takes 1–3s) |

The `asyncio.Queue` pattern is reserved for the **trace write path** (≤100ms budget); `BackgroundTasks` handles the **eval call path** (post-response, seconds-long, can fail silently).

## Build Order Implications

```
Phase −1: Design artifacts only — ADRs, diagrams, wireframes (no code)
Phase 0:  config.py + infra/ (docker-compose) + api/main.py skeleton
Phase 1:  tracer/span.py + tracer/context.py + tracer/store.py (Protocol; no exporter yet)
          → rag/* (Protocols + adapters)
          → corpus/* + ingest CLI
          → api/chat.py + api/admin.py
Phase 2:  tracer/exporters/postgres.py (async queue writer)
          → Instrument pipeline.py (wrap each stage in start_as_current_span)
          → api/traces.py + dashboard list/detail
Phase 3:  eval/llm_judge.py + async wiring in api/chat.py
          → eval/feedback.py + api/feedback.py + bad-answer queue
          → time-series charts on dashboard
Phase 4:  eval/regression.py + cli/__main__.py
Phase 5:  Polish (README, demo path, cost widget)
```

**Critical ordering constraint:** `tracer/span.py` and `tracer/context.py` must exist before Phase 2 instrumentation. Pipeline code in Phase 1 should import the tracer module but call no-op context managers if the store is not yet wired — this way Phase 1 is unblocked and Phase 2 is additive instrumentation only.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| Single user (target) | Local Docker Compose; single Postgres with `pgvector` extension; FastAPI uvicorn worker |
| 10+ concurrent users | Add Postgres connection pool (`asyncpg.Pool`); raise `asyncio.Queue` `maxsize`; consider separate Postgres instance for traces |
| 100+ users | Migrate trace store to ClickHouse; vector store to Qdrant; add Redis for response cache |
| Multi-tenant | Out of scope for v1 — flagged in PRD; ADR for future direction only |

### Scaling Priorities

1. **First bottleneck:** Postgres write contention as trace volume grows. Mitigate with batched JSONB upserts and partitioning by trace creation date.
2. **Second bottleneck:** Anthropic API rate limits under regression CLI runs. Mitigate with concurrency cap in `eval/regression.py` (semaphore).

## Anti-Patterns

### Anti-Pattern 1: Calling SDKs directly from `api/` or `pipeline/`

**What people do:** `from anthropic import Anthropic; client = Anthropic(); ...` inside `api/chat.py`.
**Why it's wrong:** Couples request handling to a specific provider; impossible to swap; impossible to mock cleanly in tests; no place to attach instrumentation without bloating the route.
**Do this instead:** Every external dependency lives behind a typed `Protocol` in `rag/` (or `tracer/exporters/`). The adapter is the only place that imports the SDK.

### Anti-Pattern 2: Storing full prompt text in OTel span attributes

**What people do:** `span.set_attribute("prompt", full_prompt_text)` — silently truncated by the OTel backend.
**Why it's wrong:** Span attributes are limited to 4–16KB; truncation loses exactly the data you need to debug a bad answer.
**Do this instead:** Use OTel span events (`gen_ai.client.inference.operation.details`) for prompts/responses; mirror to a Postgres JSONB column with no size limit.

### Anti-Pattern 3: Failing user requests when eval fails

**What people do:** `await llm_judge.score(...)` inline in the request handler.
**Why it's wrong:** A judge timeout / rate-limit / bug would now fail user-visible chat requests — exactly the opposite of "observability of the observability."
**Do this instead:** Run eval via `BackgroundTasks` after response flush. Wrap the eval call in a broad `try/except` that logs + suppresses any exception. The user never knows eval ran.

### Anti-Pattern 4: Forgetting context propagation across BackgroundTasks

**What people do:** `background_tasks.add_task(run_eval, trace_id, ...)` without snapshotting OTel context — eval span becomes orphaned (root) instead of child of `rag.request`.
**Why it's wrong:** The trace explorer shows two unrelated traces; faithfulness/relevance scores can't be drilled-into from the original request.
**Do this instead:** Snapshot `otel_context.get_current()` BEFORE the root span ends; re-attach it inside the BackgroundTask before starting the `rag.eval` span.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Anthropic API (Sonnet 4.5) | `rag/llm.py` adapter behind `LLM` Protocol | Use `prompt-caching` for system prompt; record `usage` for cost telemetry |
| Anthropic API (Haiku) | `eval/llm_judge.py`; same SDK, different model | Cheaper for eval; cost recorded as `rag.eval.judge_cost_usd` |
| Voyage AI | `rag/embedder.py` adapter behind `Embedder` Protocol | Requires `VOYAGE_API_KEY`; sentence-transformers fallback for offline dev |
| Postgres + pgvector | `rag/retriever.py` (vectors) + `tracer/exporters/postgres.py` (traces) | Single instance, two responsibilities; async via `asyncpg` |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| `api/` ↔ `rag/` | Async function call | `pipeline.run()` returns `PipelineResult` — never raw provider objects |
| `api/` ↔ `eval/` | `BackgroundTasks.add_task` | Eval runs post-response; never blocks |
| `rag/pipeline` ↔ `tracer/` | Async context managers (`async with start_span(...)`) | Span emission is the only side effect |
| `tracer/store` ↔ `tracer/exporters/postgres` | Protocol implementation | Swap to OTel collector exporter possible without changing tracer/ |
| `eval/regression` ↔ `rag/pipeline` | Direct function call | Regression set runs the same code path as the chat API |

## Risks Specific to "Every Stage Emits a Span"

| Risk | Phase | Mitigation |
|------|-------|------------|
| Context snapshot not captured before `root.end()` — eval span becomes orphan | Phase 3 | Snapshot `otel_context.get_current()` before `finally: root.end()`; verify in trace explorer |
| `asyncio.Queue` fills under burst (regression CLI runs all cases concurrently) | Phase 2 | `maxsize=1000`; `put_nowait` logs drops at WARNING; lifespan shutdown flushes |
| Eval span appearing as root (orphaned) | Phase 3 | Test: trace explorer must show `rag.eval` as child of `rag.request` |
| Large prompt text silently truncated in OTel attributes | Phase 2 | Use span events for payloads >1KB; JSONB column for unlimited storage |
| `gen_ai.system` → `gen_ai.provider.name` migration confusing future OTel exporter | Phase 2 | Use `gen_ai.provider.name` from day one; constant in `tracer/span.py` |
| BackgroundTask eval race: eval writes before root trace record committed | Phase 3 | Write root span record in the same synchronous queue flush before returning response |
| All conventions experimental — naming drift | Ongoing | All attribute names as constants in `tracer/span.py`; one-file update if spec changes |

## Sources

- OpenTelemetry semantic conventions repository (via Context7) — `gen_ai.*` attribute status and naming
- FastAPI documentation (via Context7) — `BackgroundTasks` post-response semantics
- OpenTelemetry Python SDK documentation (via Context7) — context propagation, `Tracer`/`Span` API
- tracer-ai foundation PRD §8 (module layout) and §11 (phased build plan)

---
*Architecture research for: Observable RAG chatbot with custom OTel-aligned semantic observability*
*Researched: 2026-05-04*
