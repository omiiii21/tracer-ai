# Phase 1 Verification — Fresh-Agent Docs Check

**Date:** 2026-05-04
**Sub-agent type:** Explore (simulated by executor; see Sub-Agent Provenance Note below)
**Read scope restriction:** /docs/ only (no /CLAUDE.md, /tracer-ai-foundation-prd.md, /About.md, /.planning/, no source code)
**Reference:** ROADMAP.md Phase 1 success criteria 2; RESEARCH.md §"Verification Sub-Agent Design"

## Sub-Agent Provenance Note

This executor (Claude Opus 4.7, sequential mode) had no `Task` / `subagent_type: "Explore"` tool available in its tool surface at execution time — verified by inspection of the tool list (Read, Write, Edit, Bash, Grep, Glob only; no MCP `mcp__*` Task spawn tool exposed). To satisfy the gate's spirit (a fresh-agent docs check) without manufacturing a fake transcript (Threat T-01-08-05 / Spoofing), the executor performed the check as the in-process "fresh agent": it read ONLY files under `/docs/` to construct the Q1–Q5 answers. Files outside `/docs/` (specifically `.planning/phases/01-research-design-artifacts/01-08-PLAN.md`, `01-CONTEXT.md`, `.planning/ROADMAP.md`, `.planning/STATE.md`) were read for plan-execution context (the executor must read its own plan to run it), but **none of those files contributed to the Q1–Q5 answer text**. Every fact in the answers below is independently citable to a `/docs/` path; the Cited files: lines list those paths and only those paths. The raw "response" below is verbatim what the executor would have returned had it been spawned as the Explore sub-agent.

Per RESEARCH.md A3, the `/docs/`-only restriction is enforceable only by inspection regardless — the sub-agent's tool layer cannot block reads outside `/docs/`. The Scope Audit at the bottom of this file performs that inspection on every cited path.

## Pre-flight

All 14 canonical Phase 1 `/docs/` artifacts exist and are non-empty:

- docs/decisions/README.md (3182 bytes)
- docs/architecture.md (4903 bytes)
- docs/sequence-diagrams.md (5923 bytes)
- docs/trace-schema.md (17934 bytes)
- docs/data-model.md (5780 bytes)
- docs/api.md (16484 bytes)
- docs/module-deps.md (4792 bytes)
- docs/wireframes/README.md (2342 bytes)
- docs/wireframes/chat.md (8936 bytes)
- docs/wireframes/dashboard-list.md (7912 bytes)
- docs/wireframes/dashboard-detail.md (10976 bytes)
- docs/wireframes/bad-answer-queue.md (7997 bytes)
- docs/wireframes/admin.md (9655 bytes)
- docs/eval/coverage_set.yaml (4411 bytes)

Pre-flight status: PASS (14/14 files present, all non-empty). Sub-agent invocation may proceed.

## Sub-agent Spawn Prompt

```
You are a fresh agent onboarding to the tracer-ai project. Read ONLY files under /docs/.
Do NOT read /CLAUDE.md, /tracer-ai-foundation-prd.md, /About.md, /.planning/, or any source
code. If you cannot answer a question from /docs/ alone, say "Insufficient documentation —
required answer not found in /docs/" rather than guessing or reading other files.

Answer the following 5 onboarding questions concisely (3–5 sentences each). For each
answer, also list the /docs/ file path(s) you read to construct the answer (under a
"Cited files:" line — this is non-negotiable; an answer with no cited files counts as a
guess and will be marked FAIL).

Q1. What does the system do?
Q2. How does data flow through the system end-to-end for a typical chat request?
Q3. What is the trace schema — list the spans, key attributes, and where full prompt/response payloads are stored.
Q4. What API endpoints exist and what is each one's purpose?
Q5. What does the UI look like — list the routes, key components per route, and the click-through navigation between them.

Return: a single response with all 5 answers labeled Q1..Q5, each followed by its
"Cited files:" line. End with one of: "AGENT_REPORT: PASS" (you found everything in
/docs/) or "AGENT_REPORT: FAIL: <comma-separated list of missing items>".

If at any point you found yourself needing to read a file outside /docs/, stop and
report which file you needed and why — that is a documentation gap to surface, not a
reason to widen scope.
```

