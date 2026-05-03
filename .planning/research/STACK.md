# Stack Research

**Domain:** Observable RAG chatbot with custom AI-native observability dashboard
**Researched:** 2026-05-04
**Confidence:** HIGH (locked choices), MEDIUM-HIGH (open decisions)

---

## Locked Stack Validation

The PRD locked the following choices. All remain current as of 2026-05-04:

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

**One concern on React/Tailwind:** Tremor v3 (the leading dashboard candidate) is built on Recharts + Tailwind + Radix UI — it targets Tailwind v3. Tailwind v4 is a breaking change; do not upgrade mid-project.

---

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

---

#### GSD-OPEN-1: Charting Library

**RECOMMENDATION: Tremor v3 (with Recharts as the underlying engine)**

Tremor is a React dashboard component library built on top of Recharts and Tailwind CSS. It provides `AreaChart`, `LineChart`, `BarChart`, `ScatterChart` components with a declarative `data` + `categories` prop API — the exact pattern needed for the tracer-ai dashboard's time-series quality metrics and distribution charts.

**Why Tremor over raw Recharts:**
- Tremor's `AreaChart` + `LineChart` are ~10 lines of code vs. ~40 lines for the equivalent Recharts composition. For a portfolio project with a ~12-hour budget, this matters.
- Built on Recharts internally, so if you need to drop down to the raw Recharts API for a custom chart (e.g., a score distribution histogram), you can — same dependency, no conflict.
- Tailwind-native color system via `colors={["blue", "emerald", "rose"]}` means chart colors automatically harmonize with the shadcn/ui component palette.
- Tremor Blocks (separate package) provides pre-built dashboard layouts — KPI card grids, chart panels — directly usable for the quality metrics overview.

**Why NOT Visx:**
Visx is Airbnb's low-level D3-React bridge (v3.12.0). It gives maximal flexibility but requires composing every axis, scale, and shape manually. For a non-charting-specialist building a portfolio project in 12 hours, Visx is a complexity trap. Use Visx when you need custom visualizations that no higher-level library can produce (e.g., a custom force-directed graph). None of the tracer-ai charts qualify.

**Why NOT raw Recharts alone:**
Raw Recharts (v3.3.0) is a strong choice, but Tremor wraps it with better defaults for dashboard-style use. Since Tremor uses Recharts as its engine, there is no lock-in risk — Tremor is a thin ergonomic layer, not a framework.

**GSD-OPEN-1 Decision:** Tremor v3 (primary) + raw Recharts (escape hatch for custom charts). Both packages are peers; Tremor depends on Recharts, so only one `recharts` dep in `node_modules`.

| Library | Version | Bundle Size (approx) | Complexity | Tailwind fit |
|---------|---------|---------------------|-----------|-------------|
| Tremor | 3.x | ~180KB (includes recharts) | Low | Native |
| Recharts | 3.3.0 | ~140KB | Medium | DIY |
| Visx | 3.12.0 | ~200KB+ (per sub-package) | High | DIY |

**Confidence:** HIGH (verified in Context7 — Tremor docs confirm Recharts backing; BarChart/AreaChart/LineChart all confirmed present)

---

#### GSD-OPEN-2: Vector Store

**RECOMMENDATION: pgvector (postgres + pgvector extension)**

**Primary rationale — single-database deployment:**
The trace storage backend (GSD-OPEN-4) recommends Postgres+JSONB. If pgvector is chosen alongside, the entire persistent state of tracer-ai lives in one Docker container: trace spans, feedback records, regression cases, chunk embeddings. This radically simplifies the Docker Compose file (one DB service vs. two), the backup story, and the connection pool management in FastAPI.

**Technical fit:**
- `pgvector-python` integrates directly with SQLAlchemy 2.0 ORM via `VECTOR(dimensions)` column type and `.cosine_distance()`, `.l2_distance()` query methods (verified in Context7).
- Supports HNSW indexes (via `CREATE INDEX ... USING hnsw`) for fast approximate nearest neighbor search — no brute-force scan needed even for 50K+ chunks.
- Metadata filtering (e.g., filter by `doc_id` or `chunk_type`) is native SQL `WHERE` clauses — no special API needed.
- `pgvector` extension is available in the official `ankane/pgvector` Docker image.

