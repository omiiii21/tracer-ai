# Roadmap: tracer-ai

## Overview

tracer-ai is built in seven phases that honor a design-first discipline: Phase 1 locks every architectural decision as ADRs and design artifacts before a single line of code is written. Phase 2 bootstraps the reproducible infrastructure skeleton. Phases 3–5 deliver the core product in vertical slices — working RAG chat with observability, then the tracer and trace explorer on top, then the quality/eval/feedback layer that closes the "why did it fail?" loop. Phase 6 delivers the regression CLI that industrializes the feedback loop. Phase 7 polishes the demo path and produces the portfolio artifact. Every phase leaves the system shippable and verifiable.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Research & Design Artifacts** - Produce all ADRs, diagrams, specs, and wireframes; no code until done
- [x] **Phase 2: Skeleton & Infrastructure** - Repo scaffold, Docker Compose boots green, pre-commit hooks, README skeleton
- [x] **Phase 3: RAG Pipeline + Chat UI + Corpus Admin** - Working RAG chat with citations, corpus ingestion CLI, admin UI
- [x] **Phase 4: Tracer + Trace Explorer** - Span emission, async trace write path, trace list/detail dashboard views
- [ ] **Phase 5: Quality Layer + Feedback** - LLM-as-judge eval, feedback endpoint, bad-answer queue, time-series charts
- [ ] **Phase 6: Eval CLI + Regression Set** - Regression CLI running both proactive and reactive query sets
- [ ] **Phase 7: Polish + Demo Path** - README, screenshots, cost widget, trace export, scripted demo, clean-state acceptance test

## Phase Details

### Phase 1: Research & Design Artifacts
**Goal**: Every design decision is resolved and documented so Phases 2–7 are pure execution with no mid-phase architecture discovery
**Depends on**: Nothing (first phase)
**Requirements**: DSGN-01, DSGN-02, DSGN-03, DSGN-04, DSGN-05, DSGN-06, DSGN-07, DSGN-08, DSGN-09, DSGN-10
**Success Criteria** (what must be TRUE):
  1. All 9 GSD-OPEN-N items from the PRD have a corresponding ADR in `/docs/decisions/` with context, options, decision, and consequences
  2. A fresh agent given only the `/docs/` directory can answer — what the system does, how data flows, what the trace schema is, what API endpoints exist, and what the UI looks like — without reading any code
  3. The proactive coverage regression query set (10+ queries covering each major Claude API doc section) is authored and checked in
  4. The module dependency diagram confirms zero circular dependencies in the planned architecture
  5. The risk and scope-trim plan documents which phases get cut first if build budget slips more than 25%
**Plans**: TBD

### Phase 2: Skeleton & Infrastructure
**Goal**: The full Docker Compose stack boots green and the development environment is reproducible from a fresh checkout
**Depends on**: Phase 1
**Requirements**: INFRA-01, INFRA-02, INFRA-03, INFRA-04, INFRA-05
**Success Criteria** (what must be TRUE):
  1. Running `docker compose up` from a fresh checkout starts FastAPI hello-world, Vite hello-world, and Postgres 16 with the pgvector extension — all green, no manual steps
  2. All Docker image tags are pinned (no `:latest`); `.env.example` is checked in; startup validates all required env vars with clear error messages on missing values
  3. Pre-commit hooks enforce `ruff`, `mypy --strict`, frontend `tsc`, and the basic test runner on every commit
  4. The repo scaffold matches the ARCHITECTURE.md module layout (`tracer_ai/`, `frontend/`, `infra/`) and the `/docs/decisions/` directory exists
**Plans:** 6 plans

**Wave 1** *(complete 2026-05-04)*
- [x] 02-01-PLAN.md — Repo scaffold + pyproject.toml + tracer_ai package skeleton + .env.example + Wave-0 smoke tests; Voyage pricing prereq (BLOCKING checkpoint, auto-approved per RESEARCH.md Topic 8 + --auto chain)

