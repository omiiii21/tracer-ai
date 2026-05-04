# tracer-ai — Foundation PRD

> Format note: This is a **foundation PRD** intended as input to the GSD framework. Locked decisions reflect the user's explicit choices during planning. Open questions are flagged with `[GSD-OPEN]` tags and accompanied by alternatives for GSD to research, decide, and document before execution.

---

## 1. Context

LLM applications fail silently. A RAG chatbot can return HTTP 200, sub-second latency, healthy infrastructure metrics — and still confidently produce a hallucinated, irrelevant, or unsafe answer. Traditional observability (uptime, error rates, latency) is blind to these failures because they are *semantic*, not *operational*.

**tracer-ai** is a portfolio-grade RAG chatbot built around the thesis that **AI-native observability is the product, and the chatbot is the test bed**. Every stage of the RAG pipeline (query → retrieval → prompt assembly → LLM call → output) is instrumented as a structured trace; a dashboard surfaces semantic quality drift; flagged "bad answers" become regression test cases that close the loop.

The build doubles as a learning artifact (deeply understand AI observability) and the foundation for a future productizable MVP (an observability-first RAG platform). All architectural decisions favor **modularity, explicit instrumentation, and provider-portability**.

Source brief: [About.md](../../../../Desktop/tracer-ai/About.md)

---

## 2. Problem Statement

Teams shipping RAG-based LLM applications have no way to answer **"why did the AI give this wrong answer?"** at production scale. Existing tools fall into two camps, neither sufficient:

1. **Generic APM (Datadog, New Relic, Grafana)** — measures the request, not the reasoning. A bad answer and a good answer look identical.
2. **Hosted LLM observability platforms (LangSmith, Langfuse Cloud)** — solve this for you, but as a black box; teams adopt them without understanding what's being measured or why.

Concretely, when a RAG bot misanswers a question, an engineer today cannot easily distinguish between:

- The **retriever** returned wrong/irrelevant chunks
- The **retriever** returned right chunks but the **LLM ignored them** (prompt failure)
- The **document corpus** is stale or missing the answer
- The **prompt template** changed and degraded behavior
- The **embedding model or chunking strategy** is poorly tuned

Without per-step traces and quality metrics, every debugging session is guesswork.

---

## 3. Solution Overview

A self-contained system with three intertwined layers:

```
┌─────────────────────────────────────────────────────────────────┐
│                    FRONTEND (Vite + React + TS)                 │
│  ┌───────────┐  ┌─────────────────┐  ┌──────────────────────┐   │
│  │  Chat UI  │  │ Trace Explorer  │  │ Corpus Admin / Eval  │   │
│  └─────┬─────┘  └────────┬────────┘  └──────────┬───────────┘   │
└────────┼─────────────────┼──────────────────────┼───────────────┘
         │                 │                      │
         ▼                 ▼                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                       FASTAPI BACKEND                           │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │            RAG Pipeline (instrumented)                   │   │
│  │   query → retriever → prompt assembler → LLM → answer    │   │
│  └──────────────────────────────────────────────────────────┘   │
│                            │ emits spans                        │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              Tracer (OTel-aligned schema)                │   │
│  │   - per-stage spans with AI-native attributes            │   │
│  │   - LLM-as-judge eval pipeline                           │   │
│  │   - manual feedback ingestion                            │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
         │                                          │
         ▼                                          ▼
┌──────────────────────┐                 ┌────────────────────────┐
│   Vector Store       │                 │  Trace Storage (DB)    │
│   (chunks + embeds)  │                 │  (spans, metrics, fb)  │
└──────────────────────┘                 └────────────────────────┘
```

**Self-referential corpus.** The chatbot answers questions about the **Anthropic Claude API + Claude Agent SDK** documentation. This makes the project demoable, gives clear ground truth for eval, and produces a strong portfolio narrative ("I built an observable RAG bot for the Claude API, using Claude").

---

## 4. Goals & Non-Goals

### 4.1 Goals (success criteria)