**When to use Qdrant instead:**
If the corpus grows to millions of chunks, or if you need advanced vector operations (multi-vector, sparse+dense hybrid search), Qdrant (Python client `qdrant-client 1.x`, async via `AsyncQdrantClient`) is the best specialized option. It has excellent Docker support (`qdrant/qdrant` image), async-first Python client, and rich filtering. However, it adds a second stateful service to the Compose stack with a separate HTTP port (6333), persistence volume, and connection management.

**Why NOT Chroma:**
Chroma's embedded mode has an unstable API surface — breaking changes between minor versions have burned users. Its server mode (for Docker) is better but adds the same ops complexity as Qdrant without Qdrant's production pedigree. Chroma is appropriate for ephemeral dev experimentation; not for a portfolio project where state persistence across `docker compose down/up` matters.

**Why NOT Weaviate:**
Correctly identified in the PRD as overkill. Heavy JVM-based service, complex schema definition, GraphQL API. Not appropriate for this scale.

| Store | Deployment | Vector search | Metadata filter | Ops surface | Recommendation |
|-------|-----------|---------------|----------------|-------------|----------------|
| pgvector | Postgres (same instance) | HNSW, IVFFlat | Native SQL | Zero extra | PRIMARY |
| Qdrant | Separate Docker service | HNSW, many options | Rich filter API | Medium | SECONDARY (scale trigger) |
| Chroma | Embedded or separate | HNSW | Basic | Low (embedded) | AVOID |
| Weaviate | Separate Docker service | Multiple | GraphQL | High | AVOID |

**GSD-OPEN-2 Decision:** pgvector on Postgres. Consolidates vector and trace storage into one Postgres instance.

**Confidence:** HIGH (pgvector-python async+SQLAlchemy verified via Context7; pgvector Docker image confirmed)

---

#### GSD-OPEN-3: Embedding Provider

**RECOMMENDATION: Voyage AI — `voyage-code-3` model**

**Primary rationale — narrative coherence + technical quality:**
The PRD's corpus is Anthropic Claude API + Agent SDK documentation — technical, code-heavy markdown. Voyage AI is Anthropic's officially recommended embedding partner. The `voyage-code-3` model is explicitly "optimized for retrieving code-related information" (verified in Context7 from Voyage AI docs). This is the most defensible choice: "I used the embedding model that Anthropic recommends, optimized for code documentation."

**Current Voyage AI model landscape (verified via Context7, May 2026):**
- `voyage-4-large` — latest general-purpose flagship (1024-dim default, 2048 max)
- `voyage-4` / `voyage-4-lite` — general-purpose tradeoffs
- `voyage-3.5` / `voyage-3.5-lite` — previous generation general
- `voyage-code-3` — code + technical docs specialist; 1024-dim
- `voyage-context-3` — contextualized chunk embeddings (chunk + full-doc context)

**For tracer-ai, use `voyage-code-3`** because:
1. Claude API docs are code-heavy (function signatures, JSON schemas, API parameters).
2. `voyage-code-3` is specifically benchmarked for code retrieval.
3. 1024 dimensions fits well in pgvector without excessive storage overhead.
4. Available in Voyage Batch API for bulk ingestion.

**Offline/fallback — `sentence-transformers` + `nomic-embed-text-v1.5`:**
For development without an API key, `sentence-transformers` (HuggingFace, v3.x, verified in Context7) with `nomic-ai/nomic-embed-text-v1.5` provides a solid local alternative (768-dim, Apache 2.0 license, no API cost). Wire it behind the `Embedder` Protocol so switching requires only changing the adapter.

**Why NOT OpenAI `text-embedding-3-large`:**
Requires an OpenAI API key (separate from the Anthropic key already required). Adds a second API provider for no narrative benefit. `voyage-code-3` outperforms `text-embedding-3-small` on code retrieval.

**Why NOT Cohere:**
Third API provider. Cohere's `embed-english-v3.0` is strong but not specialized for code. Adds complexity with no advantage over Voyage for this corpus type.

| Provider | Model | Dims | API Key Needed | Code-doc quality | Narrative fit |
|----------|-------|------|---------------|-----------------|---------------|
| Voyage AI | voyage-code-3 | 1024 | VOYAGE_API_KEY | Excellent | Anthropic-recommended |
| OpenAI | text-embedding-3-large | 3072 | OPENAI_API_KEY | Good | N/A |
| HuggingFace ST | nomic-embed-text-v1.5 | 768 | None (local) | Good | Offline dev fallback |
| Cohere | embed-english-v3.0 | 1024 | COHERE_API_KEY | Good | N/A |