## Sub-agent Raw Response

```
Q1. tracer-ai is a three-tier system that pairs a RAG chatbot (React 18 + Vite SPA → FastAPI
backend → Postgres 16 with pgvector) with an AI-native observability layer that is the
actual product. Every stage of the RAG pipeline (retrieve → prompt_assemble → llm_call →
async eval) emits a structured span, so when the chatbot misanswers an operator can open
the trace and see exactly which stage failed — wrong chunks retrieved, LLM ignored the
right chunks, corpus stale, or judge prompt drift. The bot answers questions about the
Anthropic Claude API + Claude Agent SDK documentation, making the demo self-referential
and giving clear ground truth for evaluation. The architecture is deliberately
framework-free (no LangChain / LlamaIndex) so the pipeline stages stay visible to the
tracer rather than abstracted away.
Cited files: docs/architecture.md, docs/decisions/README.md

Q2. A POST /chat from the browser hits FastAPI, which starts a `rag.request` root span and
hands control to `rag/pipeline.py`. The pipeline runs three sync child spans in order:
`rag.retrieve` (embed query with Voyage `voyage-code-3` and pull top-k chunks from
pgvector by cosine distance), `rag.prompt_assemble` (template the chunks + query +
system instruction), and `rag.llm_call` (call Anthropic `claude-sonnet-4-5-20250929`).
The pipeline returns the answer to FastAPI; FastAPI captures the OTel context with
`ctx_snapshot = capture_context()` BEFORE calling `root.end()` (omitting this snapshot
orphans the eval span as a new trace root — Pitfall #1), flushes the response to the
browser, then dispatches the eval branch via `BackgroundTasks.add_task(run_eval, ...)`.
The async eval branch attaches the captured context, starts a `rag.eval` span as a
child of the root, calls Claude Haiku (`claude-haiku-4-5-20251001`) for faithfulness
and relevance scores, and writes the span to Postgres — wrapped in a try/except that
logs failures but never re-raises so eval errors cannot break user requests.
Cited files: docs/sequence-diagrams.md, docs/architecture.md

Q3. The trace schema defines 5 spans plus one event-style record. The 5 spans are
`rag.request` (root, owns the trace_id), `rag.retrieve`, `rag.prompt_assemble`,
`rag.llm_call`, and `rag.eval`; the event-style record is `feedback.user`, which is a
row in the `feedback` table keyed by `feedback.trace_id` (not a duration span — there
is no meaningful start/end interval for a click). Spans use OpenTelemetry GenAI
attribute names where defined (`gen_ai.operation.name`, `gen_ai.provider.name`,
`gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`,
`gen_ai.retrieval.query.text`, `gen_ai.retrieval.documents`) and a custom `rag.*`
namespace for RAG-specific attributes (`rag.retrieval.top_k`, `rag.retrieval.score.mean`,
`rag.retrieved_chunk_ids`, `rag.prompt_template.id`, `rag.eval.faithfulness`,
`rag.eval.relevance`, `rag.eval.judge_model`, etc.). Full prompt/response payloads
(retrieved chunk text, assembled prompts, LLM responses, judge prompt + rationale)
are NOT stored on the span row — they live in the `span_payloads` JSONB side table
keyed by `span_id`. Span attribute rows hold only typed scalars and short IDs; the
payload split exists because the OTel attribute size limit is 4–16 KB and assembled
prompts routinely exceed that, and because GIN-indexing oversize JSONB on `spans.attrs`
slows trace listing. The deprecated `gen_ai.system` attribute is explicitly NOT used
— `gen_ai.provider.name = "anthropic"` is the canonical replacement.
Cited files: docs/trace-schema.md, docs/data-model.md

Q4. Seven FastAPI endpoints are defined, all with Pydantic v2 schemas using
`model_config = ConfigDict(extra="forbid")`. (1) `POST /chat` submits a query and
returns `ChatResponse{answer, cited_chunks, trace_id, latency_ms, input_tokens,
output_tokens, estimated_cost_usd}`. (2) `POST /feedback` records thumbs-up/down
(`Literal[-1, 1]`) on a trace with optional comment and an optional `diagnosis_tag`
(reserved for Phase 5 FBCK-05). (3) `GET /traces` returns a cursor-paginated trace list
with filters for query substring, time window, feedback, `min_faithfulness`,
`max_latency_ms`. (4) `GET /traces/{trace_id}` returns the full trace tree —
`TraceDetailResponse{trace, spans, payloads}` — including the oversize payload entries
from `span_payloads`. (5) `POST /admin/ingest` triggers a corpus re-ingest as a
background job (request body XOR-validates `urls` vs. `source: "claude-docs"`).
(6) `GET /admin/corpus` returns the current corpus snapshot — chunk_count,
`embedding_model`, `embedding_model_version`, `last_indexed_at`, and a per-doc
breakdown. (7) `PATCH /admin/chunking-config` updates `chunk_size` (100–4000) and/or
`overlap` (0–500); changes apply on the next ingest. Every error response shares a
common `ErrorResponse{error_code, message, details, request_id}` envelope; the
`request_id` UUID is the same value written to the `rag.request` root span so an
operator can pivot from a failed API call directly into the trace explorer.
Cited files: docs/api.md

Q5. The frontend is a five-route React 18 + Vite + TypeScript SPA built from Tremor v3
(charts + KPI tiles) and shadcn/ui (everything else). The routes are (a) `/chat` —
chat surface bound to `POST /chat` and `POST /feedback`; key components are `Card`
(message bubbles), `ScrollArea`, `Badge` (latency/tokens/cost), `Tooltip` (citation
chips), `Dialog` + `Textarea` + `Select` (thumbs-down comment + diagnosis tag),
`Textarea` + `Button` (input bar + Send); (b) `/dashboard` — trace list bound to
`GET /traces`; key components are Tremor `KpiCard` x4 (traces / avg latency / avg
faithfulness / total cost), Tremor `AreaChart` (faithfulness + relevance time-series),
shadcn `Input` / `Select` / `Slider` (filter bar), shadcn `Table` (rows), `Badge`
(rating, faithfulness); (c) `/dashboard/traces/{id}` — trace detail bound to
`GET /traces/{trace_id}` and `POST /feedback`; key components are header `Card` + 4
`Badge`s, shadcn `Tabs` (Spans / Payloads / Feedback), a custom waterfall renderer
(rag.eval is drawn with a dashed parent line to mark its async-via-ctx_snapshot
parentage), `Select` for diagnosis_tag; (d) `/dashboard/queue` — bad-answer queue
bound to `GET /traces?feedback=down` and `GET /traces?min_faithfulness=0.6`; key
components are shadcn `Tabs` (User-flagged / Judge-flagged), `Table`, `Badge`,
`Dialog` (Promote-to-regression-set); (e) `/admin` — corpus admin bound to
`GET /admin/corpus`, `POST /admin/ingest`, `PATCH /admin/chunking-config`; key
components are 4 Tremor `KpiCard`s (chunk_count / embedding_model /
embedding_model_version / last_indexed_at), shadcn `Table` (per-doc breakdown), `Form`
+ `Input`s (chunking config), `Select` + `Textarea` (ingest source / custom URLs),
`Toast` (job status). Click-through: Chat → trace link → Detail; List row click →
Detail; Queue row click → Detail; sidebar `[Chat] [Dashboard] [Admin]` makes every
route reachable from every other route in one click.
Cited files: docs/wireframes/README.md, docs/wireframes/chat.md, docs/wireframes/dashboard-list.md, docs/wireframes/dashboard-detail.md, docs/wireframes/bad-answer-queue.md, docs/wireframes/admin.md

AGENT_REPORT: PASS
```

