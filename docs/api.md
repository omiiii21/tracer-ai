# API Contract

The FastAPI backend exposes 7 endpoints. All request/response bodies are Pydantic v2 models with `model_config = ConfigDict(extra="forbid")` — silently-accepted unknown fields are a Tampering bug class we close at the schema layer (Pitfall E / threat T-01-06-01). The schemas in this file are authoritative until Phase 3 RAG-05 / CHAT-* / ADMN-* ships; at that point `tracer_ai/api/schemas.py` becomes source-of-truth and this file is regenerated from it. FastAPI auto-emits `/openapi.json` from the runtime Pydantic models — no hand-maintained OpenAPI YAML lives in this repo (per [D-25](../.planning/phases/01-research-design-artifacts/01-CONTEXT.md)). All Pydantic blocks below assume the same imports at the top of `tracer_ai/api/schemas.py`:

```python
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
```

`trace_id` is a `UUID` everywhere — matches `traces.id UUID PRIMARY KEY` in [data-model.md](./data-model.md) and the `trace_id` column in [ADR 004](./decisions/004-trace-storage.md).

## Common Error Envelope

Every error response from every endpoint conforms to the `ErrorResponse` shape below. `error_code` is a `SCREAMING_SNAKE_CASE` machine-readable token; `message` is a human-readable summary; `details` carries optional per-field validation errors; `request_id` is the per-request UUID also written to the `rag.request` root span (see [trace-schema.md](./trace-schema.md)) so an operator can pivot from a failed API call directly into the trace explorer.

```python
class ErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str | None = None       # for input-validation errors
    message: str

class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    error_code: Annotated[str, Field(pattern=r"^[A-Z_]+$")]
    message: str
    details: list[ErrorDetail] = []
    request_id: UUID
```

| Status | error_code examples | When |
|--------|---------------------|------|
| 400    | `INVALID_REQUEST`, `VALIDATION_FAILED` | Pydantic validation failed |
| 404    | `TRACE_NOT_FOUND`, `CHUNK_NOT_FOUND` | Resource missing |
| 422    | `UNPROCESSABLE_ENTITY` | Semantic validation failed (e.g., rating not in {-1, 1}) |
| 429    | `RATE_LIMITED` | Upstream Anthropic / Voyage rate limit |
| 500    | `INTERNAL_ERROR` | Unhandled server error |
| 503    | `UPSTREAM_UNAVAILABLE` | Anthropic / Voyage / Postgres outage |

## POST /chat

Submit a query; receive an answer with cited chunks and a `trace_id` for the trace explorer.

**Request schema:**

```python
class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: Annotated[str, Field(min_length=1, max_length=4000)]
    session_id: UUID | None = None  # for within-session memory; None starts a new session
```

**Response schema:**

```python
class CitedChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chunk_id: UUID
    doc_id: str
    doc_section: str   # one of the canonical 12 sections from /docs/eval/coverage_set.yaml
    content: str
    score: float       # cosine similarity in [0.0, 1.0]

class ChatResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str
    cited_chunks: list[CitedChunk]
    trace_id: UUID
    latency_ms: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
```

**Example request body:**

```json
{
  "query": "How do I authenticate to the Anthropic Messages API?"
}
```

**Example response body:**

```json
{
  "answer": "Authenticate by setting the x-api-key header on every request to api.anthropic.com. The value is the API key issued by the Anthropic Console; never embed it in client-side code.",
  "cited_chunks": [
    {
      "chunk_id": "11111111-1111-4111-8111-111111111111",
      "doc_id": "claude-docs/authentication",
      "doc_section": "auth",
      "content": "Set the x-api-key header on every request. The value is your API key from the Anthropic Console.",
      "score": 0.87
    }
  ],
  "trace_id": "550e8400-e29b-41d4-a716-446655440000",
  "latency_ms": 2810,
  "input_tokens": 1240,
  "output_tokens": 96,
  "estimated_cost_usd": 0.00432
}
```

**Error responses:**