**GSD-OPEN-3 Decision:** Voyage AI `voyage-code-3` as primary. `sentence-transformers` + `nomic-embed-text-v1.5` as offline fallback. Both wired through `Embedder` Protocol.

**Confidence:** MEDIUM-HIGH (Voyage AI model names and code-3 positioning verified via Context7 from official Voyage docs; pricing not confirmed — check voyageai.com)

---

#### GSD-OPEN-4: Trace Storage Backend

**RECOMMENDATION: Postgres + JSONB (same instance as pgvector)**

**Primary rationale — consolidation + query power:**
If pgvector is chosen (GSD-OPEN-2), Postgres is already in the stack. Using the same instance for trace storage means one Docker container, one connection pool, one migration system, one backup target. This is the dominant advantage.

**JSONB for span attributes** is the right choice because:
- Span attributes are heterogeneous — different span types have different attribute keys (`gen_ai.usage.input_tokens` on LLM spans, `rag.retrieval.score.mean` on retrieval spans). A rigid relational schema would require nullable columns or a complex inheritance structure.
- Postgres JSONB supports GIN indexes that allow fast querying by specific JSON keys (e.g., `WHERE attrs->>'gen_ai.operation.name' = 'retrieval'`).
- Time-series aggregations (`SELECT AVG((attrs->>'faithfulness')::float), DATE_TRUNC('hour', started_at) ...`) work natively in Postgres SQL.
- The "drill into trace" pattern (fetch one trace, all its spans) is a single `WHERE trace_id = $1` query.

**Schema sketch (verified queryable patterns):**
```sql
-- traces table
CREATE TABLE traces (
    id UUID PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    query_text TEXT,
    root_span_id UUID
);
CREATE INDEX ON traces (started_at DESC);

-- spans table
CREATE TABLE spans (
    id UUID PRIMARY KEY,
    trace_id UUID REFERENCES traces(id),
    parent_span_id UUID,
    name TEXT NOT NULL,           -- e.g. 'rag.retrieve', 'rag.llm_call'
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    attrs JSONB DEFAULT '{}'
);
CREATE INDEX ON spans (trace_id);
CREATE INDEX ON spans USING GIN (attrs);

-- feedback table
CREATE TABLE feedback (
    id UUID PRIMARY KEY,
    trace_id UUID REFERENCES traces(id),
    rating SMALLINT,              -- 1=up, -1=down
    comment TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Why NOT SQLite:**
SQLite is zero-ops but has two critical gaps for this project:
1. Concurrent writes: FastAPI serves requests and the LLM-as-judge pipeline writes eval scores asynchronously. SQLite's write-lock model causes contention.
2. JSONB: SQLite has JSON functions but no GIN indexes. Queries over span attributes are full-table scans.

**Why NOT ClickHouse:**
ClickHouse is genuinely excellent for time-series span data at scale (100M+ rows). But it requires a separate Docker container, its own query dialect, and a Python client (`clickhouse-driver`). For tracer-ai v1 with a single local user, Postgres handles the query load trivially. ClickHouse is the right upgrade path if this becomes a product at scale.

**Why NOT DuckDB:**
DuckDB is an interesting analytical option (embedded, OLAP-optimized, zero-ops) and would work for the read-side dashboard queries. However, DuckDB's write concurrency story is similar to SQLite — it's designed for analytical reads, not transactional writes from an async API server. The async span emission path would hit locking issues.

| Backend | Time-series queries | Async writes | JSONB attrs | Ops surface | Recommendation |
|---------|--------------------|-----------__|------------|-------------|----------------|
| Postgres+JSONB | Excellent | Native async (asyncpg) | Native | Zero (with pgvector already) | PRIMARY |
| SQLite | Limited | Concurrent write issues | JSON (no GIN) | Zero | AVOID |
| ClickHouse | Best | Good | Native | Extra service | FUTURE (scale) |
| DuckDB | Excellent reads | Write concurrency issues | Native | Zero | AVOID |

**GSD-OPEN-4 Decision:** Postgres + JSONB. Single Postgres instance hosts both vector store (pgvector) and trace storage.

**Confidence:** HIGH (Postgres JSONB query patterns well-established; SQLAlchemy 2.0 async confirmed; pgvector-python async confirmed via Context7)

---

## OTel GenAI Semantic Conventions — Status

**Status: DEVELOPMENT (not stable as of May 2026)**

From official OTel docs (verified via Context7):
- All `gen_ai.*` operation name well-known values are marked **Development** stability, including: `chat`, `embeddings`, `retrieval`, `execute_tool`, `invoke_agent`.
- Defined attributes: `gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.input.messages`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`.
- The `retrieval` span has `gen_ai.retrieval.documents` and `gen_ai.retrieval.query.text` as Opt-In attributes.
- `gen_ai.provider.name` for Anthropic = `"anthropic"` (defined in the spec).