| # | Goal | How we'll know it's met |
|---|------|--------------------------|
| G1 | A working RAG chat over Claude API docs | User asks "How do I cache prompts?" and gets an accurate, citation-backed answer |
| G2 | Every request produces a complete, replayable trace | Open any answer in the dashboard → see query, all retrieved chunks (with scores), full assembled prompt, LLM output, latency per stage, token + cost breakdown |
| G3 | Quality metrics surface drift, not just outages | Dashboard shows time-series of faithfulness, relevance, manual-feedback ratio, similarity scores. Alert thresholds configurable |
| G4 | "Bad answers" feed regression tests | Thumbs-down on chat → trace lands in review queue → reviewed traces become entries in a regression test set runnable from CLI |
| G5 | Modular architecture supports productizable-MVP evolution | Every component (LLM provider, embedder, vector store, trace store) lives behind a typed interface; swapping any one requires no changes to others |
| G6 | The project is portfolio-presentable | README + architecture diagram + recorded demo + meaningful commit history; runs locally via `docker compose up` |

### 4.2 Non-goals (initial scope)

- **Authentication / multi-tenant.** Single-user local deployment first. Auth is a known future axis but not required for v1.
- **Production hosting / SLA.** Local Docker Compose is the deployment target.
- **Streaming responses.** Server-side streaming to the chat UI is deferred (out of scope for v1; nice-to-have for v2).
- **Multi-modal input** (PDFs with images, audio queries, etc.).
- **Agentic tool-use beyond retrieval.** The RAG pipeline is a single-step retrieve-then-answer; multi-hop / re-querying agents are out of scope for v1.
- **Conversational memory across sessions.** Each query is treated independently; chat history within one session is allowed but not cross-session memory.

---

## 5. Personas

| Persona | Description | Primary surface |
|---------|-------------|-----------------|
| **End user (Asker)** | Developer who wants quick answers about the Claude API while building | Chat UI |
| **Reviewer / Operator (you)** | Inspects traces, triages bad answers, tunes prompts/retrievers | Trace Explorer + Admin UI |
| **Evaluator (CI / cron)** | Runs regression tests on every change; checks for quality drift | CLI + (later) CI integration |

---

## 6. Functional Requirements

### 6.1 Chat UI (`/chat`)
- Single-turn or multi-turn (within session) conversational interface
- Sends query → backend → renders answer + cited source chunks (clickable to expand)
- Per-message thumbs-up / thumbs-down + free-text feedback box on thumbs-down
- Each message displays: latency, token count, estimated cost
- Link from any message to its full trace in the Trace Explorer

### 6.2 Trace Explorer / Observability Dashboard (`/dashboard`)
- **Overview metrics** (configurable time window): request volume, p50/p95 latency, total tokens, total cost, faithfulness score distribution, manual-feedback ratio
- **Trace list view**: filterable/searchable table (by query text, time range, feedback rating, faithfulness score, latency bucket)
- **Trace detail view**: drill into a single request, see every span (retrieval, prompt assembly, LLM call, eval) with timing waterfall, full payloads (chunks + scores, full prompt, full response), and any auto-eval scores
- **Bad-answer queue**: subset of traces with thumbs-down OR auto-eval below threshold; mark resolved / promote to regression set
- **Quality drift charts**: faithfulness, relevance, latency, cost over time

### 6.3 Eval / Regression CLI (`tracer-ai eval`)
- Runs a curated set of (query, expected answer / acceptance criteria) pairs against the live pipeline
- Reports per-query: pass/fail, faithfulness score, latency, cost
- Aggregates into a regression report (markdown or JSON)
- Supports adding traces from the bad-answer queue to the regression set

### 6.4 Corpus Admin UI (`/admin`)
- Upload / re-index documents (drag-drop or URL list for the Claude docs)
- View current corpus: docs, chunk count, embedding model, last-indexed timestamp
- Trigger re-index with different chunking config (size, overlap)
- Display retrieval test queries (e.g., "What models are available?" → expected to retrieve `models.md` chunks)

---

## 7. Non-Functional Requirements

| Category | Requirement |
|----------|-------------|
| **Modularity** | Every external dependency (LLM, embedder, vector store, trace store) behind a typed Python `Protocol`. No direct SDK calls outside its adapter. |
| **Code quality** | Type hints everywhere; `ruff` + `mypy --strict`-clean; FastAPI with Pydantic models for all I/O; meaningful docstrings on public functions only |
| **Testing** | Unit tests for each adapter + the tracer core; integration tests for the full RAG path with mocked LLM; the eval CLI doubles as a higher-level integration test |
| **Performance** | Single-user local target: end-to-end answer < 5s for typical query; trace write must not add > 100ms to request path (async-emit to trace DB) |
| **Reproducibility** | `docker compose up` starts the entire stack (backend, frontend, vector store, trace DB); seed script ingests Claude docs |
| **Observability of the observability** | The tracer itself logs structured events; failures in the eval pipeline don't fail the user request |
| **Cost-conscious defaults** | LLM-as-judge uses Claude Haiku (cheap) by default; bot uses Claude Sonnet 4.5; configurable. Embedding cache to avoid re-embedding identical chunks |
| **Documentation** | README with architecture diagram + setup; ADR-style notes for each major decision in `/docs/decisions/` |