**Wave 2** *(complete 2026-05-04)*
- [x] 02-02-PLAN.md — Compose stack + Dockerfile.backend (multi-stage uv + non-root USER app uid 1000) + Dockerfile.frontend + db/init.sql with vector extension; live verify: `db` healthy, vector extension installed, tracer role NOSUPERUSER, container `whoami` = `app`

**Wave 3** *(complete 2026-05-04)*
- [x] 02-03-PLAN.md — Alembic async env.py + 0001_initial.py (verbatim DDL from data-model.md: 5 trace tables + chunks + 3 monthly partitions for 2026-05/06/07) + migrate service wired; live verify: migrate exit 0, 9 tables present (6 + 3 partitions), pgvector 0.8.2 active, HNSW index on chunks.embedding, feedback CHECK constraint enforced, alembic_version=0001

**Wave 4** *(complete 2026-05-04 — ran sequentially; INFRA-02 4-service boot closed)*
- [x] 02-04-PLAN.md — Full Settings (FLAT, fail-fast at import, extra=forbid) + FastAPI lifespan + asyncpg pool + GET /healthz + config-failfast tests; live verify: `curl http://localhost:8000/healthz` → 200 + `{"status":"ok","db":"ok","version":"0.1.0"}`; 24 tests pass; mypy --strict clean
- [x] 02-05-PLAN.md — Vite 5 + React 18.3.1 + TypeScript 5.5 + Tailwind v3.4 + shadcn (Zinc) + Card/Button + hello / route; live verify: `curl http://localhost:5173/` → 200 + HTML with React root; pin gates: react@^19=0, tailwindcss@^4=0, react@^18.3.1=1, tailwindcss@^3.4=1

**Wave 5** *(complete 2026-05-04 — Phase 2 EXIT)*
- [x] 02-06-PLAN.md — Pre-commit (11 hooks) + gitleaks + custom import_cycle_guard.py (B-2 alias-only emission) + README quick-start + phase-end verification gate (14/14 steps PASSED on destructive fresh-checkout drill); INFRA-04 + INFRA-05 closed

**Cross-cutting constraints** *(must_haves shared by ≥2 plans):*
- No `:latest` Docker tags; every image digest-pinned (enforced by pre-commit grep) — D-2.36 (plans 02-02, 02-06)
- No `gen_ai.system` (deprecated; use `gen_ai.provider.name`) — D-2.40 (plans 02-01, 02-06)
- No `class Config:` (Pydantic v1) — `model_config = ConfigDict(...)` only — D-2.39 (plans 02-01, 02-04, 02-06)
- No `print(...)` in `tracer_ai/` outside `cli/__main__.py`; `structlog.get_logger()` only — D-2.37 (plans 02-01, 02-06)
- No SDK imports outside their adapter file (`from anthropic` only in `rag/llm.py` + `eval/llm_judge.py`) — D-2.38 (plans 02-01, 02-06)
- Module-deps DAG enforced at commit time (`config → tracer → rag → eval → api/cli`; `corpus → rag/embedder` only) — D-2.27, D-45 (plans 02-01, 02-06)
- Pydantic v2 strict-mode (`extra="forbid"`) on all API schemas — D-2.39, D-26 (plans 02-04, 02-06)
- Tailwind v3 + React 18 pinned (Tailwind v4 + React 19 break Tremor + shadcn) — D-2.30 (plans 02-02, 02-05)

### Phase 3: RAG Pipeline + Chat UI + Corpus Admin
**Goal**: A working RAG chatbot answers questions about the Claude API docs with citation-backed answers, and an operator can manage the corpus from a UI
**Depends on**: Phase 2
**Requirements**: CORP-01, CORP-02, CORP-03, CORP-04, CORP-05, RAG-01, RAG-02, RAG-03, RAG-04, RAG-05, RAG-06, CHAT-01, CHAT-02, CHAT-03, CHAT-04, CHAT-05, ADMN-01, ADMN-02, ADMN-03, ADMN-04
**Success Criteria** (what must be TRUE):
  1. Asking 5 hand-picked questions about the Claude API returns accurate, cited answers with latency, token count, and estimated cost visible in the chat UI
  2. Each retrieved chunk is cited inline and expandable; each message links to its trace (even before the trace explorer is built — link is present, view completes in Phase 4)
  3. The admin UI at `/admin` shows the current corpus (doc list, chunk count, embedding model, last-indexed timestamp) and a re-index button that triggers ingestion
  4. A corpus ingested with one embedding model triggers a startup assertion failure if the config is changed to a different model — mismatch is caught before garbage retrieval occurs
  5. End-to-end answer latency is under 5 seconds for a typical single-user query
