# Roadmap: tracer-ai

## Overview

tracer-ai is built in seven phases that honor a design-first discipline: Phase 1 locks every architectural decision as ADRs and design artifacts before a single line of code is written. Phase 2 bootstraps the reproducible infrastructure skeleton. Phases 3–5 deliver the core product in vertical slices — working RAG chat with observability, then the tracer and trace explorer on top, then the quality/eval/feedback layer that closes the "why did it fail?" loop. Phase 6 delivers the regression CLI that industrializes the feedback loop. Phase 7 polishes the demo path and produces the portfolio artifact. Every phase leaves the system shippable and verifiable.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Research & Design Artifacts** - Produce all ADRs, diagrams, specs, and wireframes; no code until done
- [ ] **Phase 2: Skeleton & Infrastructure** - Repo scaffold, Docker Compose boots green, pre-commit hooks, README skeleton
- [ ] **Phase 3: RAG Pipeline + Chat UI + Corpus Admin** - Working RAG chat with citations, corpus ingestion CLI, admin UI
- [ ] **Phase 4: Tracer + Trace Explorer** - Span emission, async trace write path, trace list/detail dashboard views
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
**Plans**: TBD

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
**Plans**: TBD
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
**Plans**: TBD
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
| 1. Research & Design Artifacts | 1/8 | In Progress | - |
| 2. Skeleton & Infrastructure | 0/TBD | Not started | - |
| 3. RAG Pipeline + Chat UI + Corpus Admin | 0/TBD | Not started | - |
| 4. Tracer + Trace Explorer | 0/TBD | Not started | - |
| 5. Quality Layer + Feedback | 0/TBD | Not started | - |
| 6. Eval CLI + Regression Set | 0/TBD | Not started | - |
| 7. Polish + Demo Path | 0/TBD | Not started | - |