---

## 8. Architecture & Module Breakdown

Locked module layout (Python backend):

```
tracer_ai/
├── tracer/                # Core observability primitives
│   ├── span.py            # Span dataclass (OTel-aligned + AI-native attrs)
│   ├── context.py         # Context propagation, span emission
│   ├── store.py           # Protocol for trace storage backends
│   └── exporters/         # Local (Postgres/SQLite) + optional OTel/Langfuse
├── rag/                   # The RAG pipeline (every step is a span)
│   ├── retriever.py       # Protocol + Chroma/Qdrant adapter
│   ├── embedder.py        # Protocol + Voyage/OpenAI adapter
│   ├── prompt.py          # Prompt assembly with citation formatting
│   ├── llm.py             # Protocol + Anthropic adapter
│   └── pipeline.py        # Orchestration (the single instrumented path)
├── eval/                  # Quality measurement
│   ├── llm_judge.py       # Faithfulness + relevance via Claude Haiku
│   ├── feedback.py        # Manual feedback ingestion
│   └── regression.py      # Curated query set runner
├── corpus/                # Document ingestion + indexing
│   ├── loader.py          # Pull/parse Claude docs (markdown + HTML)
│   ├── chunker.py         # Configurable chunking
│   └── ingest_cli.py
├── api/                   # FastAPI app
│   ├── main.py
│   ├── chat.py
│   ├── traces.py          # Read-side for dashboard
│   ├── feedback.py
│   └── admin.py
├── cli/                   # Operator CLI (eval, ingest, ops)
│   └── __main__.py
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

### Trace schema (the heart of the system)

Every chat request emits a **trace** with the following spans (each with `parent_span_id` for nesting):

```
Span: rag.request           (root)
  ├─ rag.retrieve           (attrs: query, top_k, retriever_name, embedding_model)
  │     └─ events: chunk_returned (attrs: doc_id, chunk_id, score, text)
  ├─ rag.prompt_assemble    (attrs: prompt_template_id, prompt_token_count)
  ├─ rag.llm_call           (attrs: model, input_tokens, output_tokens, cost_usd, latency_ms, finish_reason)
  └─ rag.eval               (attrs: faithfulness, relevance, judge_model, judge_cost) [async, post-response]

Out-of-band:
  feedback.user             (attrs: rating, comment, attached_to_trace_id) [user-triggered]
