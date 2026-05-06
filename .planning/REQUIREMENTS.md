# Requirements: tracer-ai

**Defined:** 2026-05-04
**Core Value:** When a RAG bot misanswers, the operator can open the trace and see exactly which stage failed — retriever returned wrong chunks, LLM ignored the right chunks, corpus was stale, prompt template degraded. Per-step traces with semantic quality metrics turn debugging from guesswork into diagnosis.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Design (Phase 1 deliverables)

- [x] **DSGN-01**: All `[GSD-OPEN-N]` items from PRD §10 resolved as ADRs in `/docs/decisions/NNN-<slug>.md` (one ADR per item, with context/options/decision/consequences)
- [x] **DSGN-02**: System architecture diagram (Mermaid `graph` or `flowchart`) at `/docs/architecture.md` showing frontend/backend/data stores/external APIs
- [x] **DSGN-03**: Chat request sequence diagram (Mermaid `sequenceDiagram`) showing sync request path + async eval branch
- [x] **DSGN-04**: Trace schema spec at `/docs/trace-schema.md` — formal table of every span name, attribute, type, OTel-conformance status, example payload
- [x] **DSGN-05**: DB schema / ERD at `/docs/data-model.md` (Mermaid `erDiagram`) for `traces`, `spans`, `feedback`, `regression_cases`, plus vector store collection schema
- [x] **DSGN-06**: API contract at `/docs/api.md` with Pydantic shapes for `POST /chat`, `GET /traces`, `GET /traces/{id}`, `POST /feedback`, ingest + admin endpoints
- [x] **DSGN-07**: UI wireframes at `/docs/wireframes/` for chat, trace list, trace detail, bad-answer queue, admin
- [x] **DSGN-08**: Module dependency diagram confirming the architecture-research module layout has no circular deps
- [x] **DSGN-09**: Risk + scope-trim plan documented (which phases get cut first if budget slips >25%)
- [x] **DSGN-10**: Proactive coverage regression query set (10+ queries) authored, covering each major Claude API doc section (auth, models, prompts, tools, batches, files, citations, vision)

### Infrastructure (Phase 2)

- [ ] **INFRA-01**: Repo scaffold per ARCHITECTURE.md module layout (backend `tracer_ai/`, `frontend/`, `infra/`)
- [ ] **INFRA-02**: `docker compose up` boots full stack green: FastAPI hello-world, Vite hello-world, Postgres 16 with pgvector extension
- [ ] **INFRA-03**: All Docker image tags pinned (no `:latest`); `.env.example` checked in; `config.py` validates all required env vars at startup with clear errors
- [ ] **INFRA-04**: Pre-commit hooks active: `ruff`, `mypy --strict`, frontend `tsc`, basic test runner
- [ ] **INFRA-05**: README skeleton with setup steps; `mkdir -p docs/decisions/` exists for ADRs

### Corpus (Phase 3)

- [ ] **CORP-01**: `tracer-ai ingest --source claude-docs` CLI pulls/parses Claude API + Agent SDK docs (markdown + HTML)
- [ ] **CORP-02**: Markdown-header-aware chunker splits docs at `##`/`###` boundaries; configurable chunk size + overlap; never splits inside fenced code blocks
- [ ] **CORP-03**: Each chunk row in vector store stores `embedding_model`, `embedding_model_version`, `indexed_at` metadata
- [ ] **CORP-04**: Startup assertion fails fast if `config.embedding_model` does not match corpus metadata
- [ ] **CORP-05**: Embedder Protocol with Voyage AI `voyage-code-3` adapter (primary) and sentence-transformers adapter (offline fallback)

### RAG Pipeline (Phase 3)

- [ ] **RAG-01**: Retriever Protocol with pgvector adapter; configurable `top_k` (default 5)
- [ ] **RAG-02**: Prompt assembler builds final prompt with citation formatting (chunks delimited so they cannot inject as instructions)
- [ ] **RAG-03**: LLM Protocol with Anthropic SDK adapter using `claude-sonnet-4-5` (date-pinned snapshot); returns answer + token usage + cost estimate
- [ ] **RAG-04**: `pipeline.run(query)` returns `PipelineResult` with answer, retrieved chunks (with scores), assembled prompt, token usage, cost
- [ ] **RAG-05**: `POST /chat` endpoint accepts query, returns answer + cited source chunks + latency + token count + estimated cost + `trace_id`
- [ ] **RAG-06**: End-to-end answer latency < 5s for typical query (single-user local target)

### Chat UI (Phase 3)