**Plans**: TBD
**UI hint**: yes

### Phase 4: Tracer + Trace Explorer
**Goal**: Every chat request produces a complete, replayable trace visible in a dashboard with span waterfall, payload inspectors, and full filtering
**Depends on**: Phase 3
**Requirements**: TRCR-01, TRCR-02, TRCR-03, TRCR-04, TRCR-05, TRCR-06, TRCR-07, TRCR-08, TRCR-09, TRCR-10, EXPL-01, EXPL-02, EXPL-03, EXPL-04
**Success Criteria** (what must be TRUE):
  1. Every chat request from Phase 3 now produces a persisted trace; the trace list at `/dashboard` shows the query, timestamp, latency, cost, and feedback for each request
  2. Drilling into a trace detail view shows a span waterfall with all four spans (`rag.request`, `rag.retrieve`, `rag.prompt_assemble`, `rag.llm_call`), each retrieved chunk with its similarity score, the full assembled prompt, and the full LLM response
  3. The trace list supports filtering by query text, time range, feedback rating, faithfulness score, and latency bucket
  4. Trace writes add no more than 100ms p95 to the request path (async-queue pattern; measured)
**Plans:** 6 plans

Plans:
**Wave 1** *(complete 2026-05-06)*
- [x] 04-01-PLAN.md -- Schema migration (alembic 0002 adds latency_ms / faithfulness / feedback_rating / estimated_cost_usd + 2026-08 spans partition); Span model field swap (payload_id -> payload); pipeline.py up-front INSERT INTO traces + payload= per child span + UPDATE traces after _emit_root — see 04-01-SUMMARY.md

**Wave 2** *(in progress; 04-02 complete 2026-05-06)*
- [x] 04-02-PLAN.md -- BoundedDropOldestQueue (D-4.06) + saturation logging (D-4.08); standalone unit tests for drop-oldest invariant + concurrent producers + rate-limited log — see 04-02-SUMMARY.md
- [x] 04-03-PLAN.md -- PostgresTraceWriter + SpanConsumer (50-spans-or-250ms batch flush via executemany); lifespan integration (Noop -> Postgres swap, 5s shutdown drain, drain -> cancel -> close pool ordering)

**Wave 3** *(in progress; 04-04 complete 2026-05-06)*
- [x] 04-04-PLAN.md -- TraceStore Protocol + PostgresTraceStore (TRCR-05 three methods, dict[str, Any] returns to preserve module-deps DAG); GET /traces (cursor pagination + 8 filter params) + GET /traces/{trace_id} (two-query pattern); feedback.py wraps INSERT + UPDATE in atomic asyncpg transaction (D-4.03/T-04-04-08) — see 04-04-SUMMARY.md
- [x] 04-05-PLAN.md -- Frontend Dashboard.tsx + TraceDetail.tsx + SpanWaterfall.tsx; install missing shadcn primitives (tabs/table/slider/tooltip/select) + ky; route migration /traces/:id -> /dashboard + /dashboard/traces/:trace_id; MetadataStrip link target updated; TraceStub deleted — see 04-05-SUMMARY.md

**Wave 4** *(complete 2026-05-06 — Phase 4 EXIT)*
- [x] 04-06-PLAN.md -- Phase 4 verification gate: TRCR-08 p95 benchmark (delta -14.78ms vs 100ms budget) + end-to-end pipeline-with-PostgresTraceWriter (1 INSERT + 2 UPDATEs + 4 spans + 3 payloads) + alembic reversibility (live docker compose; 21.66s) + lifespan drain warn-log path; TRCR-02/03 conformance audit clean; TRCR-04 explicitly DEFERRED to Phase 5 EVAL-04 with rationale; 13/14 requirements PASS, 1 DEFERRED — see 04-06-SUMMARY.md and 04-VERIFICATION.md
**UI hint**: yes