```

Span attributes follow the **OpenTelemetry GenAI semantic conventions** where defined (`gen_ai.system`, `gen_ai.request.model`, `gen_ai.usage.input_tokens`, etc.) and extend with RAG-specific attrs (`rag.retrieved_chunks`, `rag.retrieval.score.mean`, etc.). This makes traces portable to any OTel-compatible backend later.

---

## 9. Locked Tech Stack

| Layer | Choice | Rationale |
|---|---|---|
| Backend language | **Python 3.12+** | Best AI ecosystem, user preference |
| Web framework | **FastAPI + Pydantic v2** | Type-safe I/O, auto OpenAPI for the React client |
| LLM | **Anthropic Claude (Sonnet 4.5 default; Haiku for judge)** | User choice; strong reasoning for technical Q&A |
| Orchestration | **None — direct Anthropic SDK calls** | Frameworks abstract away the very pipeline stages we want to instrument; explicit code = clean instrumentation = stronger portfolio story |
| Frontend | **Vite + React 18 + TypeScript + Tailwind + shadcn/ui** | Lightweight SPA against FastAPI; no need for Next.js's SSR/API routes |
| Charts (dashboard) | **Recharts or Tremor** [GSD-OPEN-1] | Both work with React + Tailwind |
| Containerization | **Docker Compose** | Reproducible local dev; trivial future lift to a single-node cloud host |
| Code quality tooling | **ruff, mypy, pytest, pre-commit** | Standard Python toolchain |

---

## 10. Open Questions for GSD

> GSD should research each, document the decision in `/docs/decisions/NNN-<slug>.md` (ADR format), and then implement.

### [GSD-OPEN-1] Charting library for the dashboard
- **Options**: Recharts (mature, declarative), Tremor (purpose-built for dashboards, Tailwind-native), Visx (low-level, flexible)
- **Decision criteria**: speed of building the time-series + distribution charts in §6.2; bundle size; how well it composes with shadcn/ui

### [GSD-OPEN-2] Vector store
- **Options**: Chroma (simple, embedded, dev-friendly), Qdrant (production-ready, Docker), pgvector (one-DB stack with trace store), Weaviate (overkill for MVP)
- **Decision criteria**: ease of local dev, ability to filter on metadata, future MVP-readiness, ops surface area
- **Recommendation to validate**: Qdrant for production-readiness, OR pgvector to consolidate to one Postgres instance for both vectors and traces

### [GSD-OPEN-3] Embedding provider
- **Constraint**: Anthropic does not provide embeddings.
- **Options**: Voyage AI (Anthropic's recommended embedding partner; voyage-3 / voyage-code-3), OpenAI (text-embedding-3-large / -small), open-source via sentence-transformers (BGE, nomic-embed-text), Cohere
- **Decision criteria**: quality on technical-doc retrieval, cost, ease of local-only operation, dependency on additional API keys
- **Recommendation to validate**: Voyage AI for narrative coherence ("Anthropic-recommended embedder for an Anthropic-bot"); fallback to a local sentence-transformers model for offline dev

### [GSD-OPEN-4] Trace storage backend
- **Options**: Postgres (with JSONB for span attrs; widely understood; pairs well with pgvector if chosen), SQLite (zero-ops for portfolio, anemic for time-series), ClickHouse (best for span queries at scale; heavy for v1), DuckDB (interesting analytical option, embedded)
- **Decision criteria**: query patterns needed for §6.2 (time-series aggregations, filtered list views, drill-into-trace), ops simplicity, dev-prod parity
- **Recommendation to validate**: Postgres + JSONB for v1 (clean upgrade path; consolidates with pgvector if chosen)

### [GSD-OPEN-5] Observability backend strategy
- **Options**:
  - **A. Fully custom** — bespoke trace schema, tables, dashboard. Highest learning value, most work.
  - **B. Custom + OTel GenAI conventions** — same as A but spans follow OTel semantic conventions; trivially exportable to any OTel collector later. *(PRD currently leans this way — see §8 trace schema.)*
  - **C. Wrap Langfuse self-hosted** — Langfuse handles trace storage + has a UI; we still build the bad-answer queue, regression CLI, and any custom views. Less to build, less to learn from scratch.
  - **D. Wrap Arize Phoenix** — similar to C; stronger on retrieval-quality eval, weaker on the trace-explorer UX we want.
- **Decision criteria**: Educational value vs. velocity; how customizable the dashboard needs to be; portability to a hosted backend if this becomes a product
- **User has indicated they will read up on Langfuse / Phoenix / LangSmith and weigh in.** GSD should produce a short comparison brief (1-2 pages) before locking.

### [GSD-OPEN-6] Chunking strategy
- **Options**: Fixed-size with overlap (simple baseline), markdown-header-aware (better for docs), semantic chunking (more compute), late-chunking with a long-context embedder
- **Decision criteria**: retrieval quality measured against the regression set; ingestion latency; complexity
- **Recommendation to validate**: markdown-header-aware as the default for technical docs; expose chunk size + overlap as admin-tunable config

### [GSD-OPEN-7] Re-ranking
- **Options**: None (top-K from vector search), cross-encoder reranker (e.g., Cohere Rerank, BGE reranker), LLM-based rerank
- **Decision criteria**: quality lift on the regression set vs. added latency / cost
- **Recommendation to validate**: ship v1 without reranking; add as a config-flag enhancement after baseline metrics exist

### [GSD-OPEN-8] LLM-as-judge prompts and thresholds
- **Open**: exact judge prompts for `faithfulness` (does the answer's claims appear in retrieved chunks?) and `relevance` (does the answer address the query?); threshold below which a trace lands in the bad-answer queue
- **Recommendation to validate**: start with published prompt patterns (RAGAS-style); calibrate thresholds against ~30 hand-labeled traces

### [GSD-OPEN-9] Auth + deployment for v1.5
- **Out of scope for v1** but flagged: when this graduates from local-only, what's the auth and hosting story? Single-user with Clerk/Auth.js? Self-hosted on Fly.io / Railway / Hetzner?
- GSD: **do not implement in v1**; capture the decision direction in an ADR for future reference.

---

## 11. Phased Build Plan (1.5-day target)

> Total target: **~12 working hours**, executed by GSD with AI assistance.
> **Phase −1 is autonomous**: GSD researches every `[GSD-OPEN-N]` item in §10, produces all design artifacts listed below, and proceeds directly into Phase 0 without waiting for human review. Quality is enforced by Phase −1 self-verification (see "Verifiable" below) and by the per-phase verification gates.
> If a phase estimate slips by >25%, GSD pauses and surfaces a scope-trim decision (see "Risk + scope-trim plan" in Phase −1) rather than silently extending.

---

### Phase −1 — Research & Design Artifacts (~2 hr, no code, GSD-autonomous)

**Goal**: Produce every diagram, spec, and decision needed so Phases 0–5 are pure execution. **No coding starts until this phase is fully complete.**

Deliverables (all checked into `/docs/`):

1. **ADRs** — one per `[GSD-OPEN-N]` item in §10, in `/docs/decisions/NNN-<slug>.md`. Each ADR: context, options considered, decision, consequences.
2. **System architecture diagram** (Mermaid `graph` or `flowchart`) — frontend / backend / data stores / external APIs, with arrows labeled by protocol (HTTP, vector query, LLM call).
3. **Chat request sequence diagram** (Mermaid `sequenceDiagram`) — user → React → FastAPI → retriever → embedder → vector store → prompt assembler → Anthropic API → tracer (span emit) → response. Include the async LLM-as-judge branch.
4. **Trace schema spec** (`/docs/trace-schema.md`) — formal table of every span name, every attribute, type, OTel-conformance status, and example payload.
5. **DB schema / ERD** (`/docs/data-model.md`) — Mermaid `erDiagram` for: `traces`, `spans`, `feedback`, `regression_cases`, plus the vector store collection schema.
6. **API contract** (`/docs/api.md`) — endpoint list with request/response Pydantic shapes (or an OpenAPI sketch). Covers: `POST /chat`, `GET /traces`, `GET /traces/{id}`, `POST /feedback`, ingest + admin endpoints.
7. **UI wireframes** (`/docs/wireframes/`) — low-fidelity sketches (ASCII or images from Excalidraw/tldraw) for: chat view, trace list, trace detail, bad-answer queue, admin/corpus view. Polish is not the point; layout intent is.
8. **Module dependency diagram** — confirms the §8 module layout has no circular deps; shows what depends on what.
9. **Risk + scope-trim plan** — if any phase below slips >25%, what gets cut first? **Recommended cut order**: polish phase → admin UI → eval CLI → bad-answer queue (never cut the tracer or chat — they are the thesis).

**Verifiable (self-check)**: A fresh agent given only `/docs/` should be able to answer — what does the system do, how does data flow, what's the trace schema, what API endpoints exist, what does the UI look like — without reading any code. GSD should run this check on itself by spawning a subagent over the docs before exiting Phase −1.

---

### Phase 0 — Skeleton & infra (~30 min)
- Repo scaffold (backend + frontend + infra) per the §8 layout
- `docker compose up` boots an empty stack: FastAPI hello-world, Vite hello-world, Postgres, vector store
- Pre-commit hooks: `ruff`, `mypy`, frontend `tsc`, basic test runner
- README skeleton with setup steps

### Phase 1 — RAG pipeline + chat UI + corpus admin (~3 hr)
- `tracer-ai ingest` CLI: pulls/parses Claude docs, chunks, embeds, writes to vector store
- Retriever + prompt assembly + LLM call wired end-to-end behind the §8 Protocols
- FastAPI `POST /chat` returns answer + cited chunks
- FastAPI admin endpoints: list corpus, trigger re-index, view chunking config
- Chat UI (Vite/React): messages, citations, latency/token/cost row, thumbs-up/down controls (handlers in Phase 3)
- Admin UI: corpus list, re-index button, chunking config form (no fancy upload UX — drag-drop optional, URL-list textarea is fine)
- **Verifiable**: ask 5 hand-picked questions, get reasonable cited answers; trigger a re-index from the admin UI

### Phase 2 — Tracer + trace explorer (~2.5 hr)
- Span emission helpers; wrap every pipeline stage from Phase 1
- Async write path to trace store (must add ≤100ms to request path)
- `GET /traces` (list + filter) and `GET /traces/{id}` (detail)
- Dashboard: trace list view + trace detail view (waterfall + payload inspectors for chunks, prompt, response)
- **Verifiable**: every chat request from Phase 1 now produces a trace; drilling in shows query, every retrieved chunk + score, full assembled prompt, full LLM output

### Phase 3 — Quality layer + feedback (~2 hr)
- LLM-as-judge worker (Claude Haiku) — async, post-response — writes `faithfulness` + `relevance` scores onto the trace
- Manual feedback endpoint; wire the Phase 1 thumbs-up/down + comment box
- Bad-answer queue view (filtered trace list: `feedback=down OR faithfulness < threshold`); "mark resolved" action
- Time-series charts on dashboard: latency p50/p95, cost, faithfulness mean, feedback ratio (24h default window)
- **Verifiable**: thumbs-down lands the trace in the queue within seconds; faithfulness score appears on every trace within ~30s; charts populate as you query

### Phase 4 — Eval CLI + regression set (~1.5 hr)
- `tracer-ai eval` runs the curated query set defined in Phase −1 design, prints pass/fail markdown/JSON report
- "Promote to regression set" action on bad-answer queue items (writes to the regression query file)
- **Verifiable**: deliberately corrupt the prompt template → CLI fails the right queries; promote a bad trace → it appears in the next CLI run

### Phase 5 — Polish + demo path (~1 hr)
- README with architecture diagram (from Phase −1) embedded, GIF or screenshots of the trace explorer + bad-answer queue
- Cost widget on dashboard; trace export as JSON button
- One scripted "bad answer" scenario (e.g., stale doc with deliberately wrong info) for the recorded demo
- **Verifiable**: a fresh `docker compose up` + corpus ingest reproduces the full flow (ask question → see trace → flag bad answer → run regression CLI) in under 15 minutes

---

## 12. End-to-End Acceptance Demo

Per-phase verification lives inline in §11. The project as a whole is "done" when this **single end-to-end demo script** runs cleanly from a fresh checkout in **≤15 minutes**:

1. `docker compose up` — entire stack boots green
2. `tracer-ai ingest --source claude-docs` — corpus indexed; admin UI confirms chunk count and embedding model
3. Open chat UI → ask: "How do I use prompt caching with Claude?" → get a cited, accurate answer
4. Open trace explorer → click the trace → see all spans (retrieve / prompt_assemble / llm_call / eval), each chunk with its similarity score, the full assembled prompt, the full LLM response, latency + cost
5. Ask: "What's the maximum context for Claude Haiku?" (with a deliberately stale doc loaded) → get a wrong answer → click thumbs-down + comment
6. Open bad-answer queue → see the flagged trace → diagnose the cause from the trace (stale chunk) → "Promote to regression set"
7. `tracer-ai eval` — regression CLI runs the curated set + the just-promoted case → reports pass/fail
8. Fix the corpus (re-ingest the corrected doc from admin UI) → re-run `tracer-ai eval` → previously-failing case now passes

If steps 1–8 work without human intervention beyond UI clicks and the documented CLI commands, the project ships.

---

## 13. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Custom observability stack underdelivers vs. Langfuse | OTel GenAI conventions in the trace schema mean we can swap to Langfuse later without re-instrumenting |
| Embedding provider lock-in | All embeddings go through the `Embedder` Protocol; switching is one adapter |
| LLM-as-judge is itself unreliable | Calibrate against hand-labeled traces; show judge cost + latency on dashboard so its overhead is visible; never block user response on judge |
| Scope creep into agentic features | Explicit non-goal in §4.2; revisit only after Phase 5 |
| Dashboard becomes a half-finished UI | Use shadcn/ui blocks aggressively; one polished view (trace detail) beats four mediocre ones |

---

## 14. Critical Files (for GSD execution context)

- [About.md](../../../../Desktop/tracer-ai/About.md) — original brief; canonical source for the "why"
- This PRD — locked decisions and open questions
- (To be created during GSD research phase): `/docs/decisions/` — ADRs resolving each `[GSD-OPEN-N]`

---

## 15. Glossary

- **Trace** — the full record of one user request through the RAG pipeline
- **Span** — a single instrumented step within a trace (e.g., the LLM call)
- **Faithfulness** — does the answer's content appear in the retrieved context? (vs. hallucinated)
- **Relevance** — does the answer address what the user asked?
- **Bad-answer queue** — the curated review pipeline for traces flagged by user feedback or auto-eval
- **OTel GenAI** — OpenTelemetry's emerging semantic conventions for LLM/RAG span attributes

---

*End of foundation PRD. Ready for GSD handoff after `[GSD-OPEN-N]` items are resolved.*