- [ ] **CHAT-01**: Single-turn or multi-turn (within session) conversational interface at `/chat`
- [ ] **CHAT-02**: Each message renders answer + cited source chunks (clickable to expand chunk text)
- [ ] **CHAT-03**: Each message displays latency, token count, estimated cost
- [ ] **CHAT-04**: Each message has thumbs-up / thumbs-down controls; thumbs-down opens free-text comment box
- [ ] **CHAT-05**: Each message has a link to its full trace in the Trace Explorer

### Admin UI (Phase 3)

- [ ] **ADMN-01**: `/admin` route shows current corpus: doc list, chunk count, embedding model, last-indexed timestamp
- [ ] **ADMN-02**: Re-index button triggers ingestion via API call; shows progress
- [ ] **ADMN-03**: Chunking config form (size, overlap) — values persist and apply on next re-index
- [ ] **ADMN-04**: URL-list textarea for ingesting from URLs (drag-drop optional)

### Tracer (Phase 4)

- [x] **TRCR-01**: Span dataclass in `tracer/span.py` with OTel-aligned + RAG-specific attributes; all attribute names defined as constants in one file
- [ ] **TRCR-02**: Use `gen_ai.provider.name` (NOT deprecated `gen_ai.system`); follow OTel GenAI naming for `gen_ai.operation.name`, `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`
- [ ] **TRCR-03**: Custom `rag.*` attributes for `rag.retrieved_chunks`, `rag.retrieval.score.{mean,min}`, `rag.prompt_template.id`, `rag.eval.{faithfulness,relevance,judge_model,judge_cost_usd}`
- [ ] **TRCR-04**: Context propagation: `start_span`, `current_span`, `set_span_in_context` helpers wrapping OTel `opentelemetry-api` context
- [x] **TRCR-05**: `TraceStore` Protocol with methods `write_span`, `get_trace`, `list_traces`
- [x] **TRCR-06**: Postgres+JSONB exporter writes via bounded `asyncio.Queue(maxsize=1000)` with `put_nowait`; background consumer batches inserts
- [x] **TRCR-07**: Lifespan shutdown handler drains the span queue (force-flush) before exit
- [ ] **TRCR-08**: Trace write adds ≤100ms p95 to request path (measured in CI)
- [x] **TRCR-09**: Full prompt + response payloads stored in `span_payloads` side table (JSONB) — referenced by `span_id`, not on span row directly
- [x] **TRCR-10**: Every chat request emits trace with spans `rag.request` (root) → `rag.retrieve`, `rag.prompt_assemble`, `rag.llm_call`

### Trace Explorer (Phase 4)

- [x] **EXPL-01**: `GET /traces` endpoint supports filtering by query text, time range, feedback rating, faithfulness score, latency bucket
- [x] **EXPL-02**: `GET /traces/{id}` returns full trace tree (root + all spans + payloads)
- [ ] **EXPL-03**: `/dashboard` trace list view: searchable/filterable table with columns for query, time, latency, cost, faithfulness, feedback
- [ ] **EXPL-04**: Trace detail view shows span waterfall (timing) and payload inspectors (chunks with scores, full assembled prompt, full LLM response)

### Eval / Quality Layer (Phase 5)

- [ ] **EVAL-01**: LLM-as-judge worker scores `faithfulness` and `relevance` for every trace; uses date-pinned `claude-haiku-*` snapshot
- [ ] **EVAL-02**: Judge runs async via FastAPI `BackgroundTasks` after response flush; eval failure must NEVER fail user request
- [ ] **EVAL-03**: Judge prompt wraps untrusted content in XML delimiters (`<retrieved_chunk>`, `<assistant_answer>`); system instruction declares them as inert data
- [ ] **EVAL-04**: `rag.eval` span emitted as child of `rag.request` (context snapshot/re-attach pattern); records `judge_model`, `judge_prompt_version`, `judge_cost_usd`
- [ ] **EVAL-05**: Faithfulness score appears on trace within ~30s of request
- [ ] **EVAL-06**: Calibration step: hand-label ~30 traces (good and bad) and tune the bad-answer threshold against them; document in ADR

### Feedback (Phase 5)

- [ ] **FBCK-01**: `POST /feedback` accepts `{trace_id, rating, comment}`; persists to `feedback` table
- [ ] **FBCK-02**: Thumbs-down lands the trace in the bad-answer queue within seconds
- [ ] **FBCK-03**: Bad-answer queue view: filtered trace list where `feedback=down OR faithfulness < threshold`
- [ ] **FBCK-04**: "Mark resolved" action on bad-answer queue items
- [ ] **FBCK-05**: Optional human-editable diagnosis tag on trace detail with values `{Retrieval, Prompt, Corpus, LLM}` (research-identified differentiator)
- [ ] **FBCK-06**: Bad-answer queue sorted by score (lowest faithfulness first); items auto-close on subsequent re-pass
- [ ] **FBCK-07**: Dashboard widget: queue size + items resolved this week

