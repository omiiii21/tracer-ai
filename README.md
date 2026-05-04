# tracer-ai

A portfolio-grade RAG chatbot built around the thesis that **AI-native observability is the product, and the chatbot is the test bed**. Every stage of the RAG pipeline (query → retrieval → prompt assembly → LLM call → output) is instrumented as a structured trace; a dashboard surfaces semantic quality drift; flagged "bad answers" become regression test cases that close the loop. The chatbot answers questions about the Anthropic Claude API + Claude Agent SDK documentation — making it self-referential, demoable, and giving clear ground truth for evaluation.

**Core value:** When a RAG bot misanswers, the operator can open the trace and see exactly *which stage failed* — retriever returned wrong chunks, LLM ignored the right chunks, corpus was stale, prompt template degraded.

## Status

Phase 1 (Research & Design Artifacts) complete — all design contracts locked under [`docs/`](./docs/). Phases 2–7 are implementation.

| Phase | Goal | Status |
|-------|------|--------|
| 1 | Research & Design Artifacts | ✓ Complete |
| 2 | Skeleton & Infrastructure | Not started |
| 3 | RAG Pipeline + Chat UI + Corpus Admin | Not started |
| 4 | Tracer + Trace Explorer | Not started |
| 5 | Quality Layer + Feedback | Not started |
| 6 | Eval CLI + Regression Set | Not started |
| 7 | Polish + Demo Path | Not started |

## Documentation

A fresh agent given only `/docs/` can answer what the system does, how data flows, what the trace schema is, what API endpoints exist, and what the UI looks like — without reading any code.

- **Architecture:** [`docs/architecture.md`](./docs/architecture.md), [`docs/module-deps.md`](./docs/module-deps.md)
- **Decisions:** [`docs/decisions/`](./docs/decisions/) — 10 ADRs (one per locked decision)
- **Data flow:** [`docs/sequence-diagrams.md`](./docs/sequence-diagrams.md)
- **Trace schema:** [`docs/trace-schema.md`](./docs/trace-schema.md)
- **Data model:** [`docs/data-model.md`](./docs/data-model.md)
- **API contract:** [`docs/api.md`](./docs/api.md)
- **Wireframes:** [`docs/wireframes/`](./docs/wireframes/)
- **Evaluation:** [`docs/eval/coverage_set.yaml`](./docs/eval/coverage_set.yaml)

## Stack (locked)

- **Backend:** Python 3.12, FastAPI, Pydantic v2, direct Anthropic SDK (no orchestration framework)
- **LLM:** Claude Sonnet 4.5 (`claude-sonnet-4-5-20250929`) — bot; Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) — judge
- **Embeddings:** Voyage AI `voyage-code-3` (primary), `sentence-transformers nomic-embed-text-v1.5` (offline fallback)
- **Persistence:** Postgres 16 + JSONB + `pgvector` extension (single instance: trace store + vector store)
- **Frontend:** Vite + React 18 + TypeScript + Tailwind v3 + shadcn/ui + Tremor v3
- **Containerization:** Docker Compose v2

## Observability strategy

Custom tracer that adopts OpenTelemetry GenAI semantic conventions as **attribute names only** (Python constants), without taking a runtime dependency on `opentelemetry-sdk`. Spans go through a bounded `asyncio.Queue` to a Postgres+JSONB exporter — trace writes add ≤100ms p95 to the request path. Async LLM-as-judge runs via FastAPI `BackgroundTasks` after response flush; eval failures cannot fail user requests.

See [`docs/decisions/005-observability-strategy.md`](./docs/decisions/005-observability-strategy.md).
