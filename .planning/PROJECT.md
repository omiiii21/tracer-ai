# tracer-ai

## What This Is

A portfolio-grade RAG chatbot built around the thesis that **AI-native observability is the product, and the chatbot is the test bed**. Every stage of the RAG pipeline (query → retrieval → prompt assembly → LLM call → output) is instrumented as a structured trace; a dashboard surfaces semantic quality drift; flagged "bad answers" become regression test cases that close the loop. The chatbot answers questions about the Anthropic Claude API + Claude Agent SDK documentation — making it self-referential, demoable, and giving clear ground truth for evaluation.

## Core Value

When a RAG bot misanswers, the operator can open the trace and see exactly *which stage failed* — retriever returned wrong chunks, LLM ignored the right chunks, corpus was stale, prompt template degraded. Per-step traces with semantic quality metrics turn debugging from guesswork into diagnosis.

## Requirements

### Validated

(None yet — ship to validate)

### Active

<!-- Top-level capabilities. Detailed requirements live in REQUIREMENTS.md. -->

- [ ] Working RAG chat over Claude API docs with citation-backed answers
- [ ] Every request produces a complete, replayable trace (all spans, payloads, scores, costs)
- [ ] Quality metrics dashboard surfaces drift (faithfulness, relevance, latency, cost, feedback ratio)
- [ ] "Bad answers" flow into regression tests via thumbs-down → review queue → CLI
- [ ] Modular architecture (every external dep behind a typed Protocol)
- [ ] Local Docker Compose deployment reproduces the full demo in ≤15 minutes
- [ ] Corpus admin UI for re-indexing, viewing chunk counts, tuning chunking config
- [ ] LLM-as-judge auto-evaluation (faithfulness + relevance) on every trace, async

### Out of Scope

- **Authentication / multi-tenant** — single-user local deployment first; auth is a future axis but not v1
- **Production hosting / SLA** — local Docker Compose is the deployment target
- **Streaming responses** — server-side streaming to chat UI deferred to v2
- **Multi-modal input** — no PDFs with images, audio queries, etc.
- **Agentic tool-use beyond retrieval** — single-step retrieve-then-answer; no multi-hop / re-querying agents in v1
- **Cross-session conversational memory** — within-session history allowed, no persistence across sessions

## Context

**Source documents:**
- `tracer-ai-foundation-prd.md` — locked foundation PRD; canonical source of decisions and open questions
- `About.md` — original brief; canonical source for the "why"

**Project framing:**
- Doubles as a learning artifact (deeply understand AI observability) and the foundation for a future productizable MVP (an observability-first RAG platform)
- All architectural decisions favor **modularity, explicit instrumentation, and provider-portability**
- Self-referential narrative: "I built an observable RAG bot for the Claude API, using Claude" — strong portfolio story

**Why custom observability over Langfuse/Phoenix:**
- Frameworks abstract away the very pipeline stages we want to instrument
- Explicit code = clean instrumentation = stronger portfolio story
- OpenTelemetry GenAI semantic conventions in the trace schema preserve portability — trivially exportable to any OTel-compatible backend later

**Trace schema (the heart of the system):**
- Root: `rag.request`
- Spans: `rag.retrieve` → `rag.prompt_assemble` → `rag.llm_call` → `rag.eval` (async)
- Out-of-band: `feedback.user`
- Attributes follow OTel GenAI conventions where defined; extends with RAG-specific attrs (`rag.retrieved_chunks`, `rag.retrieval.score.mean`)

**Build target:** ~12 working hours, 6 phases (Phase −1 research/design + Phases 0–5 execution).

## Constraints

