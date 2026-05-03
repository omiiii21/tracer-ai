# Project Research Summary

**Project:** tracer-ai
**Domain:** Observable RAG chatbot with custom OTel-aligned semantic observability
**Researched:** 2026-05-04
**Confidence:** HIGH

## Executive Summary

tracer-ai is a portfolio-grade RAG chatbot whose product thesis is the *observability layer*, not the chat surface. Research confirms that production LLM observability has converged on a standard feature set (trace listing, span waterfall, payload inspector, LLM-as-judge eval, manual feedback, time-series dashboards) — every major platform (LangSmith, Langfuse, Arize Phoenix, Braintrust) ships these. The PRD §6 features map cleanly to this baseline. The differentiation comes from three places: (1) **per-stage failure diagnosis** (PRD §2's "retriever vs LLM vs corpus" distinction is not surfaced as UI in any competitor), (2) **first-class bad-answer → regression CLI loop** (closer to differentiating than table stakes), and (3) **OTel GenAI conventions from day one** (most competitors retrofit OTel; building on it preserves real portability).

The recommended stack consolidates persistence: Postgres + JSONB (trace storage) and pgvector (vector store) collapse into one Docker container, replacing the planned separate Qdrant service. Embeddings via Voyage AI `voyage-code-3` (Anthropic's recommended partner; tuned for technical docs); judge via date-pinned Haiku snapshot (alias drift causes false time-series discontinuities). Frontend: Vite + React 18 + Tailwind v3 (NOT v4 — Tremor v3 and shadcn/ui both target v3) + shadcn/ui + Tremor for charts.

Critical risks center on async tracing: OTel context propagation breaks across `BackgroundTasks` boundaries unless explicitly snapshotted, embedding model mismatches silently produce garbage retrieval, and judge model aliases drift over time. All three are addressed in Phase −1 design and Phase 2/3 implementation patterns. The PRD's 6-phase structure (Phase −1 design + Phases 0–5 execution) is sound and is preserved by the roadmap.

## Key Findings

### Recommended Stack

The PRD §9 locked choices (Python 3.12+, FastAPI, Pydantic v2, direct Anthropic SDK, Vite + React 18 + Tailwind + shadcn/ui, Docker Compose) all validate as current 2026 best practices. Four open decisions are now resolved with research backing.

**Core technologies (locked + research-resolved):**
- **Python 3.12+, FastAPI, Pydantic v2** — type-safe I/O, auto OpenAPI for the React client (locked)
- **Anthropic Claude Sonnet 4.5 (bot) + date-pinned Haiku (judge)** — `claude-sonnet-4-5-20250929`; pin Haiku to a dated snapshot, not alias (locked + pin requirement)
- **No orchestration framework — direct SDK** — frameworks abstract away the very pipeline stages we want to instrument (locked)
- **Postgres 16 + JSONB + pgvector extension** — single Docker service for traces AND vectors (resolves GSD-OPEN-2 + GSD-OPEN-4)
- **Voyage AI `voyage-code-3`** — Anthropic's recommended partner; benchmarked for code/technical docs; sentence-transformers fallback for offline dev (resolves GSD-OPEN-3)
- **OTel GenAI attribute naming WITHOUT the `opentelemetry-sdk` runtime dep** — adopt attribute names as constants in `tracer/span.py`; preserves portability without SDK overhead. All `gen_ai.*` are Development/Experimental as of 2026; `gen_ai.system` is deprecated, use `gen_ai.provider.name`
- **Tremor v3** for charts — wraps Recharts internally; declarative API saves ~75% LoC vs raw Recharts (resolves GSD-OPEN-1)
- **Tailwind v3 (pinned)** — NOT v4 (breaking migration; Tremor v3 + shadcn/ui both require v3)
- **Markdown-header-aware chunking, top_k=5 default** — prevents code/prose split and lost-in-the-middle (resolves GSD-OPEN-6)

### Expected Features

Production LLM observability platforms have converged on a well-known table-stakes set; building this baseline is non-negotiable. tracer-ai's differentiators are narrow but real.

**Must have (table stakes — all in PRD §6):**
- Chat UI with citations, latency/token/cost row, thumbs-up/down per message
- Trace list with filters (time, score, cost, feedback), trace detail with span waterfall
- Full prompt + response + retrieved chunks payload inspector
- LLM-as-judge auto-eval (faithfulness + relevance), async, post-response
- Manual feedback ingestion (thumbs + free-text comment)
- Time-series dashboard (latency p50/p95, cost, faithfulness, feedback ratio)
- Bad-answer queue (filtered subset: feedback=down OR score < threshold)
- Eval/regression CLI with pass/fail report

**Should have (genuine differentiators):**
- **Per-stage failure diagnosis tag on trace detail** — operator sets one of {Retrieval, Prompt, Corpus, LLM} when triaging a trace. None of LangSmith/Langfuse/Phoenix/Braintrust/Helicone surface this. *(NEW gap identified by research — not in PRD §6.)*
- **Promote-to-regression-set in one click/command** from the bad-answer queue. Existing platforms have annotation queues but not a first-class one-shot promote-to-CI workflow.
- **OTel GenAI conventions from day one** — preserves trivial migration path to OTel collectors (Langfuse, Datadog, etc.) later.
- **Corpus admin UI** — none of the five platforms manage the document corpus. Genuine tracer-ai-only feature.
- **Trace link surfaced inside chat message** — drill from any chat answer to its full trace.

**Defer (v2+ / out of scope):**
- Streaming responses, multi-turn cross-session memory, multi-modal input, agentic multi-hop, auth/multi-tenant, production SLA, alerting UI (use config file in v1)

### Architecture Approach

Three-layer system — frontend SPA, FastAPI backend with instrumented RAG pipeline, Postgres + pgvector for persistence. Every pipeline stage emits a span; all spans funnel through an `asyncio.Queue` to a background consumer that batch-writes JSONB to Postgres (≤100ms hot-path budget). Async LLM-as-judge runs via FastAPI `BackgroundTasks` after response flush — context snapshot/re-attach pattern parents the `rag.eval` span under `rag.request`.

**Major components:**
1. **`tracer/`** — span dataclass with OTel attribute name constants, context propagation helpers, `TraceStore` Protocol, async-queue Postgres exporter
2. **`rag/`** — Protocol + adapter pattern for retriever (pgvector), embedder (Voyage), prompt assembler, LLM (Anthropic). `pipeline.py` orchestrates; every stage wrapped in `start_as_current_span`
3. **`eval/`** — `llm_judge.py` (Haiku, async, post-response, never blocks user), `feedback.py`, `regression.py`
4. **`corpus/`** — loader (Claude docs), chunker (markdown-header-aware), ingest CLI
5. **`api/`** — FastAPI routes for chat, traces, feedback, admin
6. **Persistence** — single Postgres 16 instance with `pgvector` extension; serves both vector store and trace database

**Cross-cutting additions vs PRD §8:** add `errors.py` (exception hierarchy preventing raw SDK exceptions reaching `api/`), promote `tracer/exporters/__init__.py` to a Protocol-based loader.

### Critical Pitfalls

1. **Async span context loss → orphaned eval span.** `rag.eval` must be a child of `rag.request`. OTel context breaks across `BackgroundTasks`. Snapshot `otel_context.get_current()` before root.end(), re-attach inside the eval coroutine. *Phase 2 helper, Phase 3 wiring.*
2. **Embedding model mismatch → silent retrieval garbage.** Vector scores remain "normal" but semantic match is meaningless when query and corpus use different embedders. Store `embedding_model` metadata on every chunk; assert match at startup; fail fast. *Phase 1.*
3. **Judge model alias drift → false time-series discontinuities.** Pinning to `claude-haiku-3-5` (alias) causes step changes when Anthropic deploys a new dated snapshot. Pin to a dated snapshot; record `judge_model` on every `rag.eval` span. *Phase 3.*
4. **Tracer overhead breaches 100ms budget.** Sync DB writes or large JSONB payloads in the hot path. Use bounded `asyncio.Queue.put_nowait`; separate `span_payloads` side table for full prompt/response. *Phase 2.*
5. **Bad-answer queue becomes write-only.** Without operational pressure, triaging slips and G4 (the regression-from-feedback loop) becomes a dead UI feature. Sort queue by score, auto-close on re-pass, one-command CLI promote, dashboard widget showing weekly resolutions. *Phase 3 + 4.*

(Six more major pitfalls covered in PITFALLS.md, including chunking strategy, judge prompt-injection defenses, OTel attribute drift, regression set overfitting, corpus version drift, Docker Compose demo failure.)

## Implications for Roadmap

The PRD §11 phase structure (Phase −1 design + Phases 0–5 execution) is sound and research confirms it. Phase −1 is doing genuine work: it resolves all GSD-OPEN-N items into ADRs, authors the proactive coverage regression set, and locks the OTel attribute name constants. Skipping Phase −1 would compound mistakes in every downstream phase.

### Suggested Phase Structure (Coarse Granularity — matches PRD §11)

#### Phase −1: Research & Design Artifacts (~2 hr, no code)
**Rationale:** All GSD-OPEN-N items must be resolved before code; OTel attribute drift, embedding metadata mandate, judge calibration plan, and proactive coverage set are all expensive to retrofit.
**Delivers:** ADRs for GSD-OPEN-1..9, system architecture diagram, sequence diagram, trace schema spec, DB ERD, API contract, UI wireframes, module dependency diagram, risk + scope-trim plan.
**Addresses (from FEATURES):** All design — defines what every later phase builds.
**Avoids (from PITFALLS):** #3 (embedding metadata mandate), #4 (judge calibration plan), #5 (chunking ADR), #8 (judge prompt design), #9 (attribute constants design), #10 (proactive coverage set authored).

#### Phase 0: Skeleton & Infra (~30 min)
**Rationale:** Compose stack must boot green before any feature work; pinning + env validation prevents demo failures later.
**Delivers:** Repo scaffold per ARCHITECTURE.md layout, `docker compose up` boots green (FastAPI hello-world, Vite hello-world, Postgres+pgvector), pre-commit hooks (ruff, mypy, tsc), README skeleton.
**Uses:** Postgres 16 + pgvector image, Tailwind v3 pin, Docker Compose with pinned image tags.
**Avoids:** #2 (lifespan handler skeleton), #12 (compose pinning, env validation).

#### Phase 1: RAG Pipeline + Chat UI + Corpus Admin (~3 hr)
**Rationale:** Functional bot first; tracer in Phase 2 is additive instrumentation. This sequencing keeps the foundation working while observability is built.
**Delivers:** `tracer-ai ingest` CLI, retriever/prompt/LLM Protocols + adapters, `POST /chat`, admin endpoints, Chat UI with citations + latency/token/cost row + thumbs controls (handlers in Phase 3), Admin UI for corpus listing + re-index.
**Uses:** Voyage AI `voyage-code-3`, pgvector, markdown-header-aware chunker, Anthropic Sonnet 4.5.
**Implements:** `tracer/span.py` + `tracer/context.py` (Protocol-only; no exporter yet; pipeline imports tracer but spans are no-ops in this phase).
**Avoids:** #3 (corpus records embedding_model metadata), #5 (chunker implementation), #7 (`indexed_at` per chunk).

#### Phase 2: Tracer + Trace Explorer (~2.5 hr)
**Rationale:** Now that the pipeline works, instrumentation is additive. Trace store exporter + dashboard list/detail views surface what was already happening.
**Delivers:** `tracer/exporters/postgres.py` (async-queue writer), pipeline stages wrapped in `start_as_current_span`, `GET /traces` (list + filter), `GET /traces/{id}` (detail), Dashboard trace list + trace detail views (waterfall + payload inspectors).
**Uses:** Postgres 16 JSONB, OTel attribute constants in `tracer/span.py`, Tremor for charts (charts wired in Phase 3).
**Implements:** `tracer/exporters/postgres.py`, span attributes following OTel GenAI naming.
**Avoids:** #1 (context snapshot helper), #2 (queue + flush logic), #6 (overhead budget enforced), #9 (attribute constants file).

#### Phase 3: Quality Layer + Feedback (~2 hr)
**Rationale:** Eval and feedback close the "why did it fail?" loop — the project thesis. Bad-answer queue is the UI surface that ties feedback to traces.
**Delivers:** LLM-as-judge worker (Haiku, async via `BackgroundTasks`, writes faithfulness/relevance to `rag.eval` span), feedback endpoint + UI wiring, bad-answer queue view ("mark resolved" action), time-series charts (latency p50/p95, cost, faithfulness, feedback ratio).
**Uses:** Date-pinned Haiku snapshot, XML-delimited judge prompt with inert-data instruction, Tremor `AreaChart`/`LineChart`.
**Implements:** Per-stage failure diagnosis tag on trace detail (NEW vs PRD — research-identified differentiator).
**Avoids:** #4 (judge model pin + calibration), #8 (delimiter prompts), #11 (queue sort + dashboard widget).

#### Phase 4: Eval CLI + Regression Set (~1.5 hr)
**Rationale:** CLI closes the loop by running both reactive (promoted) and proactive (Phase −1 coverage) regression sets.
**Delivers:** `tracer-ai eval` CLI runs curated query set, prints pass/fail markdown/JSON report, "Promote to regression set" action on bad-answer queue items writes to regression query file.
**Uses:** Click/Typer for CLI, eval queries authored in Phase −1.
**Avoids:** #10 (CLI runs both reactive AND proactive sets), #11 (CLI auto-closes self-resolved items).

#### Phase 5: Polish + Demo Path (~1 hr)
**Rationale:** Demo reproducibility is what makes this a portfolio artifact, not a developer toy.
**Delivers:** README with embedded architecture diagram, GIF/screenshots, cost widget, JSON trace export, scripted "stale doc" demo scenario, clean-state acceptance test.
**Avoids:** #7 (snapshot fixture for demo, not live URLs), #12 (clean-state test on a fresh machine).

### Phase Ordering Rationale

- **Design-first (Phase −1) is non-negotiable.** Six of twelve identified pitfalls are addressed *only* by Phase −1 design. Skipping it means retrofitting every one of them.
- **Functional-before-instrumented (Phase 1 before Phase 2)** keeps the project shippable at every checkpoint. Pipeline works in Phase 1; Phase 2 is pure instrumentation addition.
- **Eval after trace storage (Phase 3 after Phase 2)** because the eval span needs the trace storage exporter to write into.
- **CLI after dashboard (Phase 4 after Phase 3)** because the CLI's "promote to regression" action depends on the bad-answer queue.
- **Polish last (Phase 5)** because demo scenarios must be tested against the final integrated system.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase −1:** *itself a research phase* — no separate planning research needed; Phase −1 = the planning research.
- **Phase 3:** Judge prompt design and threshold calibration — RAGAS-style published patterns are starting point but require ~30 hand-labeled traces for calibration. Plan extra time if calibration set is not ready.

Phases with standard patterns (light research suffices):
- **Phase 0** — Docker Compose + FastAPI hello-world is well-documented.
- **Phase 1** — RAG pipeline is well-documented; pattern follows ARCHITECTURE.md.
- **Phase 2** — Tracer pattern is fully specified in ARCHITECTURE.md.
- **Phase 4** — CLI patterns (Click/Typer) are standard.
- **Phase 5** — Demo path follows §12 of PRD.

## GSD-OPEN-N Resolution Status

Status of each open question from PRD §10 after research:

| ID | Question | Status | Resolution |
|----|----------|--------|------------|
| GSD-OPEN-1 | Charting library | **Resolved by research** | Tremor v3 (wraps Recharts; declarative; saves ~75% LoC) |
| GSD-OPEN-2 | Vector store | **Resolved by research** | pgvector (consolidates with trace store; one Postgres) |
| GSD-OPEN-3 | Embedding provider | **Resolved by research** | Voyage AI `voyage-code-3` + sentence-transformers offline fallback |
| GSD-OPEN-4 | Trace storage backend | **Resolved by research** | Postgres 16 + JSONB (pairs with pgvector; GIN indexes) |
| GSD-OPEN-5 | Observability strategy | **Resolved by research** | Custom + OTel GenAI conventions (PRD's leaning is correct; differentiator) |
| GSD-OPEN-6 | Chunking strategy | **Resolved by research** | Markdown-header-aware default; admin-tunable size + overlap |
| GSD-OPEN-7 | Re-ranking | **Resolved by research** | Ship v1 without; config flag for post-baseline addition |
| GSD-OPEN-8 | Judge prompts + thresholds | **Resolved by research, requires calibration** | RAGAS-style prompts; XML-delimited input; calibrate against 30 hand-labeled traces in Phase 3 |
| GSD-OPEN-9 | Auth + deployment for v1.5 | **ADR-only, no v1 implementation** | Capture direction in ADR; do not implement |

**Net:** All 9 GSD-OPEN-N items have research-backed recommendations ready for ADR drafting in Phase −1. None require user input before Phase −1 begins. GSD-OPEN-5 was the only item the PRD flagged as user-pending; research recommends staying with the PRD's leaning (custom + OTel) — user can override during Phase −1 ADR review.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All locked choices verified current; all 4 open decisions resolved with Context7-sourced rationale |
| Features | HIGH | All competitor platforms surveyed via Context7 official docs; gap (per-stage diagnosis tag) identified |
| Architecture | HIGH | OTel SDK + FastAPI BackgroundTasks patterns verified; 3 module additions vs PRD §8 justified |
| Pitfalls | HIGH | 12 specific pitfalls; each mapped to a phase; prevention strategies are concrete code/config |

**Overall confidence:** HIGH

### Gaps to Address

- **Voyage AI `voyage-code-3` pricing** — not verified in research; check `https://docs.voyageai.com/docs/pricing` before Phase −1 ADR for GSD-OPEN-3 is finalized. If pricing is a blocker, `nomic-embed-text-v1.5` (sentence-transformers) is a production-quality fallback.
- **`@tremor/react` vs `tremor` npm package name** — confirm at install time during Phase 0.
- **`claude-sonnet-4-5` and `claude-haiku-3-5` exact dated snapshot IDs** — verify at runtime via `client.models.list()` in case newer dated snapshots exist by build time.
- **Judge calibration set (~30 hand-labeled traces)** — not yet authored; Phase 3 must include a calibration step before going live with thresholds.
- **Proactive coverage regression queries (10+)** — must be authored in Phase −1; covers each major Claude API doc section (auth, models, prompts, tools, batches, files, citations, vision, etc.).

---
*Research summary for: tracer-ai*
*Researched: 2026-05-04*