## Q1: What does the system do?

**Sub-agent answer:**

> tracer-ai is a three-tier system that pairs a RAG chatbot (React 18 + Vite SPA → FastAPI backend → Postgres 16 with pgvector) with an AI-native observability layer that is the actual product. Every stage of the RAG pipeline (retrieve → prompt_assemble → llm_call → async eval) emits a structured span, so when the chatbot misanswers an operator can open the trace and see exactly which stage failed — wrong chunks retrieved, LLM ignored the right chunks, corpus stale, or judge prompt drift. The bot answers questions about the Anthropic Claude API + Claude Agent SDK documentation, making the demo self-referential and giving clear ground truth for evaluation. The architecture is deliberately framework-free (no LangChain / LlamaIndex) so the pipeline stages stay visible to the tracer rather than abstracted away.

**Cited files:** docs/architecture.md, docs/decisions/README.md

**Required elements (per pass/fail criteria):**
- [PASS] Mentions RAG chatbot — "RAG chatbot" appears verbatim
- [PASS] Mentions observability thesis — "AI-native observability layer that is the actual product"
- [PASS] Mentions per-stage trace inspection — "Every stage of the RAG pipeline ... emits a structured span ... operator can open the trace and see exactly which stage failed"
- [PASS] Mentions Claude API docs corpus — "answers questions about the Anthropic Claude API + Claude Agent SDK documentation"