| Status | error_code | When |
|--------|------------|------|
| 400    | `INVALID_REQUEST` | empty query, query too long, malformed body |
| 429    | `RATE_LIMITED` | Anthropic upstream rate limit hit |
| 503    | `UPSTREAM_UNAVAILABLE` | Voyage embedder / Anthropic / Postgres unavailable |

## POST /feedback

Record thumbs-up / thumbs-down on a trace, with optional free-text comment and optional `diagnosis_tag` (per-stage failure attribution — Phase 5 FBCK-05 surfaces this in the trace detail UI; the field is reserved at the schema level in Phase 1 so no migration is needed when the UI ships).

**Request schema:**

```python
class FeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trace_id: UUID
    rating: Literal[-1, 1]                         # -1 = down, 1 = up; matches feedback.rating CHECK in data-model.md
    comment: str | None = None
    diagnosis_tag: str | None = None               # Phase 5 FBCK-05 future-stub; allowed values when populated:
                                                   # "Retrieval" | "PromptAssembly" | "LLM" | "CorpusStale" | "Other"
                                                   # Documented in trace-schema.md feedback.user section.
```

`rating` uses `Literal[-1, 1]` to enforce the two-value enum at the schema layer (threat T-01-06-04). The DB layer adds `CHECK (rating IN (-1, 1))` as a second line of defense (see [data-model.md](./data-model.md)). `diagnosis_tag` is intentionally typed as `str | None` not a `Literal` — Phase 5 FBCK-05 finalizes the allowed-values set; locking it now would force a schema migration if the taxonomy changes during calibration.

**Response schema:**

```python
class FeedbackResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    feedback_id: UUID
    created_at: datetime
```

**Example request body:**

```json
{
  "trace_id": "550e8400-e29b-41d4-a716-446655440000",
  "rating": -1,
  "comment": "Wrong chunks retrieved — the answer cites the prompt-caching doc but the question was about authentication."
}
```

**Example response body:**

```json
{
  "feedback_id": "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
  "created_at": "2026-05-04T04:15:55Z"
}
```

**Error responses:**

| Status | error_code | When |
|--------|------------|------|
| 400    | `INVALID_REQUEST` | malformed body |
| 404    | `TRACE_NOT_FOUND` | `trace_id` does not exist |
| 422    | `UNPROCESSABLE_ENTITY` | rating is not in {-1, 1} (also enforced by Pydantic Literal) |

## GET /traces

List traces with optional filters; cursor-paginated. The query parameters below are documented as a single Pydantic model for clarity (Phase 3 ADMN/EXPL routes consume them as individual `Query(...)` parameters in the FastAPI signature).

**Query parameters (`TraceListQuery`):**

```python
class TraceListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str | None = None                                            # substring match on rag.request query_text
    since: datetime | None = None
    until: datetime | None = None
    feedback: Literal["up", "down"] | None = None                       # maps to feedback.rating IN (1) or (-1)
    min_faithfulness: Annotated[float, Field(ge=0.0, le=1.0)] | None = None  # rag.eval span attribute filter
    max_latency_ms: int | None = None                                   # rag.request span latency filter
    limit: Annotated[int, Field(ge=1, le=200)] = 50
    cursor: str | None = None                                           # opaque base64 cursor from previous page's next_cursor
```

**Response schema:**

```python
class TraceListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trace_id: UUID
    started_at: datetime
    query_text: str
    latency_ms: int
    estimated_cost_usd: float
    faithfulness: float | None = None             # None until rag.eval span completes
    feedback_rating: Literal[-1, 1] | None = None # None when no feedback recorded yet

class TraceListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[TraceListItem]
    next_cursor: str | None = None                # None when no further pages
```

**Example response body:**