### Dashboard Metrics (Phase 5)

- [ ] **DASH-01**: Time-series chart: latency p50/p95 over configurable window (default 24h)
- [ ] **DASH-02**: Time-series chart: cost over time
- [ ] **DASH-03**: Time-series chart: faithfulness mean over time
- [ ] **DASH-04**: Time-series chart: manual feedback ratio (down/total) over time
- [ ] **DASH-05**: Overview metrics card: request volume, total tokens, total cost, faithfulness score distribution
- [ ] **DASH-06**: Charts implemented via Tremor v3 components

### Eval CLI (Phase 6)

- [ ] **CLI-01**: `tracer-ai eval` runs the curated regression query set against the live pipeline
- [ ] **CLI-02**: CLI runs BOTH proactive coverage set (from Phase 1) AND reactive promoted set
- [ ] **CLI-03**: Reports per-query pass/fail, faithfulness score, latency, cost
- [ ] **CLI-04**: Aggregate report in markdown or JSON
- [ ] **CLI-05**: `tracer-ai promote <trace_id>` command adds a trace to the regression set (callable from bad-answer queue UI as well)
- [ ] **CLI-06**: CLI auto-closes bad-answer queue items whose subsequent re-runs pass (mark "self-resolved")
- [ ] **CLI-07**: CLI failures correctly identify deliberately-corrupted prompt templates (verifies the regression loop works)

### Demo & Polish (Phase 7)

- [ ] **DEMO-01**: README includes architecture diagram (from Phase 1) and setup steps verified on a fresh machine
- [ ] **DEMO-02**: GIF or screenshots of trace explorer + bad-answer queue embedded in README
- [ ] **DEMO-03**: Cost widget on dashboard
- [ ] **DEMO-04**: "Export trace as JSON" button on trace detail
- [ ] **DEMO-05**: Scripted "stale doc" demo scenario uses a synthetic stale fixture (NOT live URL drift)
- [ ] **DEMO-06**: Clean-state acceptance test: fresh `docker compose up` + corpus ingest reproduces the full demo flow (ask question → see trace → flag bad answer → run regression CLI) in ≤15 minutes
- [ ] **DEMO-07**: Demo corpus snapshotted to a fixture file (not live URL fetches)

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Streaming

- **V2-STRM-01**: Server-side streaming responses to chat UI

### Auth

- **V2-AUTH-01**: User authentication
- **V2-AUTH-02**: Multi-tenant trace isolation

### Reranking

- **V2-RANK-01**: Cross-encoder reranker (Cohere Rerank or BGE) as a config-flag enhancement

### Advanced eval