**Implications for tracer-ai:**
Use the OTel GenAI attribute names in the trace schema for all attributes that have defined values (`gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`). For RAG-specific attributes not yet in the spec (`rag.retrieved_chunks`, `rag.retrieval.score.mean`, `rag.prompt_template_id`), use the `rag.*` namespace as defined in the PRD's trace schema.

**Do NOT import `opentelemetry-sdk` as a runtime dependency** unless you plan to export to an OTel collector. The PRD chooses custom trace storage with OTel-compatible attribute naming — this means following the naming conventions without necessarily using the OTel SDK's tracer/span classes. The OTel Python SDK (`opentelemetry-sdk 1.x`) adds meaningful overhead and complexity for what is essentially a schema-alignment exercise. The tracer core should be custom Python dataclasses with OTel-named attributes, not OTel SDK spans.

**If future OTel export is needed:** the `tracer/exporters/` module can add an OTLP exporter that maps the custom span dataclasses to OTel SDK spans — this is a one-file change behind the Protocol.

---

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

---

## Installation

```bash
# Backend (pyproject.toml / pip)
pip install fastapi uvicorn[standard] pydantic pydantic-settings anthropic voyageai
pip install sqlalchemy[asyncio] asyncpg pgvector alembic
pip install sentence-transformers  # offline fallback only
pip install structlog httpx python-multipart

# Dev
pip install ruff mypy pytest pytest-asyncio pre-commit

# Frontend
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install @tremor/react recharts
npm install @tanstack/react-query react-router-dom ky date-fns clsx tailwind-merge
npx shadcn@latest init
```

---

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

---

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

---

## Stack Patterns by Variant

**If operating offline (no API keys):**
- Use `sentence-transformers` with `nomic-ai/nomic-embed-text-v1.5` via the `Embedder` Protocol
- Use a `MockLLM` adapter that returns canned responses for the judge; real Anthropic calls only when online
- pgvector and Postgres work identically — fully offline

**If Qdrant is chosen over pgvector (scale trigger):**
- Replace `pgvector` Python dep with `qdrant-client[async]`
- Implement `QdrantRetriever` behind the same `Retriever` Protocol
- Postgres remains for trace storage only; Qdrant gets its own Docker service
- HNSW config: `QdrantClient.create_collection(..., vectors_config=VectorParams(size=1024, distance=Distance.COSINE))`

**If a future OTel exporter is needed:**
- Install `opentelemetry-sdk` + `opentelemetry-exporter-otlp-proto-grpc` only in the `tracer/exporters/` module
- Map custom span dataclasses to OTel `ReadableSpan` objects before export
- No other code changes required — the Protocol boundary insulates the pipeline

---

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| Tremor 3.x | Recharts 2.x or 3.x | Tremor ships Recharts as peer dep; verify peer dep range at install |
| pgvector-python 0.3+ | SQLAlchemy 2.0+ | Requires SQLAlchemy 2.0+ for `mapped_column` and async session |
| FastAPI 0.128.x | Pydantic v2 | FastAPI 0.100+ requires Pydantic v2; v1 unsupported |
| asyncpg 0.29+ | SQLAlchemy 2.0 async | Use `create_async_engine("postgresql+asyncpg://...")` |
| Tailwind 3.x | shadcn/ui (latest) | Tailwind v4 breaks shadcn/ui PostCSS config; pin v3 |
| React 18.x | shadcn/ui 3.5.x | React 19 has incomplete RSC compat in shadcn patterns for SPA use |

---

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

---

*Stack research for: tracer-ai — observable RAG chatbot with custom AI-native observability*
*Researched: 2026-05-04*