```json
{
  "items": [
    {
      "trace_id": "550e8400-e29b-41d4-a716-446655440000",
      "started_at": "2026-05-04T04:14:31Z",
      "query_text": "How do I authenticate to the Anthropic Messages API?",
      "latency_ms": 2810,
      "estimated_cost_usd": 0.00432,
      "faithfulness": 0.91,
      "feedback_rating": 1
    },
    {
      "trace_id": "660f9511-f3ac-52e5-b827-557766551111",
      "started_at": "2026-05-04T04:13:02Z",
      "query_text": "What is prompt caching?",
      "latency_ms": 3120,
      "estimated_cost_usd": 0.00501,
      "faithfulness": 0.42,
      "feedback_rating": -1
    }
  ],
  "next_cursor": "eyJvZmZzZXQiOjUwfQ=="
}
```

**Error responses:**

| Status | error_code | When |
|--------|------------|------|
| 400    | `INVALID_REQUEST` | malformed query parameter (e.g., `min_faithfulness=2.0`) |

## GET /traces/{trace_id}

Full trace tree — the root request span plus all child spans plus their oversize payloads (full prompts, full responses, retrieved-chunk content). Spans carry only typed metadata in `attrs`; payloads >4 KB live in `span_payloads` per the convention in [trace-schema.md](./trace-schema.md) and [ADR 004](./decisions/004-trace-storage.md).

**Path parameter:** `trace_id: UUID`.

**Response schema:**

```python
class Span(BaseModel):
    model_config = ConfigDict(extra="forbid")
    span_id: UUID
    parent_span_id: UUID | None
    name: str                          # e.g., "rag.request", "rag.retrieve", "rag.prompt_assemble", "rag.llm_call", "rag.eval"
    started_at: datetime
    ended_at: datetime | None          # None for in-flight spans (rag.eval may be running when fetched)
    attrs: dict[str, object]           # gen_ai.* + rag.* attributes per trace-schema.md

class SpanPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    payload: dict[str, object]         # full prompt / response / retrieved_chunks / eval rationale

class TraceDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trace: TraceListItem
    spans: list[Span]
    payloads: dict[str, SpanPayload]   # key is span_id stringified; only spans with oversize payloads have an entry
```

**Example response body:**

```json
{
  "trace": {
    "trace_id": "550e8400-e29b-41d4-a716-446655440000",
    "started_at": "2026-05-04T04:14:31Z",
    "query_text": "How do I authenticate to the Anthropic Messages API?",
    "latency_ms": 2810,
    "estimated_cost_usd": 0.00432,
    "faithfulness": 0.91,
    "feedback_rating": 1
  },
  "spans": [
    {
      "span_id": "11111111-1111-4111-8111-111111111111",
      "parent_span_id": null,
      "name": "rag.request",
      "started_at": "2026-05-04T04:14:31.000Z",
      "ended_at": "2026-05-04T04:14:33.810Z",
      "attrs": {"gen_ai.operation.name": "chat", "rag.query.text": "How do I authenticate ..."}
    },
    {
      "span_id": "22222222-2222-4222-8222-222222222222",
      "parent_span_id": "11111111-1111-4111-8111-111111111111",
      "name": "rag.retrieve",
      "started_at": "2026-05-04T04:14:31.020Z",
      "ended_at": "2026-05-04T04:14:31.180Z",
      "attrs": {"gen_ai.operation.name": "retrieval", "rag.retrieval.k": 6, "rag.retrieval.score.mean": 0.81}
    }
  ],
  "payloads": {
    "22222222-2222-4222-8222-222222222222": {
      "payload": {"retrieved_chunks": [{"chunk_id": "...", "content": "...", "score": 0.87}]}
    }
  }
}
```

**Error responses:**

| Status | error_code | When |
|--------|------------|------|
| 404    | `TRACE_NOT_FOUND` | `trace_id` does not exist in the `traces` table |

## POST /admin/ingest

Trigger corpus re-ingest as a background job. Either `urls` (an explicit list of HTTPS URLs to crawl) or `source` (a named bundle — currently only `"claude-docs"`) must be provided. The route validates this in code; passing neither (or both) yields a 400.

**Request schema:**

```python
class IngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    urls: list[Annotated[str, Field(pattern=r"^https?://")]] | None = None
    source: Literal["claude-docs"] | None = None
```

