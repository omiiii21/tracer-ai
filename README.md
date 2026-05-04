# tracer-ai

A portfolio-grade RAG chatbot built around the thesis that **AI-native observability is the product, and the chatbot is the test bed**. Every stage of the RAG pipeline (query → retrieval → prompt assembly → LLM call → output) is instrumented as a structured trace; a dashboard surfaces semantic quality drift; flagged "bad answers" become regression test cases that close the loop. The chatbot answers questions about the Anthropic Claude API + Claude Agent SDK documentation — making it self-referential, demoable, and giving clear ground truth for evaluation.

**Core value:** When a RAG bot misanswers, the operator can open the trace and see exactly *which stage failed* — retriever returned wrong chunks, LLM ignored the right chunks, corpus was stale, prompt template degraded.

## Quick Start

Requires Docker Desktop (Compose v2) and `git`.

```bash
git clone <this-repo> tracer-ai && cd tracer-ai
cp .env.example .env
# Edit .env: set ANTHROPIC_API_KEY=sk-ant-... and VOYAGE_API_KEY=...
docker compose -f infra/docker-compose.yml up --build
```

When all services report healthy:

| Service | URL | Probe |
|---------|-----|-------|
| Backend API | http://localhost:8000/healthz | `curl --silent http://localhost:8000/healthz \| jq` |
| Frontend SPA | http://localhost:5173 | open in browser — shows "Hello tracer-ai" Card |
| Postgres | (internal only — see `infra/docker-compose.yml` to opt-in to host port 5432) | `docker compose exec db psql -U tracer -d tracer_ai` |

A successful first boot applies all Alembic migrations, installs the `pgvector` extension, and exposes a working `/healthz` endpoint. Stop the stack with `docker compose down`; pass `-v` to also wipe the Postgres volume.

## Project Structure

```
tracer-ai/
├── tracer_ai/              # Python package (backend) — mirrors docs/architecture.md
│   ├── tracer/             # OTel-aligned span constants, context, store, exporters
│   ├── rag/                # Retriever / Embedder / LLM Protocols (Phase 3+)
│   ├── eval/               # LLM-as-judge, feedback, regression (Phase 5+)
│   ├── corpus/             # Document ingestion + chunking (Phase 3+)
│   ├── api/                # FastAPI app — main.py, health.py
│   ├── cli/                # Operator CLI (Phase 6+)
│   ├── errors.py           # Cross-cutting exception hierarchy
│   └── config.py           # Pydantic Settings — fail-fast at import (D-2.21)
├── frontend/               # Vite + React 18 + TS + Tailwind v3 + shadcn/ui
│   └── src/                # App + components/ui/{card,button} + lib/utils
├── alembic/                # DB migrations — 0001_initial = full Phase 1 DDL
├── infra/                  # Docker Compose, Dockerfile.backend, Dockerfile.frontend, db/init.sql
│   └── scripts/            # import_cycle_guard.py (DAG enforcement)
├── tests/                  # pytest suite — config fail-fast, /healthz, anti-patterns, smoke imports
├── docs/                   # Phase 1 design contracts (locked) — see Documentation below
└── .planning/              # GSD workflow artifacts — phase plans, summaries, state
```

## Development

After `git clone`, install pre-commit hooks once:

```bash
uv sync --all-extras            # backend deps (uv 0.5+ recommended)
uv run pre-commit install        # install hooks at .git/hooks/pre-commit
cd frontend && npm install      # frontend deps (only needed for local tsc)
```

The pre-commit chain runs on every commit:

| Hook | What |
|------|------|
| `ruff` (lint + format) | Python style |
| `mypy --strict tracer_ai/` | Static type checking |
| `tsc --noEmit -p frontend/tsconfig.json` | Frontend type checking |
| `pytest --testmon` | Changed-only test run |
| `gitleaks` | Secret scanning (Anthropic + Voyage key patterns) |
| `import-cycle-guard` | Enforces the locked module DAG (`docs/module-deps.md`) |
| `anti-pattern-grep` | No `:latest`, no `class Config:` (Pydantic v1), no `print()` in `tracer_ai/`, no `gen_ai.system`, no `opentelemetry-sdk` runtime dep |

## Status

Phase 1 (Research & Design Artifacts) and Phase 2 (Skeleton & Infrastructure) complete. Phases 3–7 are feature implementation.

| Phase | Goal | Status |
|-------|------|--------|
| 1 | Research & Design Artifacts | ✓ Complete |
| 2 | Skeleton & Infrastructure | ✓ Complete |
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
