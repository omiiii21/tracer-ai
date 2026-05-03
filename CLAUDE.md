<!-- GSD:project-start source:PROJECT.md -->
## Project

**tracer-ai**

A portfolio-grade RAG chatbot built around the thesis that **AI-native observability is the product, and the chatbot is the test bed**. Every stage of the RAG pipeline (query → retrieval → prompt assembly → LLM call → output) is instrumented as a structured trace; a dashboard surfaces semantic quality drift; flagged "bad answers" become regression test cases that close the loop. The chatbot answers questions about the Anthropic Claude API + Claude Agent SDK documentation — making it self-referential, demoable, and giving clear ground truth for evaluation.

**Core Value:** When a RAG bot misanswers, the operator can open the trace and see exactly *which stage failed* — retriever returned wrong chunks, LLM ignored the right chunks, corpus was stale, prompt template degraded. Per-step traces with semantic quality metrics turn debugging from guesswork into diagnosis.

### Constraints

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
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

## Locked Stack Validation
| Choice | PRD Version | Verified Current Version | Status |
|--------|-------------|--------------------------|--------|
| Python 3.12+ | 3.12+ | 3.13 released; 3.12 LTS stable | VALID — use 3.12 for wider Docker image availability |
| FastAPI | latest | 0.128.x (Context7 shows 0.128.0 as latest) | VALID |
| Pydantic v2 | v2 | v2.x active; v2 is the default now | VALID |
| Anthropic Claude SDK (Python) | latest | Confirms `claude-sonnet-4-5-20250929`; Haiku available | VALID |
| Claude Sonnet 4.5 (bot) / Haiku (judge) | claude-sonnet-4-5, claude-haiku | Both confirmed via SDK `models.list()` | VALID |
| Vite + React 18 + TypeScript | latest | React 18 stable; React 19 exists but React 18 preferred for shadcn/ui stability | VALID — pin React 18 |
| Tailwind CSS | v3 | v4 released; shadcn/ui still primarily targets v3 | VALID — use Tailwind v3; v4 migration is disruptive |
| shadcn/ui | 0.9.x | shadcn@2.9.0 + shadcn@3.5.0 in Context7 | VALID — use latest shadcn CLI |
| Docker Compose | v2 | Docker Compose v2 (plugin format) | VALID |
| ruff + mypy + pytest + pre-commit | latest | All actively maintained | VALID |
## Recommended Stack — Full Picture
### Core Technologies (Locked)
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Python | 3.12 | Backend runtime | LTS stability; widest Docker image support; async/await native |
| FastAPI | 0.128.x | HTTP API server | Auto OpenAPI; native async; Pydantic v2 integration; industry standard for Python AI APIs |
| Pydantic v2 | 2.x | Data validation, Settings, I/O schemas | v2 is 5-20x faster than v1; `model_validator`, `field_validator` cover all custom logic |
| Pydantic Settings | 2.x | Env-var config loading | Companion to Pydantic v2; replaces python-dotenv for typed config |
| Anthropic Python SDK | latest (0.49+) | LLM calls (Claude Sonnet 4.5, Haiku) | Official SDK; async client; `messages.create()` with structured responses |
| Vite | 5.x | Frontend build | Lightning-fast HMR; zero-config TypeScript; standard for React SPAs |
| React | 18.x | Frontend UI | shadcn/ui and Tremor both target React 18; React 19 adoption is still incomplete in ecosystem |
| TypeScript | 5.x | Frontend type safety | Required by shadcn/ui; catches API contract mismatches at build time |
| Tailwind CSS | 3.x | Styling | Pin to v3 — Tremor and shadcn/ui both target Tailwind v3; v4 migration breaks both |
| shadcn/ui | latest CLI | UI component library | Copy-paste components with full ownership; Radix UI primitives; zero runtime styling overhead |
| Docker Compose | v2 (plugin) | Local orchestration | `docker compose up` syntax; no separate binary install needed |
### Open Decision Recommendations
#### GSD-OPEN-1: Charting Library
- Tremor's `AreaChart` + `LineChart` are ~10 lines of code vs. ~40 lines for the equivalent Recharts composition. For a portfolio project with a ~12-hour budget, this matters.
- Built on Recharts internally, so if you need to drop down to the raw Recharts API for a custom chart (e.g., a score distribution histogram), you can — same dependency, no conflict.
- Tailwind-native color system via `colors={["blue", "emerald", "rose"]}` means chart colors automatically harmonize with the shadcn/ui component palette.
- Tremor Blocks (separate package) provides pre-built dashboard layouts — KPI card grids, chart panels — directly usable for the quality metrics overview.
| Library | Version | Bundle Size (approx) | Complexity | Tailwind fit |
|---------|---------|---------------------|-----------|-------------|
| Tremor | 3.x | ~180KB (includes recharts) | Low | Native |
| Recharts | 3.3.0 | ~140KB | Medium | DIY |
| Visx | 3.12.0 | ~200KB+ (per sub-package) | High | DIY |
#### GSD-OPEN-2: Vector Store
- `pgvector-python` integrates directly with SQLAlchemy 2.0 ORM via `VECTOR(dimensions)` column type and `.cosine_distance()`, `.l2_distance()` query methods (verified in Context7).
- Supports HNSW indexes (via `CREATE INDEX ... USING hnsw`) for fast approximate nearest neighbor search — no brute-force scan needed even for 50K+ chunks.
- Metadata filtering (e.g., filter by `doc_id` or `chunk_type`) is native SQL `WHERE` clauses — no special API needed.
- `pgvector` extension is available in the official `ankane/pgvector` Docker image.
| Store | Deployment | Vector search | Metadata filter | Ops surface | Recommendation |
|-------|-----------|---------------|----------------|-------------|----------------|
| pgvector | Postgres (same instance) | HNSW, IVFFlat | Native SQL | Zero extra | PRIMARY |
| Qdrant | Separate Docker service | HNSW, many options | Rich filter API | Medium | SECONDARY (scale trigger) |
| Chroma | Embedded or separate | HNSW | Basic | Low (embedded) | AVOID |
| Weaviate | Separate Docker service | Multiple | GraphQL | High | AVOID |
#### GSD-OPEN-3: Embedding Provider
- `voyage-4-large` — latest general-purpose flagship (1024-dim default, 2048 max)
- `voyage-4` / `voyage-4-lite` — general-purpose tradeoffs
- `voyage-3.5` / `voyage-3.5-lite` — previous generation general
- `voyage-code-3` — code + technical docs specialist; 1024-dim
- `voyage-context-3` — contextualized chunk embeddings (chunk + full-doc context)
| Provider | Model | Dims | API Key Needed | Code-doc quality | Narrative fit |
|----------|-------|------|---------------|-----------------|---------------|
| Voyage AI | voyage-code-3 | 1024 | VOYAGE_API_KEY | Excellent | Anthropic-recommended |
| OpenAI | text-embedding-3-large | 3072 | OPENAI_API_KEY | Good | N/A |
| HuggingFace ST | nomic-embed-text-v1.5 | 768 | None (local) | Good | Offline dev fallback |
| Cohere | embed-english-v3.0 | 1024 | COHERE_API_KEY | Good | N/A |
#### GSD-OPEN-4: Trace Storage Backend
- Span attributes are heterogeneous — different span types have different attribute keys (`gen_ai.usage.input_tokens` on LLM spans, `rag.retrieval.score.mean` on retrieval spans). A rigid relational schema would require nullable columns or a complex inheritance structure.
- Postgres JSONB supports GIN indexes that allow fast querying by specific JSON keys (e.g., `WHERE attrs->>'gen_ai.operation.name' = 'retrieval'`).
- Time-series aggregations (`SELECT AVG((attrs->>'faithfulness')::float), DATE_TRUNC('hour', started_at) ...`) work natively in Postgres SQL.
- The "drill into trace" pattern (fetch one trace, all its spans) is a single `WHERE trace_id = $1` query.
| Backend | Time-series queries | Async writes | JSONB attrs | Ops surface | Recommendation |
|---------|--------------------|-----------__|------------|-------------|----------------|
| Postgres+JSONB | Excellent | Native async (asyncpg) | Native | Zero (with pgvector already) | PRIMARY |
| SQLite | Limited | Concurrent write issues | JSON (no GIN) | Zero | AVOID |
| ClickHouse | Best | Good | Native | Extra service | FUTURE (scale) |
| DuckDB | Excellent reads | Write concurrency issues | Native | Zero | AVOID |
## OTel GenAI Semantic Conventions — Status
- All `gen_ai.*` operation name well-known values are marked **Development** stability, including: `chat`, `embeddings`, `retrieval`, `execute_tool`, `invoke_agent`.
- Defined attributes: `gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.input.messages`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`.
- The `retrieval` span has `gen_ai.retrieval.documents` and `gen_ai.retrieval.query.text` as Opt-In attributes.
- `gen_ai.provider.name` for Anthropic = `"anthropic"` (defined in the spec).
## Supporting Libraries
### Backend Python
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `anthropic` | 0.49+ | Anthropic SDK | All LLM calls; async via `AsyncAnthropic` |
| `voyageai` | 0.3+ | Voyage AI embedding client | Production embeddings (voyage-code-3) |
| `sentence-transformers` | 3.x | Local embeddings | Offline dev; fallback Embedder |
| `pgvector` | 0.3+ | pgvector Python client | Vector column type + distance queries |
| `asyncpg` | 0.29+ | Async Postgres driver | Required for SQLAlchemy async; fast |
| `sqlalchemy` | 2.0+ | ORM + migrations | Trace store schema; async session support |
| `alembic` | 1.x | DB migrations | Schema versioning; required for production-grade DB |
| `uvicorn` | 0.30+ | ASGI server | Runs FastAPI; `--reload` for dev |
| `httpx` | 0.27+ | HTTP client | FastAPI `TestClient`; also used in tests |
| `python-multipart` | latest | File upload support | Corpus admin upload endpoint |
| `structlog` | 24.x | Structured logging | JSON logs from tracer; `structlog.get_logger()` |
| `tiktoken` | 0.7+ | Token counting | Estimate costs before LLM call; Anthropic uses its own tokenizer but tiktoken is close enough for estimation |
### Frontend JavaScript/TypeScript
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `@tremor/react` | 3.x | Dashboard charts and UI | Quality drift charts, KPI cards, trace list |
| `recharts` | 3.3.0 | Chart primitives (peer dep) | Custom charts not in Tremor (e.g., histogram) |
| `@tanstack/react-query` | 5.x | Server state management | API data fetching, caching, polling for eval scores |
| `react-router-dom` | 6.x | Client-side routing | `/chat`, `/dashboard`, `/admin` routes |
| `axios` or `ky` | latest | HTTP client | API calls to FastAPI; prefer `ky` (smaller, fetch-based) |
| `date-fns` | 3.x | Date formatting | Trace timestamps, time windows |
| `clsx` | 2.x | Conditional class names | Used by shadcn/ui pattern |
| `tailwind-merge` | 2.x | Tailwind class deduplication | Required by shadcn/ui `cn()` utility |
### Development Tools
| Tool | Purpose | Notes |
|------|---------|-------|
| `ruff` | Python linter + formatter | Replaces flake8 + black; fast; configured in `pyproject.toml` |
| `mypy` (strict) | Static type checking | `--strict` mode; catches untyped Protocol implementations |
| `pytest` | Python testing | With `pytest-asyncio` for async test support |
| `pytest-asyncio` | Async test runner | Required for testing async FastAPI + async trace writer |
| `httpx` | FastAPI test client | `AsyncClient` for integration tests against FastAPI |
| `pre-commit` | Git hooks | Runs ruff + mypy + tsc before commit |
| `docker compose` v2 | Local orchestration | Single `docker compose up --build` for full stack |
| `alembic` | DB migrations | Run in entrypoint; `alembic upgrade head` before FastAPI starts |
## Installation
# Backend (pyproject.toml / pip)
# Dev
# Frontend
## Alternatives Considered
| Recommended | Alternative | When Alternative is Better |
|-------------|-------------|---------------------------|
| Tremor v3 | Raw Recharts | When you need full chart control, custom SVG, or animations not in Tremor |
| Tremor v3 | Visx | When building a truly custom visualization (force graph, custom waterfall) at the cost of >2x development time |
| pgvector | Qdrant | When corpus exceeds ~500K chunks or when hybrid sparse+dense search is needed |
| pgvector | Qdrant | When the vector store Protocol needs to remain completely independent from the DB (microservices future) |
| Postgres+JSONB | ClickHouse | When traces grow to 100M+ rows and the product needs sub-second aggregations at that scale |
| Postgres+JSONB | DuckDB | When the system is read-only analytical (no real-time writes from the API) |
| voyage-code-3 | text-embedding-3-large | When corpus shifts away from code/technical docs toward general prose |
| voyage-code-3 | nomic-embed-text-v1.5 | When no API key budget exists and offline operation is the primary constraint |
## What NOT to Use
| Avoid | Why | Use Instead |
|-------|-----|-------------|
| LangChain / LlamaIndex | Abstracts pipeline stages tracer-ai deliberately wants to instrument; direct SDK calls are the thesis | Direct `anthropic` SDK + custom pipeline |
| Langfuse / Phoenix (as primary) | Black-box trace storage; would defeat the learning objective; use as future export target only | Custom tracer with OTel-named attributes |
| `opentelemetry-sdk` as tracer | Heavy dependency; adds OTel SDK span lifecycle to what should be simple dataclass emission; the goal is OTel-compatible naming, not OTel SDK runtime | Custom span dataclass with `gen_ai.*` attribute names |
| SQLite for trace storage | Write-lock contention under async concurrent writes; no JSONB GIN indexes | Postgres + JSONB |
| Chroma vector store | Unstable minor-version API surface; embedded mode not suitable for persisted Docker volume | pgvector or Qdrant |
| Weaviate | JVM-based, GraphQL API, overkill for single-user local MVP | pgvector |
| React 19 | Incomplete shadcn/ui + Tremor compatibility in 2026; bleeding edge | React 18 (pin `"react": "^18.3.1"`) |
| Tailwind v4 | Breaking changes incompatible with Tremor v3 and current shadcn/ui | Tailwind v3 (pin `"tailwindcss": "^3.4.x"`) |
| `axios` | Heavy; fetch-based alternatives are simpler for a React SPA against a local API | `ky` (fetch wrapper, 2KB) or native `fetch` |
## Stack Patterns by Variant
- Use `sentence-transformers` with `nomic-ai/nomic-embed-text-v1.5` via the `Embedder` Protocol
- Use a `MockLLM` adapter that returns canned responses for the judge; real Anthropic calls only when online
- pgvector and Postgres work identically — fully offline
- Replace `pgvector` Python dep with `qdrant-client[async]`
- Implement `QdrantRetriever` behind the same `Retriever` Protocol
- Postgres remains for trace storage only; Qdrant gets its own Docker service
- HNSW config: `QdrantClient.create_collection(..., vectors_config=VectorParams(size=1024, distance=Distance.COSINE))`
- Install `opentelemetry-sdk` + `opentelemetry-exporter-otlp-proto-grpc` only in the `tracer/exporters/` module
- Map custom span dataclasses to OTel `ReadableSpan` objects before export
- No other code changes required — the Protocol boundary insulates the pipeline
## Version Compatibility
| Package | Compatible With | Notes |
|---------|-----------------|-------|
| Tremor 3.x | Recharts 2.x or 3.x | Tremor ships Recharts as peer dep; verify peer dep range at install |
| pgvector-python 0.3+ | SQLAlchemy 2.0+ | Requires SQLAlchemy 2.0+ for `mapped_column` and async session |
| FastAPI 0.128.x | Pydantic v2 | FastAPI 0.100+ requires Pydantic v2; v1 unsupported |
| asyncpg 0.29+ | SQLAlchemy 2.0 async | Use `create_async_engine("postgresql+asyncpg://...")` |
| Tailwind 3.x | shadcn/ui (latest) | Tailwind v4 breaks shadcn/ui PostCSS config; pin v3 |
| React 18.x | shadcn/ui 3.5.x | React 19 has incomplete RSC compat in shadcn patterns for SPA use |
## Sources
- Context7 `/recharts/recharts` — confirmed Recharts v3.3.0, `LineChart`, `AreaChart`, `ComposedChart` components
- Context7 `/tremorlabs/tremor` — confirmed Tremor is Recharts-backed; `BarChart`, `AreaChart`, `LineChart` with Tailwind color API
- Context7 `/tremorlabs/tremor-blocks` — confirmed time-series data patterns for incident/metrics dashboards
- Context7 `/airbnb/visx` — confirmed v3.12.0; low-level D3-React primitives
- Context7 `/qdrant/qdrant-client` — confirmed `AsyncQdrantClient`, filtering, collection creation
- Context7 `/pgvector/pgvector-python` — confirmed SQLAlchemy 2.0 `VECTOR` column, `.cosine_distance()`, HNSW index
- Context7 `/websites/voyageai` — confirmed `voyage-code-3`, `voyage-4-large`, `voyage-4`; Voyage AI models list
- Context7 `/websites/opentelemetry_io` — confirmed GenAI semantic conventions at **Development** stability; `gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.retrieval.documents` attributes
- Context7 `/anthropics/anthropic-sdk-python` — confirmed `claude-sonnet-4-5-20250929` model ID; async `AsyncAnthropic` client
- Context7 `/huggingface/sentence-transformers` — confirmed v3.x; `nomic-embed-text` support
- Context7 `/fastapi/fastapi` — confirmed FastAPI 0.128.x as latest
- Context7 `/shadcn-ui/ui` — confirmed `shadcn@3.5.0` as latest CLI
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