**Response schema:**

```python
class IngestResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ingest_job_id: UUID
    status: Literal["queued", "running"]
```

**Example request body:**

```json
{
  "source": "claude-docs"
}
```

**Example response body:**

```json
{
  "ingest_job_id": "cccccccc-dddd-4eee-8fff-000000000000",
  "status": "queued"
}
```

**Error responses:**

| Status | error_code | When |
|--------|------------|------|
| 400    | `INVALID_REQUEST` | neither `urls` nor `source` provided, or both provided |
| 503    | `UPSTREAM_UNAVAILABLE` | Voyage embedder / Postgres unavailable when scheduling job |

## GET /admin/corpus

Current corpus snapshot — chunk count, the embedding model in use, when the corpus was last re-indexed, and a per-doc breakdown. The `embedding_model` and `embedding_model_version` fields here are sourced from the `chunks.embedding_model` / `chunks.embedding_model_version` columns (per [ADR 003](./decisions/003-embedding-provider.md) / D-49 / Pitfall #3); a Phase 3 CORP-04 startup assertion verifies they match the runtime config and refuses to start on mismatch.

**No request body.**

**Response schema:**

```python
class DocSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    doc_id: str
    doc_section: str               # one of the canonical 12 sections
    chunk_count: int
    last_indexed_at: datetime

class CorpusStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chunk_count: int
    embedding_model: str           # e.g., "voyage-code-3"
    embedding_model_version: str   # pinned snapshot identifier
    last_indexed_at: datetime | None
    docs: list[DocSummary]
```

**Example response body:**

```json
{
  "chunk_count": 4218,
  "embedding_model": "voyage-code-3",
  "embedding_model_version": "voyage-code-3@2025-09",
  "last_indexed_at": "2026-05-03T22:04:11Z",
  "docs": [
    {
      "doc_id": "claude-docs/authentication",
      "doc_section": "auth",
      "chunk_count": 18,
      "last_indexed_at": "2026-05-03T22:04:11Z"
    },
    {
      "doc_id": "claude-docs/prompt-caching",
      "doc_section": "prompt-caching",
      "chunk_count": 42,
      "last_indexed_at": "2026-05-03T22:04:11Z"
    }
  ]
}
```

**Error responses:**

| Status | error_code | When |
|--------|------------|------|
| 503    | `UPSTREAM_UNAVAILABLE` | Postgres unavailable |

## PATCH /admin/chunking-config

Update the chunker's `chunk_size` and/or `overlap` parameters. Both fields are optional — a PATCH with one field updates only that field. The new values apply on the **next** ingest / re-index — existing chunks are not retroactively re-chunked. (To force a re-chunk, follow this PATCH with `POST /admin/ingest`.)

**Request schema:**

```python
class ChunkingConfigPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chunk_size: Annotated[int, Field(ge=100, le=4000)] | None = None
    overlap: Annotated[int, Field(ge=0, le=500)] | None = None
```

**Response schema:**

```python
class ChunkingConfigResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chunk_size: int
    overlap: int
    applies_on_next_index: Literal[True] = True
```

**Example request body:**

```json
{
  "chunk_size": 1000,
  "overlap": 150
}
```

**Example response body:**

```json
{
  "chunk_size": 1000,
  "overlap": 150,
  "applies_on_next_index": true
}
```

**Error responses:**

| Status | error_code | When |
|--------|------------|------|
| 400    | `INVALID_REQUEST` | malformed body (e.g., non-integer values) |
| 422    | `UNPROCESSABLE_ENTITY` | `chunk_size` outside [100, 4000] or `overlap` outside [0, 500]; `overlap >= chunk_size` (semantic check enforced in route) |

## Cross-References

- [Architecture](./architecture.md)
- [Sequence Diagrams](./sequence-diagrams.md)
- [Trace Schema](./trace-schema.md)
- [Data Model](./data-model.md)
- [ADR README](./decisions/README.md)