- **Tech stack — Backend**: Python 3.12+, FastAPI, Pydantic v2 — locked. Rationale: best AI ecosystem, type-safe I/O, auto OpenAPI for the React client.
- **Tech stack — LLM**: Anthropic Claude (Sonnet 4.5 default; Haiku for judge) — locked. Rationale: user choice; strong reasoning for technical Q&A; cost-conscious judge.
- **Tech stack — Orchestration**: None — direct Anthropic SDK calls. Rationale: frameworks (LangChain, LlamaIndex) abstract away the pipeline stages we want to instrument.
- **Tech stack — Frontend**: Vite + React 18 + TypeScript + Tailwind + shadcn/ui — locked. Rationale: lightweight SPA against FastAPI; no need for Next.js's SSR/API routes.
- **Tech stack — Containerization**: Docker Compose — locked. Rationale: reproducible local dev; trivial future lift to single-node cloud host.
- **Code quality**: type hints everywhere; `ruff` + `mypy --strict`-clean; Pydantic for all I/O; meaningful docstrings on public functions only.
- **Testing**: unit tests per adapter + tracer core; integration tests for full RAG path with mocked LLM; eval CLI doubles as integration test.
- **Performance**: end-to-end answer < 5s for typical query; trace write must not add > 100ms to request path (async-emit).
- **Reproducibility**: `docker compose up` starts entire stack; seed script ingests Claude docs.
- **Modularity**: every external dependency (LLM, embedder, vector store, trace store) behind a typed Python `Protocol`. No direct SDK calls outside their adapter.
- **Observability of the observability**: tracer itself logs structured events; failures in eval pipeline must not fail user requests.
- **Cost-conscious defaults**: judge uses Haiku (cheap); bot uses Sonnet 4.5; embedding cache to avoid re-embedding identical chunks.
- **Documentation**: README + architecture diagram + ADR-style notes for each major decision in `/docs/decisions/`.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Build custom observability over wrapping Langfuse/Phoenix | Educational value; explicit instrumentation = portfolio thesis; OTel conventions preserve portability | Locked in `docs/decisions/005-observability-strategy.md` (Phase 1) |
| OpenTelemetry GenAI semantic conventions for span attributes | Portability — can swap to any OTel backend without re-instrumenting | Locked in `docs/decisions/005` + `docs/trace-schema.md` (Phase 1) — `gen_ai.provider.name`, NOT deprecated `gen_ai.system` |
| Self-referential corpus (Claude API docs) | Demoable, clear ground truth, strong narrative ("Anthropic-bot using Anthropic") | Locked — coverage set authored at `docs/eval/coverage_set.yaml` (Phase 1) |
| Direct Anthropic SDK over orchestration frameworks | Frameworks hide the very pipeline stages we want to instrument | Locked in `docs/decisions/005` + `docs/architecture.md` (Phase 1) |
| Anthropic Claude as LLM (Sonnet 4.5 bot, Haiku judge) | User preference; cost-conscious; strong reasoning | Locked — Sonnet `claude-sonnet-4-5-20250929`, Haiku `claude-haiku-4-5-20251001` (dated snapshots) — `docs/decisions/008-judge-prompts-thresholds.md` (Phase 1) |
| Phase 1 (research + design artifacts) before any code | All ADRs/diagrams/wireframes locked before Phase 2 — downstream phases are pure execution | Validated — Phase 1 complete 2026-05-04; fresh-agent docs check PASSED (`docs/_verification.md`); 10/10 must-haves verified |
| Single-user local Docker Compose for v1 (no auth, no hosting) | Scope discipline — observability story is the deliverable, not infrastructure | Locked in `docs/decisions/009-auth-deployment-direction.md` (Phase 1) |

## Open Questions Resolved in Phase 1

All 9 `[GSD-OPEN-N]` items from the foundation PRD §10 are now codified as ADRs in `/docs/decisions/`. See `docs/decisions/README.md` for the index.

| ID | Question | Resolved In | Decision |
|----|----------|-------------|----------|
| GSD-OPEN-1 | Charting library | `docs/decisions/001-charting-library.md` | Tremor v3 (Tailwind v3 pinned) |
| GSD-OPEN-2 | Vector store | `docs/decisions/002-vector-store.md` | pgvector on the same Postgres 16 as the trace DB |
| GSD-OPEN-3 | Embedding provider | `docs/decisions/003-embedding-provider.md` | Voyage AI `voyage-code-3` primary; `sentence-transformers nomic-embed-text-v1.5` offline fallback. Pricing verification = Phase 2 INFRA-01 prereq |
| GSD-OPEN-4 | Trace storage backend | `docs/decisions/004-trace-storage.md` | Postgres 16 + JSONB; `spans` partitioned by `started_at` monthly |
| GSD-OPEN-5 | Observability strategy | `docs/decisions/005-observability-strategy.md` | Custom tracer using OTel GenAI attribute names as Python constants; **no `opentelemetry-sdk` runtime dep** |
| GSD-OPEN-6 | Chunking strategy | `docs/decisions/006-chunking-strategy.md` | Markdown-header-aware splitter; default `chunk_size=900`, `overlap=100`; admin-tunable |
| GSD-OPEN-7 | Re-ranking | `docs/decisions/007-reranking.md` | None in v1; `ENABLE_RERANKER` config flag reserved for v2 |
| GSD-OPEN-8 | LLM-as-judge prompts and thresholds | `docs/decisions/008-judge-prompts-thresholds.md` | RAGAS-style prompts; XML-delimited untrusted content; threshold calibrated against ~30 hand-labeled traces in Phase 5 EVAL-06 |
| GSD-OPEN-9 | Auth + deployment for v1.5 | `docs/decisions/009-auth-deployment-direction.md` | ADR-only direction (intent captured); no v1 implementation |

A 10th ADR — `docs/decisions/010-scope-trim.md` — codifies the >25% budget-slip cut order (DSGN-09).

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-05-06 after Phase 4 (Tracer + Trace Explorer) completion. 13/14 phase requirements PASS (TRCR-04 deferred to Phase 5 EVAL-04 for OTel context propagation). Trace write p95 delta -14.78ms vs 100ms budget. Phase 5 (Quality Layer + Feedback) is unblocked.*