### Phase 5: Quality Layer + Feedback
**Goal**: Every trace is automatically scored for faithfulness and relevance by an async LLM judge; bad answers surface in a prioritized review queue; time-series charts show quality drift
**Depends on**: Phase 4
**Requirements**: EVAL-01, EVAL-02, EVAL-03, EVAL-04, EVAL-05, EVAL-06, FBCK-01, FBCK-02, FBCK-03, FBCK-04, FBCK-05, FBCK-06, FBCK-07, DASH-01, DASH-02, DASH-03, DASH-04, DASH-05, DASH-06
**Success Criteria** (what must be TRUE):
  1. A faithfulness score appears on every trace within approximately 30 seconds of the request; the score is a child span (`rag.eval`) of `rag.request` — not an orphaned root span
  2. Clicking thumbs-down on a chat message lands the trace in the bad-answer queue within seconds; the queue is sorted by lowest faithfulness score first
  3. Time-series charts on the dashboard populate as queries are made — latency p50/p95, cost over time, faithfulness mean, and manual feedback ratio are all visible
  4. The bad-answer queue has a "mark resolved" action and a dashboard widget showing queue size and items resolved this week
  5. A judge failure (timeout, rate limit, or exception) never causes a user-facing chat request to fail
**Plans:** 7/7 plans executed

**Wave 1** *(parallel; foundations)*
- [x] 05-01-PLAN.md — Eval foundation: tracer_ai/tracer/context.py hand-rolled contextvar helpers (D-5.06; closes TRCR-04) + tracer_ai/eval/{protocols,prompts,llm_judge}.py (Anthropic Haiku judge + tool_use forced + XML-delimited prompts + injection-escape + MockJudge + PROMPT_VERSION) + tracer_ai/config.py 4 new Settings fields (D-5.13/D-5.09/D-5.05/D-5.14) + ERROR_TYPE / RAG_EVAL_JUDGE_LATENCY_MS constants. EVAL-01 + EVAL-03.
- [x] 05-02-PLAN.md — alembic 0003_feedback_resolved.py (FBCK-04 / D-5.15) + PATCH /feedback/{trace_id}/resolved route + FeedbackResolveResponse schema; idempotent UPDATE; partial index for bad-answer queue exclusion. FBCK-01 + FBCK-02 + FBCK-04 + FBCK-06.
- [x] 05-03-PLAN.md — GET /admin/eval-config endpoint + EvalConfigResponse schema (D-5.13) + GET /admin/queue-health + QueueHealthResponse (FBCK-07 fix; live queue_size + resolved_this_week for the 5th KpiCard); single source of truth for runtime threshold + judge identity; lazy-import PROMPT_VERSION pattern. EVAL-06 + FBCK-07.

**Wave 2** *(parallel; depends on Wave 1 contracts)*
- [x] 05-04-PLAN.md — EvalDispatcher (D-5.07/08/10) + Pipeline ctx_snapshot capture before _emit_root (Pitfall 1) + ChatFinalEvent extension (private excluded fields) + chat.py SSE generator dispatch + lifespan integration (drain order: dispatcher -> consumer -> pool close). Closes TRCR-04 deferral. EVAL-02 + EVAL-04 + EVAL-05. — see 05-04-SUMMARY.md
- [x] 05-05-PLAN.md — GET /traces/timeseries with adaptive bucketing (D-5.17; 1h/24h/7d/30d) + extend GET /traces with max_faithfulness + sort_by=faithfulness_asc (FBCK-03/06 backend) + PostgresTraceStore.timeseries() with generate_series + percentile_cont; LEFT JOIN preserves empty-bucket NULL rows for connectNulls=false. DASH-01..06 + FBCK-03 + FBCK-06.
- [x] 05-06-PLAN.md — tracer-ai calibrate {label, threshold} CLI (D-5.11/12; argparse not Click per Pitfall 10) + best-F1 sweep over [0.3, 0.9] step 0.05 + Pitfall 6 prompt-version mismatch refusal + docs/eval/calibration_set.yaml schema + pyyaml runtime dep; print allowlist preserved (render_sweep_report returns string; CLI prints). EVAL-06.