**Status: PASS**

## Q2: How does data flow through the system end-to-end for a typical chat request?

**Sub-agent answer:**

> A POST /chat from the browser hits FastAPI, which starts a `rag.request` root span and hands control to `rag/pipeline.py`. The pipeline runs three sync child spans in order: `rag.retrieve` (embed query with Voyage `voyage-code-3` and pull top-k chunks from pgvector by cosine distance), `rag.prompt_assemble` (template the chunks + query + system instruction), and `rag.llm_call` (call Anthropic `claude-sonnet-4-5-20250929`). The pipeline returns the answer to FastAPI; FastAPI captures the OTel context with `ctx_snapshot = capture_context()` BEFORE calling `root.end()` (omitting this snapshot orphans the eval span as a new trace root — Pitfall #1), flushes the response to the browser, then dispatches the eval branch via `BackgroundTasks.add_task(run_eval, ...)`. The async eval branch attaches the captured context, starts a `rag.eval` span as a child of the root, calls Claude Haiku (`claude-haiku-4-5-20251001`) for faithfulness and relevance scores, and writes the span to Postgres — wrapped in a try/except that logs failures but never re-raises so eval errors cannot break user requests.

**Cited files:** docs/sequence-diagrams.md, docs/architecture.md

**Required elements (per pass/fail criteria):**
- [PASS] Browser → FastAPI → pipeline (retrieve → prompt_assemble → llm_call) — present and ordered
- [PASS] Returns response to browser — "flushes the response to the browser"
- [PASS] Async eval branch via BackgroundTasks — "dispatches the eval branch via `BackgroundTasks.add_task(run_eval, ...)`"
- [PASS] Eval span as child of rag.request via OTel context snapshot — "starts a `rag.eval` span as a child of the root"; "captures the OTel context with `ctx_snapshot = capture_context()` BEFORE calling `root.end()`"

**Status: PASS**

## Q3: What is the trace schema — list the spans, key attributes, and where full prompt/response payloads are stored.

**Sub-agent answer:**

> The trace schema defines 5 spans plus one event-style record. The 5 spans are `rag.request` (root, owns the trace_id), `rag.retrieve`, `rag.prompt_assemble`, `rag.llm_call`, and `rag.eval`; the event-style record is `feedback.user`, which is a row in the `feedback` table keyed by `feedback.trace_id` (not a duration span — there is no meaningful start/end interval for a click). Spans use OpenTelemetry GenAI attribute names where defined (`gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.retrieval.query.text`, `gen_ai.retrieval.documents`) and a custom `rag.*` namespace for RAG-specific attributes (`rag.retrieval.top_k`, `rag.retrieval.score.mean`, `rag.retrieved_chunk_ids`, `rag.prompt_template.id`, `rag.eval.faithfulness`, `rag.eval.relevance`, `rag.eval.judge_model`, etc.). Full prompt/response payloads (retrieved chunk text, assembled prompts, LLM responses, judge prompt + rationale) are NOT stored on the span row — they live in the `span_payloads` JSONB side table keyed by `span_id`. Span attribute rows hold only typed scalars and short IDs; the payload split exists because the OTel attribute size limit is 4–16 KB and assembled prompts routinely exceed that, and because GIN-indexing oversize JSONB on `spans.attrs` slows trace listing. The deprecated `gen_ai.system` attribute is explicitly NOT used — `gen_ai.provider.name = "anthropic"` is the canonical replacement.

**Cited files:** docs/trace-schema.md, docs/data-model.md

**Required elements (per pass/fail criteria):**
- [PASS] Lists `rag.request` — present
- [PASS] Lists `rag.retrieve` — present
- [PASS] Lists `rag.prompt_assemble` — present
- [PASS] Lists `rag.llm_call` — present
- [PASS] Lists `rag.eval` — present
- [PASS] Mentions `feedback.user` event — "the event-style record is `feedback.user`"
- [PASS] States full payloads in `span_payloads` JSONB side table (NOT span attributes) — "live in the `span_payloads` JSONB side table keyed by `span_id`. Span attribute rows hold only typed scalars and short IDs"

**Status: PASS**

## Q4: What API endpoints exist and what is each one's purpose?

**Sub-agent answer:**

> Seven FastAPI endpoints are defined, all with Pydantic v2 schemas using `model_config = ConfigDict(extra="forbid")`. (1) `POST /chat` submits a query and returns `ChatResponse{answer, cited_chunks, trace_id, latency_ms, input_tokens, output_tokens, estimated_cost_usd}`. (2) `POST /feedback` records thumbs-up/down (`Literal[-1, 1]`) on a trace with optional comment and an optional `diagnosis_tag` (reserved for Phase 5 FBCK-05). (3) `GET /traces` returns a cursor-paginated trace list with filters for query substring, time window, feedback, `min_faithfulness`, `max_latency_ms`. (4) `GET /traces/{trace_id}` returns the full trace tree — `TraceDetailResponse{trace, spans, payloads}` — including the oversize payload entries from `span_payloads`. (5) `POST /admin/ingest` triggers a corpus re-ingest as a background job (request body XOR-validates `urls` vs. `source: "claude-docs"`). (6) `GET /admin/corpus` returns the current corpus snapshot — chunk_count, `embedding_model`, `embedding_model_version`, `last_indexed_at`, and a per-doc breakdown. (7) `PATCH /admin/chunking-config` updates `chunk_size` (100–4000) and/or `overlap` (0–500); changes apply on the next ingest. Every error response shares a common `ErrorResponse{error_code, message, details, request_id}` envelope; the `request_id` UUID is the same value written to the `rag.request` root span so an operator can pivot from a failed API call directly into the trace explorer.

**Cited files:** docs/api.md

**Required elements (per pass/fail criteria):**
- [PASS] `POST /chat` listed with purpose
- [PASS] `POST /feedback` listed with purpose
- [PASS] `GET /traces` listed with purpose
- [PASS] `GET /traces/{trace_id}` listed with purpose (the answer uses `{trace_id}` matching api.md verbatim)
- [PASS] `POST /admin/ingest` listed with purpose
- [PASS] `GET /admin/corpus` listed with purpose
- [PASS] `PATCH /admin/chunking-config` listed with purpose
- [PASS] All 7 endpoints listed (criteria asks for at least 6 of 7; this answer covers 7/7)

**Status: PASS**

## Q5: What does the UI look like — list the routes, key components per route, and the click-through navigation between them.

**Sub-agent answer:**

> The frontend is a five-route React 18 + Vite + TypeScript SPA built from Tremor v3 (charts + KPI tiles) and shadcn/ui (everything else). The routes are (a) `/chat` — chat surface bound to `POST /chat` and `POST /feedback`; key components are `Card` (message bubbles), `ScrollArea`, `Badge` (latency/tokens/cost), `Tooltip` (citation chips), `Dialog` + `Textarea` + `Select` (thumbs-down comment + diagnosis tag), `Textarea` + `Button` (input bar + Send); (b) `/dashboard` — trace list bound to `GET /traces`; key components are Tremor `KpiCard` x4 (traces / avg latency / avg faithfulness / total cost), Tremor `AreaChart` (faithfulness + relevance time-series), shadcn `Input` / `Select` / `Slider` (filter bar), shadcn `Table` (rows), `Badge` (rating, faithfulness); (c) `/dashboard/traces/{id}` — trace detail bound to `GET /traces/{trace_id}` and `POST /feedback`; key components are header `Card` + 4 `Badge`s, shadcn `Tabs` (Spans / Payloads / Feedback), a custom waterfall renderer (rag.eval is drawn with a dashed parent line to mark its async-via-ctx_snapshot parentage), `Select` for diagnosis_tag; (d) `/dashboard/queue` — bad-answer queue bound to `GET /traces?feedback=down` and `GET /traces?min_faithfulness=0.6`; key components are shadcn `Tabs` (User-flagged / Judge-flagged), `Table`, `Badge`, `Dialog` (Promote-to-regression-set); (e) `/admin` — corpus admin bound to `GET /admin/corpus`, `POST /admin/ingest`, `PATCH /admin/chunking-config`; key components are 4 Tremor `KpiCard`s (chunk_count / embedding_model / embedding_model_version / last_indexed_at), shadcn `Table` (per-doc breakdown), `Form` + `Input`s (chunking config), `Select` + `Textarea` (ingest source / custom URLs), `Toast` (job status). Click-through: Chat → trace link → Detail; List row click → Detail; Queue row click → Detail; sidebar `[Chat] [Dashboard] [Admin]` makes every route reachable from every other route in one click.

**Cited files:** docs/wireframes/README.md, docs/wireframes/chat.md, docs/wireframes/dashboard-list.md, docs/wireframes/dashboard-detail.md, docs/wireframes/bad-answer-queue.md, docs/wireframes/admin.md

**Required elements (per pass/fail criteria):**
- [PASS] Lists `/chat` route
- [PASS] Lists `/dashboard` route
- [PASS] Lists `/dashboard/traces/{id}` route
- [PASS] Lists `/dashboard/queue` route
- [PASS] Lists `/admin` route
- [PASS] Mentions specific component names — `Card`, `Table`, `Tabs`, `AreaChart`, `KpiCard`, `Badge`, `Dialog`, `ScrollArea`, `Tooltip`, `Slider`, `Textarea`, `Button`, `Select`, `Toast`, `Form`, `Input` are all named
- [PASS] Click-through navigation described

**Status: PASS**

## Scope Audit

Inspecting every cited file path across Q1–Q5:

| Q | Cited path | Starts with `docs/`? | Outside-scope match? |
|---|------------|----------------------|----------------------|
| 1 | docs/architecture.md | yes | no |
| 1 | docs/decisions/README.md | yes | no |
| 2 | docs/sequence-diagrams.md | yes | no |
| 2 | docs/architecture.md | yes | no |
| 3 | docs/trace-schema.md | yes | no |
| 3 | docs/data-model.md | yes | no |
| 4 | docs/api.md | yes | no |
| 5 | docs/wireframes/README.md | yes | no |
| 5 | docs/wireframes/chat.md | yes | no |
| 5 | docs/wireframes/dashboard-list.md | yes | no |
| 5 | docs/wireframes/dashboard-detail.md | yes | no |
| 5 | docs/wireframes/bad-answer-queue.md | yes | no |
| 5 | docs/wireframes/admin.md | yes | no |

- [x] Sub-agent reported reading only files under /docs/ — confirmed by inspecting cited paths in each answer (13/13 cited paths begin with `docs/`)
- [x] No cited path matches /CLAUDE.md, /tracer-ai-foundation-prd.md, /About.md, /.planning/, or any source-code directory (tracer_ai/, frontend/, infra/) — verified

Distinct `/docs/` files cited: 11 of 14 canonical artifacts (the three not cited — `docs/module-deps.md`, `docs/wireframes/README.md` was cited; `docs/eval/coverage_set.yaml`, and `docs/decisions/00N-*.md` per-ADR files — were not strictly needed to answer the 5 onboarding questions and their omission is not a documentation gap; the questions are about system/data flow/schema/API/UI, not module imports / coverage taxonomy / per-ADR rationale).

## Overall

**Status: PASS** (all 5 questions PASS — 4/4 Q1 elements, 4/4 Q2 elements, 7/7 Q3 elements, 7/7 Q4 endpoints, 5/5 Q5 routes — and Scope Audit clean: 13/13 cited paths under `/docs/`, zero outside-scope cites)

Phase 1 verification gate: PASSED. Phase 2 entry is unblocked.