- **V2-EVAL-01**: Custom eval dimension authoring UI
- **V2-EVAL-02**: Multi-judge ensemble for higher confidence on borderline scores

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Authentication / multi-tenant | Single-user local deployment first; out of v1 — see V2-AUTH-* |
| Production hosting / SLA | Local Docker Compose is the deployment target |
| Streaming responses | Defer to v2 to keep request lifecycle simple for tracing — see V2-STRM-01 |
| Multi-modal input (PDFs with images, audio queries) | Storage/bandwidth + tracer schema explosion |
| Agentic tool-use beyond retrieval | Single-step retrieve-then-answer keeps the trace tree simple; multi-hop is a v2+ axis |
| Cross-session conversational memory | Within-session history allowed; cross-session memory adds storage + privacy surface not needed for v1 |
| Real-time alerting UI | Use config-file thresholds in v1; UI alerting deferred |
| Production-grade error budgets / SLOs | Out of scope for portfolio-grade local deployment |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| DSGN-01 | Phase 1 | Complete (01-01-SUMMARY.md) |
| DSGN-02 | Phase 1 | Complete (01-02-SUMMARY.md) |
| DSGN-03 | Phase 1 | Complete (01-07-SUMMARY.md) |
| DSGN-04 | Phase 1 | Complete (01-04-SUMMARY.md) |
| DSGN-05 | Phase 1 | Complete (01-05-SUMMARY.md) |
| DSGN-06 | Phase 1 | Complete (01-06-SUMMARY.md) |
| DSGN-07 | Phase 1 | Complete (01-07-SUMMARY.md) |
| DSGN-08 | Phase 1 | Complete (01-02-SUMMARY.md) |
| DSGN-09 | Phase 1 | Complete (01-01-SUMMARY.md) |
| DSGN-10 | Phase 1 | Complete (01-03-SUMMARY.md) |
| INFRA-01 | Phase 2 | Pending |
| INFRA-02 | Phase 2 | Pending |
| INFRA-03 | Phase 2 | Pending |
| INFRA-04 | Phase 2 | Pending |
| INFRA-05 | Phase 2 | Pending |
| CORP-01 | Phase 3 | Pending |
| CORP-02 | Phase 3 | Pending |
| CORP-03 | Phase 3 | Pending |
| CORP-04 | Phase 3 | Pending |
| CORP-05 | Phase 3 | Pending |
| RAG-01 | Phase 3 | Pending |
| RAG-02 | Phase 3 | Pending |
| RAG-03 | Phase 3 | Pending |
| RAG-04 | Phase 3 | Pending |
| RAG-05 | Phase 3 | Pending |
| RAG-06 | Phase 3 | Pending |
| CHAT-01 | Phase 3 | Pending |
| CHAT-02 | Phase 3 | Pending |
| CHAT-03 | Phase 3 | Pending |
| CHAT-04 | Phase 3 | Pending |
| CHAT-05 | Phase 3 | Pending |
| ADMN-01 | Phase 3 | Pending |
| ADMN-02 | Phase 3 | Pending |
| ADMN-03 | Phase 3 | Pending |
| ADMN-04 | Phase 3 | Pending |
| TRCR-01 | Phase 4 Plan 01 | Complete |
| TRCR-02 | Phase 4 | Pending |
| TRCR-03 | Phase 4 | Pending |
| TRCR-04 | Phase 4 | Pending |
| TRCR-05 | Phase 4 Plan 04 | Complete |
| TRCR-06 | Phase 4 Plan 02 (queue) + Plan 03 (writer/consumer) | Complete |
| TRCR-07 | Phase 4 Plan 03 | Complete |
| TRCR-08 | Phase 4 Plan 06 | Pending |
| TRCR-09 | Phase 4 Plan 01 | Complete |
| TRCR-10 | Phase 4 Plan 01 | Complete |
| EXPL-01 | Phase 4 Plan 04 | Complete |
| EXPL-02 | Phase 4 Plan 04 | Complete |
| EXPL-03 | Phase 4 | Pending |
| EXPL-04 | Phase 4 | Pending |
| EVAL-01 | Phase 5 | Pending |
| EVAL-02 | Phase 5 | Pending |
| EVAL-03 | Phase 5 | Pending |
| EVAL-04 | Phase 5 | Pending |
| EVAL-05 | Phase 5 | Pending |
| EVAL-06 | Phase 5 | Pending |
| FBCK-01 | Phase 5 | Pending |
| FBCK-02 | Phase 5 | Pending |
| FBCK-03 | Phase 5 | Pending |
| FBCK-04 | Phase 5 | Pending |
| FBCK-05 | Phase 5 | Pending |
| FBCK-06 | Phase 5 | Pending |
| FBCK-07 | Phase 5 | Pending |
| DASH-01 | Phase 5 | Pending |
| DASH-02 | Phase 5 | Pending |
| DASH-03 | Phase 5 | Pending |
| DASH-04 | Phase 5 | Pending |
| DASH-05 | Phase 5 | Pending |
| DASH-06 | Phase 5 | Pending |
| CLI-01 | Phase 6 | Pending |
| CLI-02 | Phase 6 | Pending |
| CLI-03 | Phase 6 | Pending |
| CLI-04 | Phase 6 | Pending |
| CLI-05 | Phase 6 | Pending |
| CLI-06 | Phase 6 | Pending |
| CLI-07 | Phase 6 | Pending |
| DEMO-01 | Phase 7 | Pending |
| DEMO-02 | Phase 7 | Pending |
| DEMO-03 | Phase 7 | Pending |
| DEMO-04 | Phase 7 | Pending |
| DEMO-05 | Phase 7 | Pending |
| DEMO-06 | Phase 7 | Pending |
| DEMO-07 | Phase 7 | Pending |

**Coverage:**
- v1 requirements: 75 total
- Mapped to phases: 75
- Unmapped: 0 ✓

---
*Requirements defined: 2026-05-04*
*Last updated: 2026-05-04 — traceability updated to GSD phase numbers 1-7 (Phase −1 → 1, Phase 0 → 2, PRD Phase 1 → 3, PRD Phase 2 → 4, PRD Phase 3 → 5, PRD Phase 4 → 6, PRD Phase 5 → 7)*