**Wave 3** *(frontend; depends on Wave 2 endpoints)*
- [x] 05-07-PLAN.md — Frontend: NEW /dashboard/queue page (Tabs User-flagged / Judge-flagged + Mark Resolved + Promote-stub) + Dashboard QualityCharts (4 Tremor time-series; connectNulls=false on every chart, D-5.07 LOAD-BEARING for faithfulness) + 5th KpiCard Queue Health wired to LIVE GET /admin/queue-health (FBCK-07 fix; cache-invalidated on Mark-Resolved via ['queue-health'] queryKey) + TraceDetail diagnosis-tag Select (FBCK-05; preserves current rating instead of forcing -1 — Rule 2 fix) + AppShell Queue nav link + Dashboard NavLink `end` prop (Rule 1 nav active-prefix fix) + extended ky api/traces.ts (getTimeseries, getEvalConfig, getQueueHealth, markResolved, postFeedback). FBCK-02/03/05/06/07 + DASH-01..06. — see 05-07-SUMMARY.md
**UI hint**: yes

### Phase 6: Eval CLI + Regression Set
**Goal**: An operator CLI runs both the proactive coverage set and the reactive promoted set as a regression suite, reporting pass/fail per query and identifying self-resolved items
**Depends on**: Phase 5
**Requirements**: CLI-01, CLI-02, CLI-03, CLI-04, CLI-05, CLI-06, CLI-07
**Success Criteria** (what must be TRUE):
  1. `tracer-ai eval` runs the curated regression set (both proactive coverage queries from Phase 1 and any promoted reactive cases) and prints a per-query pass/fail report in markdown or JSON
  2. Deliberately corrupting the prompt template causes the CLI to fail the correct queries — the regression loop is verified to catch real regressions
  3. Running `tracer-ai promote <trace_id>` from the bad-answer queue adds the trace to the regression set, and it appears in the next CLI run
  4. CLI auto-closes bad-answer queue items whose subsequent re-runs pass, marking them "self-resolved"
**Plans**: TBD

### Phase 7: Polish + Demo Path
**Goal**: A fresh `docker compose up` plus corpus ingest reproduces the full observable RAG demo in under 15 minutes, and the README is portfolio-presentable
**Depends on**: Phase 6
**Requirements**: DEMO-01, DEMO-02, DEMO-03, DEMO-04, DEMO-05, DEMO-06, DEMO-07
**Success Criteria** (what must be TRUE):
  1. Running `docker compose up` on a clean machine and following the README steps verbatim reproduces the full demo flow — ask question, see trace, flag bad answer, run regression CLI — in under 15 minutes
  2. The README includes the architecture diagram from Phase 1 and embedded GIF or screenshots of the trace explorer and bad-answer queue
  3. The "stale doc" demo scenario uses a synthetic stale fixture (not live URL drift), and the demo corpus is snapshotted to a fixture file so the demo is reproducible regardless of upstream doc changes
  4. The trace detail view has an "Export trace as JSON" button and the dashboard shows a cost widget
**Plans**: TBD
**UI hint**: yes

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Research & Design Artifacts | 8/8 | Complete    | 2026-05-04 |
| 2. Skeleton & Infrastructure | 6/6 | Complete    | 2026-05-04 |
| 3. RAG Pipeline + Chat UI + Corpus Admin | 9/9 | Complete (with 1 carried gap) | 2026-05-05 |
| 4. Tracer + Trace Explorer | 6/6 | Complete    | 2026-05-06 |
| 5. Quality Layer + Feedback | 4/7 | In Progress|  |
| 6. Eval CLI + Regression Set | 0/TBD | Not started | - |
| 7. Polish + Demo Path | 0/TBD | Not started | - |
