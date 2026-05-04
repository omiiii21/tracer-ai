# Trace Schema Specification

## Overview

Every chat request to tracer-ai produces one trace with **four child spans**: `rag.retrieve`, `rag.prompt_assemble`, `rag.llm_call` (sync, on the request path), plus `rag.eval` (async, dispatched via `BackgroundTasks` after the response is flushed). A separate event-style record `feedback.user` correlates user thumbs-up/thumbs-down to the trace via `feedback.trace_id` and is **not** a duration span.

Spans use **OpenTelemetry GenAI semantic-convention attribute names** where defined (`gen_ai.*`) and a custom **`rag.*` namespace** for RAG-specific attributes that the OTel spec does not cover. ALL `gen_ai.*` attributes are at **Development / Experimental** stability — naming may change in future spec revisions. To absorb that drift in one place, every attribute name is centralized as a Python constant in `tracer_ai/tracer/span.py` (Phase 4 TRCR-01) — a spec rename is a one-line edit per constant.

For the rationale behind this strategy (custom tracer with OTel-compatible *naming* but no `opentelemetry-sdk` runtime dependency), see [ADR 005 — Observability Strategy](./decisions/005-observability-strategy.md). For the architectural context (where these spans are emitted in the request flow, the `BackgroundTasks` async-eval pattern, and the OTel context-snapshot mitigation), see [Architecture Research §"OTel GenAI Semantic Conventions — Status as of 2026"](../.planning/research/ARCHITECTURE.md#otel-genai-semantic-conventions--status-as-of-2026) and [Architecture §"Anti-Patterns"](../.planning/research/ARCHITECTURE.md#anti-patterns).

## OTel Status Disclaimer

The OpenTelemetry GenAI semantic conventions are at **Development / Experimental** stability as of May 2026. Two facts to encode permanently in this spec:

- **`gen_ai.system` is DEPRECATED in the current OTel GenAI spec.** Do **not** use it. Use **`gen_ai.provider.name`** instead. For tracer-ai, the value is `"anthropic"` on every span that calls Anthropic (`rag.request`, `rag.llm_call`, `rag.eval`).
- The full `gen_ai.*` set may rename in future spec revisions. **Mitigation:** every attribute name in this spec is a Python constant in one file (see §Attribute Constants below); a spec rename is a one-line edit per constant — no pipeline-code changes required.

This is a normative requirement, not a stylistic preference: ADR 005's "Mandatory follow-ups" lists "Document the `gen_ai.system` DEPRECATION explicitly in `/docs/trace-schema.md`" as a deliverable Phase 1 owns.

## Attribute Constants

The following block is **copy-paste-ready** into `tracer_ai/tracer/span.py` in Phase 4 TRCR-01. No surrounding markdown to strip — the fenced Python block IS the contract.

```python
# OTel GenAI conventions (Development stability; gen_ai.system DEPRECATED)
GEN_AI_OPERATION_NAME = "gen_ai.operation.name"   # "chat" | "embeddings" | "retrieval"
GEN_AI_PROVIDER_NAME = "gen_ai.provider.name"     # "anthropic" — USE THIS
# GEN_AI_SYSTEM = "gen_ai.system"                 # DEPRECATED; do not use
GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
GEN_AI_RESPONSE_MODEL = "gen_ai.response.model"
GEN_AI_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
GEN_AI_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
GEN_AI_RETRIEVAL_QUERY_TEXT = "gen_ai.retrieval.query.text"
GEN_AI_RETRIEVAL_DOCUMENTS = "gen_ai.retrieval.documents"

# Custom rag.* namespace (no official rag.* exists in OTel)
RAG_RETRIEVED_CHUNK_IDS = "rag.retrieved_chunk_ids"
RAG_RETRIEVAL_TOP_K = "rag.retrieval.top_k"
RAG_RETRIEVAL_SCORE_MEAN = "rag.retrieval.score.mean"
RAG_RETRIEVAL_SCORE_MIN = "rag.retrieval.score.min"
RAG_RETRIEVAL_SCORE_MAX = "rag.retrieval.score.max"
RAG_PROMPT_TEMPLATE_ID = "rag.prompt_template.id"
RAG_PROMPT_TOKEN_COUNT = "rag.prompt.token_count"
RAG_EMBEDDING_MODEL = "rag.embedding.model"
RAG_EMBEDDING_MODEL_VERSION = "rag.embedding.model_version"
RAG_EVAL_FAITHFULNESS = "rag.eval.faithfulness"
RAG_EVAL_RELEVANCE = "rag.eval.relevance"
RAG_EVAL_JUDGE_MODEL = "rag.eval.judge_model"
RAG_EVAL_JUDGE_PROMPT_VERSION = "rag.eval.judge_prompt_version"
RAG_EVAL_JUDGE_COST_USD = "rag.eval.judge_cost_usd"
RAG_EVAL_JUDGE_LATENCY_MS = "rag.eval.judge_latency_ms"
```

These constants are imported into `tracer_ai/tracer/span.py` in Phase 4 TRCR-01.

## Payload Storage Convention

> **Warning** — full prompt/response text **must NOT** be stored as span attributes. The OTel attribute size limit is 4–16 KB per attribute; assembled prompts (1–2 K tokens of system instruction + retrieved chunks + user query) and LLM responses routinely exceed this. Storing them on the span row also bloats GIN indexes on `spans.attrs` and slows trace listing. **Use the `span_payloads` JSONB side table** (see [Data Model](./data-model.md)) referenced by `span_id` (1:N FK off `spans.id`). Span attribute rows hold only metadata: scores, IDs, token counts, model names, finish reasons. This is Anti-Pattern #2 in [Architecture Research §"Anti-Patterns"](../.planning/research/ARCHITECTURE.md#anti-patterns) and decision **D-47** in `01-CONTEXT.md`.

The split is:

- **`spans.attrs` (JSONB column on `spans`):** small, queryable metadata — typed scalars and short string IDs. GIN-indexed for fast filtering.
- **`span_payloads.payload` (JSONB column on `span_payloads`):** unbounded — full retrieved chunk text, full assembled prompts, full LLM responses, full judge prompt + judge response. One row per heavy span; not GIN-indexed; fetched only on trace-detail drill-in.

## rag.request

**Purpose:** Root span of every chat request trace; one per HTTP `POST /chat` invocation. Owns the trace_id; all four child spans (`rag.retrieve`, `rag.prompt_assemble`, `rag.llm_call`, `rag.eval`) attach under it. The `feedback.user` event correlates back to this span's `trace_id`.

**Attributes:**

| name | type | required | OTel status | example |
|------|------|----------|-------------|---------|
| `gen_ai.operation.name` | string | yes | OTel GenAI Development | `"chat"` |
| `gen_ai.provider.name` | string | yes | OTel GenAI Development | `"anthropic"` |
| `query_text` | string | yes | custom | `"How do I authenticate to the Anthropic Messages API?"` |
| `feedback.rating` | int (-1, 0, 1) | no (post-feedback) | custom | `1` |
| `feedback.comment_id` | UUID | no | custom | `"550e8400-e29b-41d4-a716-446655440000"` |

**JSON example:**

```json
{
  "name": "rag.request",
  "trace_id": "550e8400-e29b-41d4-a716-446655440000",
  "span_id": "0000-0001",
  "parent_span_id": null,
  "started_at": "2026-05-04T12:00:00.000Z",
  "ended_at": "2026-05-04T12:00:03.420Z",
  "attrs": {
    "gen_ai.operation.name": "chat",
    "gen_ai.provider.name": "anthropic",
    "query_text": "How do I authenticate to the Anthropic Messages API?"
  }
}
```

**Payload table:** none. The root span carries no heavy payload — its job is to own the trace_id and parent the children.

## rag.retrieve

**Purpose:** Vector retrieval step — embed the query (Voyage AI `voyage-code-3`) and fetch the top-k nearest chunks from pgvector by cosine distance.

**Attributes:**

| name | type | required | OTel status | example |
|------|------|----------|-------------|---------|
| `gen_ai.operation.name` | string | yes | OTel GenAI Development | `"retrieval"` |
| `rag.embedding.model` | string | yes | custom | `"voyage-code-3"` |
| `rag.embedding.model_version` | string | yes | custom | `"2024-11"` |
| `rag.retrieval.top_k` | int | yes | custom | `5` |
| `rag.retrieval.score.mean` | float | yes | custom | `0.78` |
| `rag.retrieval.score.min` | float | yes | custom | `0.62` |
| `rag.retrieval.score.max` | float | yes | custom | `0.91` |
| `rag.retrieved_chunk_ids` | list[UUID] | yes | custom | `["a1b2...", "c3d4...", "e5f6...", "0708...", "9a0b..."]` |
| `gen_ai.retrieval.query.text` | string | no | OTel GenAI Opt-In | `"How do I authenticate to the Anthropic Messages API?"` |

`gen_ai.retrieval.query.text` is **Opt-In** per the OTel GenAI spec — emit only when query-text logging is enabled in config. The query text is also available on the parent `rag.request.query_text`, so duplicating here is opt-in to avoid storage cost when not needed.

**JSON example:**

```json
{
  "name": "rag.retrieve",
  "trace_id": "550e8400-e29b-41d4-a716-446655440000",
  "span_id": "0000-0002",
  "parent_span_id": "0000-0001",
  "started_at": "2026-05-04T12:00:00.040Z",
  "ended_at": "2026-05-04T12:00:00.310Z",
  "attrs": {
    "gen_ai.operation.name": "retrieval",
    "rag.embedding.model": "voyage-code-3",
    "rag.embedding.model_version": "2024-11",
    "rag.retrieval.top_k": 5,
    "rag.retrieval.score.mean": 0.78,
    "rag.retrieval.score.min": 0.62,
    "rag.retrieval.score.max": 0.91,
    "rag.retrieved_chunk_ids": ["a1b2c3d4-...", "c3d4e5f6-...", "e5f60708-...", "07089a0b-...", "9a0bc1d2-..."]
  }
}
```

**Payload table:** Full retrieved chunk content (chunk text + per-chunk score + chunk metadata) is stored in `span_payloads` keyed by `span_id`. The `rag.retrieved_chunk_ids` attribute on the span row is the index into that payload (and into the `chunks` table).

## rag.prompt_assemble

**Purpose:** Assemble the final LLM prompt from the retrieved chunks, the user query, and the system instruction (citation-formatted). This step is pure-Python templating; no external calls.

**Attributes:**

| name | type | required | OTel status | example |
|------|------|----------|-------------|---------|
| `rag.prompt_template.id` | string | yes | custom | `"v1.basic-citation"` |
| `rag.prompt.token_count` | int | yes | custom | `1247` |

`rag.prompt_template.id` is **versioned** — when the prompt template changes (Phase 5 calibration may iterate it), the ID changes. This makes faithfulness drift correlatable to template version: a sudden score drop across all traces emitted with `v2.aggressive-citation` is a template regression, not a corpus or model issue.

**JSON example:**

```json
{
  "name": "rag.prompt_assemble",
  "trace_id": "550e8400-e29b-41d4-a716-446655440000",
  "span_id": "0000-0003",
  "parent_span_id": "0000-0001",
  "started_at": "2026-05-04T12:00:00.315Z",
  "ended_at": "2026-05-04T12:00:00.318Z",
  "attrs": {
    "rag.prompt_template.id": "v1.basic-citation",
    "rag.prompt.token_count": 1247
  }
}
```

**Payload table:** Full assembled prompt text (system instruction + chunks + user query, exactly as sent to Anthropic) is stored in `span_payloads` keyed by `span_id`. This is the artifact the operator inspects when diagnosing "LLM ignored the right chunks."

## rag.llm_call

**Purpose:** Call the Anthropic Messages API with the assembled prompt; receive answer + token usage. This is the only span that touches the LLM provider for the answer.

**Attributes:**

| name | type | required | OTel status | example |
|------|------|----------|-------------|---------|
| `gen_ai.operation.name` | string | yes | OTel GenAI Development | `"chat"` |
| `gen_ai.provider.name` | string | yes | OTel GenAI Development | `"anthropic"` |
| `gen_ai.request.model` | string | yes | OTel GenAI Development | `"claude-sonnet-4-5-20250929"` |
| `gen_ai.response.model` | string | yes | OTel GenAI Development | `"claude-sonnet-4-5-20250929"` |
| `gen_ai.usage.input_tokens` | int | yes | OTel GenAI Development | `1247` |
| `gen_ai.usage.output_tokens` | int | yes | OTel GenAI Development | `412` |
| `gen_ai.response.finish_reasons` | list[string] | no | OTel GenAI Development | `["end_turn"]` |

`gen_ai.request.model` and `gen_ai.response.model` are **dated snapshots** (e.g., `claude-sonnet-4-5-20250929`), **never** the alias `claude-sonnet-4-5`. Pinning to a dated snapshot is mandated by Pitfall #4 — alias-pinned models silently change behavior at provider release time, breaking faithfulness/relevance score baselines without any deploy event to correlate against.

**JSON example:**

```json
{
  "name": "rag.llm_call",
  "trace_id": "550e8400-e29b-41d4-a716-446655440000",
  "span_id": "0000-0004",
  "parent_span_id": "0000-0001",
  "started_at": "2026-05-04T12:00:00.320Z",
  "ended_at": "2026-05-04T12:00:03.410Z",
  "attrs": {
    "gen_ai.operation.name": "chat",
    "gen_ai.provider.name": "anthropic",
    "gen_ai.request.model": "claude-sonnet-4-5-20250929",
    "gen_ai.response.model": "claude-sonnet-4-5-20250929",
    "gen_ai.usage.input_tokens": 1247,
    "gen_ai.usage.output_tokens": 412,
    "gen_ai.response.finish_reasons": ["end_turn"]
  }
}
```

**Payload table:** Full LLM response text (the answer that flows back to the user) is stored in `span_payloads` keyed by `span_id`. This is the artifact the judge scores against in `rag.eval`.

## rag.eval

**Purpose:** LLM-as-judge scoring — Claude Haiku rates faithfulness (does the answer stay grounded in the retrieved chunks?) and relevance (does the answer address the user's query?) on a 0.0–1.0 scale. Runs in a `BackgroundTasks` async branch **after** the HTTP response is flushed, using the OTel context snapshot captured **before** `root.end()` so the `rag.eval` span attaches as a child of `rag.request` rather than orphaning as a new root. See [Architecture §"Async LLM-as-judge via FastAPI BackgroundTasks"](../.planning/research/ARCHITECTURE.md#pattern-3-async-llm-as-judge-via-fastapi-backgroundtasks) and Pitfall #1 / #4.

**Attributes:**

| name | type | required | OTel status | example |
|------|------|----------|-------------|---------|
| `rag.eval.faithfulness` | float (0.0–1.0) | yes | custom | `0.82` |
| `rag.eval.relevance` | float (0.0–1.0) | yes | custom | `0.91` |
| `rag.eval.judge_model` | string | yes | custom | `"claude-haiku-4-5-20251001"` |
| `rag.eval.judge_prompt_version` | string | yes | custom | `"v1.ragas-faithfulness"` |
| `rag.eval.judge_cost_usd` | float | yes | custom | `0.00012` |
| `rag.eval.judge_latency_ms` | int | no | custom | `850` |

`rag.eval.judge_model` is a **dated snapshot mandatory** (e.g., `claude-haiku-4-5-20251001`), never the alias `claude-haiku`. This is decision **D-50** in `01-CONTEXT.md` and Pitfall #4 — judge model alias drift silently shifts the calibration baseline; the dated snapshot is what makes faithfulness scores comparable across weeks. `rag.eval.judge_prompt_version` enforces the same discipline for the judge prompt: when the judge prompt is iterated (Phase 5 EVAL-06 calibration), the version string changes, and pre-vs-post-calibration scores remain distinguishable.

**JSON example:**

```json
{
  "name": "rag.eval",
  "trace_id": "550e8400-e29b-41d4-a716-446655440000",
  "span_id": "0000-0005",
  "parent_span_id": "0000-0001",
  "started_at": "2026-05-04T12:00:08.500Z",
  "ended_at": "2026-05-04T12:00:09.350Z",
  "attrs": {
    "rag.eval.faithfulness": 0.82,
    "rag.eval.relevance": 0.91,
    "rag.eval.judge_model": "claude-haiku-4-5-20251001",
    "rag.eval.judge_prompt_version": "v1.ragas-faithfulness",
    "rag.eval.judge_cost_usd": 0.00012,
    "rag.eval.judge_latency_ms": 850
  }
}
```

**Payload table:** Full judge prompt (system + assistant_answer + retrieved_chunks XML-wrapped) and full judge response (the scoring rationale Claude Haiku returned, before parsing into the two floats) are stored in `span_payloads` keyed by `span_id`. This is what the operator inspects when a faithfulness score looks wrong — was it the score, the rationale, or the parser?

## feedback.user

**Purpose:** User thumbs-up or thumbs-down on a chat message. **Event-style record, not a duration span** — there is no meaningful "started_at / ended_at" interval for a click. Persisted as a row in the `feedback` table keyed by `feedback.trace_id`; surfaced in the trace-detail UI alongside the trace's spans for context, but does not appear in the span waterfall.

**Attributes:**

| name | type | required | OTel status | example |
|------|------|----------|-------------|---------|
| `feedback.rating` | int (1 = up, -1 = down) | yes | custom | `-1` |
| `feedback.trace_id` | UUID | yes | custom | `"550e8400-e29b-41d4-a716-446655440000"` |
| `feedback.comment` | string | no | custom | `"Wrong chunks retrieved — none mention API key headers"` |
| `feedback.diagnosis_tag` | string | no (Phase 5 FBCK-05) | custom | `"Retrieval"` |

`feedback.diagnosis_tag` is reserved for Phase 5 FBCK-05 (per-stage failure diagnosis). The schema column is allocated in Phase 1; the UI to populate it is deferred. Allowed values when implemented: `"Retrieval"`, `"PromptAssembly"`, `"LLM"`, `"CorpusStale"`, `"Other"`.

**JSON example:**

```json
{
  "name": "feedback.user",
  "feedback.trace_id": "550e8400-e29b-41d4-a716-446655440000",
  "recorded_at": "2026-05-04T12:01:14.700Z",
  "attrs": {
    "feedback.rating": -1,
    "feedback.comment": "Wrong chunks retrieved — none mention API key headers"
  }
}
```

**Payload table:** none. The optional `feedback.comment` is short-form free text and lives directly on the `feedback` row; no large payload is attached.

## Cross-References

- [Architecture](./architecture.md) — system overview diagram showing where each span is emitted in the request flow.
- [Sequence Diagrams](./sequence-diagrams.md) — chat-request sequence diagram showing the OTel context-snapshot capture before `root.end()` (mitigates the orphan-eval-span pitfall).
- [Data Model](./data-model.md) — `traces` / `spans` / `span_payloads` / `feedback` tables, including the JSONB columns referenced by this spec.
- [ADR 005 — Observability Strategy](./decisions/005-observability-strategy.md) — rationale for the custom-tracer + OTel-naming approach this spec codifies.
- [Module Dependencies](./module-deps.md) — `tracer/` is a leaf module imported by `rag/`, `eval/`, and `api/`; the constants in this spec live there.
- [Architecture Research §"OTel GenAI Semantic Conventions — Status as of 2026"](../.planning/research/ARCHITECTURE.md#otel-genai-semantic-conventions--status-as-of-2026) — verbatim status table for every `gen_ai.*` attribute used here.
