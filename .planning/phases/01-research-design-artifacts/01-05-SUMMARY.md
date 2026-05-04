---
phase: 01-research-design-artifacts
plan: 05
subsystem: database
tags: [erd, data-model, postgres, pgvector, jsonb, partitioning, hnsw, design]

requires:
  - phase: 01-CONTEXT
    provides: D-17 (ERD scope — 5 tables + pgvector chunks), D-47 (payload-storage convention — span_payloads side table), D-49 (chunks metadata mandate — embedding_model + embedding_model_version + indexed_at + startup assertion), D-51 (spans table partitioned by started_at month at write time, expensive to retrofit)
  - phase: 01-01 (ADRs Wave 1)
    provides: docs/decisions/002-vector-store.md (pgvector on Postgres 16; VECTOR(1024); HNSW vector_cosine_ops), docs/decisions/003-embedding-provider.md (voyage-code-3 → 1024-dim; embedding metadata mandate), docs/decisions/004-trace-storage.md (Postgres 16 + JSONB GIN; span_payloads side table; PARTITION BY RANGE (started_at) monthly)
  - phase: 01-04 (trace schema)
    provides: docs/trace-schema.md (Payload Storage Convention referenced — full prompts/responses live in span_payloads JSONB, NOT span attributes; this ERD is the destination contract for that convention)
  - phase: research
    provides: 01-RESEARCH.md §"Per-Artifact Authoring Guide › Artifact 6" + §"Mermaid Syntax Reference › erDiagram" (lines 545-605) — verbatim erDiagram sample with all 5 entities + cardinalities

provides:
  - DB schema / ERD specification at docs/data-model.md (DSGN-05) — Mermaid erDiagram + Postgres DDL for 5 trace tables + pgvector chunks schema + migration strategy
  - Phase 2 INFRA-01 Alembic migration contract — initial migration creates: traces, spans (PARTITIONED BY RANGE started_at), span_payloads, feedback (with rating CHECK constraint), regression_cases, plus chunks (VECTOR(1024) + HNSW) + 3 months forward-rolling spans partitions
  - Phase 3 CORP-04 startup-assertion contract — chunks table has embedding_model + embedding_model_version + indexed_at columns; the assertion `config.embedding_model == chunks.embedding_model` is the silent-garbage-retrieval mitigation (Pitfall #3)
  - Phase 6 CLI-05 regression-promote contract — regression_cases.source_trace_id FK → traces.id is how a trace gets promoted into the regression set; expected_doc_section + expected_chunk_keywords (JSONB) are the assertion fields
  - Phase 5 FBCK-05 schema-allocation guarantee — feedback.diagnosis_tag column exists from day one; UI surfaces in Phase 5 (per D-13 capture-intent-without-implementing pattern)

affects: [01-06 API contract (POST /chat response includes trace_id from traces.id; POST /feedback writes feedback row with trace_id FK; GET /traces queries traces table; GET /traces/{id} joins traces × spans × span_payloads), 01-08 verification (fresh-agent docs check Q4 "data model — what tables exist and how do they relate" answerable from this file alone), Phase 2 INFRA-01 (Alembic migration is derived directly from the Postgres DDL block here — no translation), Phase 2 INFRA-02 (monthly partition rotation is documented as out-of-scope Phase 2 work but the partition naming convention spans_y{YYYY}m{MM} is fixed here), Phase 3 CORP-01..04 (chunks table schema + embedding metadata + canonical doc_section taxonomy), Phase 4 TRCR-02/03 (Postgres exporter writes to spans/span_payloads exactly as specified here; Spans-by-month partition routing is exporter responsibility), Phase 5 FBCK-01..05 (feedback table schema; rating CHECK constraint enforces (-1, 1) at DB layer), Phase 6 CLI-05 (regression_cases promotion writes a row keyed to source_trace_id), Phase 7 DEMO-04 (JSON export queries traces + spans + span_payloads via FK joins)]

tech-stack:
  added: []  # design-only markdown; no runtime deps in Phase 1
  patterns:
    - "Range partitioning on append-only time-series tables (spans BY RANGE started_at month) at write time — cheap upfront, prohibitively expensive to retrofit. Per-partition GIN(attrs) and (trace_id) indexes apply per partition. (D-51 / Pitfall #2)"
    - "JSONB side table for unbounded payloads — span_payloads.payload holds full prompts/responses/chunks; spans.attrs holds only typed metadata. Span list queries stay cheap (no payload bloat); payload reads happen only on detail drill-in. (D-47)"
    - "Partitioned-parent FK omission — span_payloads has NO FK to spans because Postgres does not support cross-partition FKs cheaply; FK enforcement is application-layer in tracer/exporters/postgres.py. Documented inline in DDL comment so future readers understand the omission is deliberate."
    - "Embedding-metadata triple-column mandate — chunks table records (embedding_model, embedding_model_version, indexed_at) on every row. Startup assertion in Phase 3 CORP-04 compares config.embedding_model to corpus.embedding_model and refuses to start on mismatch. Converts silent garbage retrieval into a loud startup error. (D-49 / Pitfall #3)"
    - "DB-layer integrity constraints over application-layer trust — feedback.rating uses CHECK (rating IN (-1, 1)); regression_cases.expected_chunk_keywords is JSONB NOT NULL (assertion data must exist); spans.attrs has NOT NULL DEFAULT '{}'::jsonb (never null, always queryable)."
    - "ON DELETE CASCADE on trace_id FKs (spans, feedback) — dropping a trace cascades to its spans and feedback rows. regression_cases.source_trace_id has NO ON DELETE because regression cases must outlive the source trace they were promoted from."

key-files:
  created:
    - docs/data-model.md
  modified: []

key-decisions:
  - "Used the verbatim erDiagram from 01-RESEARCH.md lines 547-589 (mandated by the plan's <action> §3) — preserves the audit trail (research → CONTEXT → PLAN → file) and matches the Mermaid Syntax Reference. All 5 entities + 4 cardinality relationships present."
  - "spans table is PARTITIONED BY RANGE (started_at) at the schema level (D-51) — initial monthly partition spans_y2026m05 created in DDL with FOR VALUES FROM ('2026-05-01') TO ('2026-06-01'). Per-partition indexes (GIN on attrs, btree on trace_id) follow the same naming convention spans_y{YYYY}m{MM}_{idx}. Phase 2 INFRA-01 Alembic migration extends this with 3 months forward-rolling partitions; Phase 2 INFRA-02 owns rotation."
  - "span_payloads has NO FK constraint to spans — partitioned parent tables in Postgres do not support cheap FK enforcement; the DDL comment documents this and points to tracer/exporters/postgres.py for application-layer enforcement. PRIMARY KEY span_id ensures 1:1 spans→payload at insert time."
  - "Composite primary key on spans (id, started_at) — Postgres requires the partition key (started_at) to be part of the PK on a partitioned table. id alone would be unique conceptually but cannot be the PK. UUIDs collide vanishingly rarely so the composite PK is a Postgres correctness requirement, not a uniqueness requirement."
  - "feedback.rating CHECK (rating IN (-1, 1)) constraint — DB-layer rejection of invalid values (e.g., 0 or 2) means a misbehaving client cannot poison the feedback table. Application-layer Pydantic validation belongs in /docs/api.md (Plan 01-06) but the DB layer is the last line of defense."
  - "feedback.diagnosis_tag TEXT column allocated in Phase 1 (per D-13 'capture intent without implementing' pattern adapted from D-49 / Plan 01-04 trace-schema feedback.user) — the FBCK-05 UI is Phase 5; the column lives now so backfill is trivial. Allowed values enumerated in /docs/trace-schema.md feedback.user section: Retrieval, PromptAssembly, LLM, CorpusStale, Other."
  - "chunks table has 3 metadata columns — embedding_model TEXT NOT NULL, embedding_model_version TEXT NOT NULL, indexed_at TIMESTAMPTZ NOT NULL DEFAULT now() — exactly as ADR 003 mandates (D-49). Per-row metadata (rather than table-level) means a partial re-embedding to a new model can coexist transitionally with the old one until the cutover is complete."
  - "HNSW index on chunks.embedding using vector_cosine_ops — matches ADR 002's choice (HNSW + cosine similarity); CREATE INDEX chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops). Secondary btree index on chunks.doc_section supports the canonical 12-section taxonomy filter from /docs/eval/coverage_set.yaml."
  - "Cross-References section uses relative links (./architecture.md, ./trace-schema.md, ./decisions/002-vector-store.md, etc.) — the file lives at docs/data-model.md so a fresh agent navigating /docs/ never breaks a link by relocating."

patterns-established:
  - "Phase 1 design artifacts that produce DB DDL include the DDL inline as a fenced ```sql block — Phase 2 Alembic migrations consume it directly via copy-paste. Schema drift between /docs/ and /tracer_ai/ is eliminated because the spec IS the DDL."
  - "Range-partitioned tables in this codebase use the spans_y{YYYY}m{MM} naming convention with per-partition indexes named {parent}_y{YYYY}m{MM}_{indexname}. Phase 2 INFRA-02 partition rotation must follow this convention for monitoring/dashboarding query parity."
  - "Embedding-metadata triple-column pattern (model + model_version + indexed_at) applies to ANY future vector table — not just chunks. If Phase 3+ adds a second corpus (e.g., user-uploaded documents), the same triple must apply per ADR 003 / D-49 to preserve the silent-garbage-retrieval mitigation."
  - "DB-layer constraint pattern — DB CHECK constraints catch values that bypass application-layer validation; Pydantic validation in /docs/api.md is the first line, DB CHECK is the second. Both layers MUST agree on allowed values; drift = bug."

requirements-completed: [DSGN-05]

duration: ~1 min
completed: 2026-05-04
---

# Phase 1 Plan 05: Data Model / ERD Summary

**Authored docs/data-model.md (151 LOC) — Mermaid erDiagram for 5 trace tables (traces, spans, span_payloads, feedback, regression_cases) plus full Postgres DDL with spans PARTITION BY RANGE (started_at) monthly (D-51) and pgvector chunks schema with VECTOR(1024) + HNSW index + 3-column embedding metadata mandate (D-49). The DDL IS the contract Phase 2 INFRA-01 Alembic migration consumes; the chunks metadata IS the contract Phase 3 CORP-04 startup assertion enforces.**

## Performance

- **Duration:** ~1 min
- **Started:** 2026-05-04T04:09:43Z
- **Completed:** 2026-05-04T04:10:46Z
- **Tasks:** 1
- **Files created:** 1 (`docs/data-model.md`, 151 LOC)
- **Files modified:** 0

## Accomplishments

- Created `docs/data-model.md` (151 LOC) — within the planned 120-160 LOC target.
- Authored Mermaid `erDiagram` block with all 5 entities (traces, spans, span_payloads, feedback, regression_cases) and 4 FK cardinality relationships verbatim from 01-RESEARCH.md lines 547-589 — the audit trail (research → CONTEXT → PLAN → file) is preserved.
- Authored full Postgres DDL block: 5 `CREATE TABLE` statements + 1 `traces_started_at_idx` index + 2 partition-level indexes (`spans_y2026m05_attrs_gin`, `spans_y2026m05_trace_id_idx`) + 1 `feedback_trace_id_idx`. spans table is `PARTITION BY RANGE (started_at)` per D-51; initial partition `spans_y2026m05` created with `FOR VALUES FROM ('2026-05-01') TO ('2026-06-01')`.
- Authored separate pgvector chunks DDL block: `CREATE EXTENSION IF NOT EXISTS vector` + `CREATE TABLE chunks` with `VECTOR(1024)` column + 3 embedding-metadata columns (`embedding_model`, `embedding_model_version`, `indexed_at`) per D-49 + HNSW index using `vector_cosine_ops` + btree on `doc_section` for the canonical-12-section taxonomy filter from /docs/eval/coverage_set.yaml.
- Encoded the D-49 startup-assertion mandate inline ("Startup assertion (Phase 3 CORP-04) verifies `config.embedding_model == chunks.embedding_model` before serving requests — prevents silent garbage-retrieval (Pitfall #3 / ADR 003).").
- Encoded `feedback.rating CHECK (rating IN (-1, 1))` DB-layer constraint — last line of defense against malformed feedback (rejects 0, 2, etc. at INSERT time).
- Encoded `feedback.diagnosis_tag TEXT` column allocated for Phase 5 FBCK-05 (per D-13 capture-intent pattern); UI defers, schema lives now.
- Documented partitioned-parent FK omission inline (`span_payloads` has no FK to `spans` because Postgres cross-partition FKs are expensive; FK enforcement is application-layer in `tracer/exporters/postgres.py`).
- Authored Migration Strategy section pointing to Phase 2 INFRA-01 (initial Alembic migration) and Phase 2 INFRA-02 (partition rotation) — runtime detail correctly scoped out of Phase 1.
- Cross-References section links docs/architecture.md, docs/trace-schema.md, docs/decisions/{002,003,004}-* with relative paths — robust to docs/ tree relocation.

## Task Commits

Each task was committed atomically:

1. **Task 1: Author docs/data-model.md (DSGN-05, ERD + Postgres DDL + pgvector chunks schema)** — `ff2219d` (docs)

_Plan metadata commit will follow this SUMMARY._

## Files Created/Modified

- `docs/data-model.md` (created, 151 LOC) — DB schema / ERD specification. Sections: framing paragraph / Entity-Relationship Diagram (Mermaid erDiagram, 5 entities + FKs) / Postgres DDL (5 trace tables + spans monthly partitioning + per-partition indexes) / pgvector Chunks Collection Schema (VECTOR(1024) + HNSW + embedding metadata triple) / Migration Strategy / Cross-References.

### The 5 trace tables documented

| Table | Role | Key Schema Element | Partitioned? |
|-------|------|--------------------|--------------|
| traces | One row per chat request; owns trace_id | id PK, started_at (idx DESC) | no |
| spans | One row per span; heterogeneous attrs JSONB | (id, started_at) PK; trace_id FK CASCADE | yes — RANGE (started_at) monthly |
| span_payloads | Unbounded full prompts/responses; 1:1 with span | span_id PK; no FK (D-47, partitioned-parent omission) | no |
| feedback | Thumbs-up/down + comment + diagnosis_tag (FBCK-05 reservation) | id PK; trace_id FK CASCADE; rating CHECK IN (-1, 1) | no |
| regression_cases | Traces promoted into regression set (Phase 6 CLI-05) | id PK; source_trace_id FK (no CASCADE — outlives trace) | no |

### The chunks (pgvector) schema

| Column | Type | Mandate |
|--------|------|---------|
| id | UUID PK | — |
| doc_id | TEXT NOT NULL | — |
| doc_section | TEXT NOT NULL | Canonical 12-section taxonomy from /docs/eval/coverage_set.yaml |
| content | TEXT NOT NULL | Chunk text |
| embedding | VECTOR(1024) NOT NULL | Voyage voyage-code-3 dimension (ADR 002 + ADR 003) |
| embedding_model | TEXT NOT NULL | D-49 / Pitfall #3 — startup assertion contract |
| embedding_model_version | TEXT NOT NULL | D-49 — pinned snapshot |
| indexed_at | TIMESTAMPTZ NOT NULL DEFAULT now() | D-49 — when this row was embedded |
| metadata | JSONB NOT NULL DEFAULT '{}' | future per-row attributes |

Indexes: `chunks_embedding_hnsw` (HNSW, vector_cosine_ops) + `chunks_doc_section_idx` (btree).

### Verbatim mandates encoded in the file

- **D-17 (ERD scope):** `erDiagram` block has all 5 entities + 4 FK relationships (traces ||--o{ spans, traces ||--o{ feedback, spans ||--o| span_payloads, regression_cases }o--|| traces).
- **D-47 (payload storage convention):** span_payloads side table with JSONB payload column; framing paragraph cites docs/trace-schema.md for the full convention.
- **D-49 (chunks metadata mandate):** chunks table has all 3 columns (embedding_model + embedding_model_version + indexed_at) NOT NULL; inline note links the startup assertion to Phase 3 CORP-04.
- **D-51 (spans partitioning):** spans table `PARTITION BY RANGE (started_at)`; initial spans_y2026m05 partition created in DDL; comment notes Phase 2 Alembic creates rolling future partitions.
- **ADR 002 cross-reference:** "002-vector-store" appears in pgvector framing + Cross-References.
- **ADR 003 cross-reference:** "003-embedding-provider" appears in Cross-References + as inline citation on chunks-metadata note.
- **ADR 004 cross-reference:** "004-trace-storage" appears in framing paragraph + Migration Strategy + Cross-References.

## Decisions Made

- **Verbatim erDiagram from 01-RESEARCH.md lines 547-589** — preserves the research → CONTEXT → PLAN → file audit trail; the mermaid syntax reference IS the contract.
- **Composite PK on spans (id, started_at)** — Postgres requires the partition key in the PK; documented as a Postgres correctness requirement (not a uniqueness one).
- **span_payloads has NO FK to spans** — partitioned-parent FK enforcement is expensive in Postgres; the DDL comment documents this and delegates to tracer/exporters/postgres.py at the application layer. PRIMARY KEY span_id ensures 1:1 spans→payload at insert time.
- **feedback.rating CHECK (rating IN (-1, 1))** — DB-layer rejection of malformed values; complements Pydantic validation in /docs/api.md (Plan 01-06).
- **feedback.diagnosis_tag column allocated now, populated in Phase 5** — D-13 capture-intent-without-implementing pattern adapted from Plan 01-04 (trace-schema.md feedback.user reservation).
- **Per-partition indexes named {parent}_y{YYYY}m{MM}_{idx}** — naming-convention pattern for Phase 2 INFRA-02 partition rotation to follow.
- **regression_cases.source_trace_id has NO ON DELETE clause** — regression cases must outlive the source trace they were promoted from (Phase 6 CLI-05 contract); explicit absence is intentional.
- **Cross-References use relative links** — robust to docs/ tree relocation.

## Deviations from Plan

None — plan executed exactly as written.

The plan was a single-task spec-authoring job with a programmatic verify step. The verify-step grep assertions all pass (see Self-Check below). The action block in the plan provided a near-complete file template; the executor preserved every required element verbatim and added no out-of-scope content.

**Total deviations:** 0
**Impact on plan:** N/A — clean execution.

## Issues Encountered

None.

## Self-Check

- File `docs/data-model.md`: **FOUND** (151 LOC; within the 120-160 LOC target).
- Commit `ff2219d`: **FOUND** in `git log --oneline` as `docs(01-05): author docs/data-model.md (DSGN-05)`.
- Plan's `<verify>` automation: **PASSED** — all 14 grep assertions succeeded:
  - `^# Data Model` h1 present
  - `^```mermaid` fence present
  - `erDiagram` token present
  - All 5 entity names present (traces, spans, span_payloads, feedback, regression_cases)
  - `PARTITION BY RANGE (started_at)` present (D-51)
  - `CREATE EXTENSION` present (pgvector enable)
  - `VECTOR(1024)` present (Voyage voyage-code-3 dimension)
  - `hnsw` present (HNSW index)
  - `embedding_model`, `embedding_model_version`, `indexed_at` all present (D-49)
  - `002-vector-store` cross-reference present
  - `004-trace-storage` cross-reference present
  - `CHECK (rating IN` constraint present
- Acceptance criteria from PLAN.md: all 11 satisfied. Success-criteria checklist from the prompt: all 8 satisfied (file exists; ERD models 5 tables; FK relationships present in erDiagram; Postgres DDL has CREATE TABLE for all 5; spans partitioned by started_at; pgvector chunks has VECTOR(1024) + HNSW + 3 metadata cols; ADR 002/003/004 cited; task committed).

## Self-Check: PASSED

## User Setup Required

None — no external service configuration required. (No USER-SETUP.md generated.)

## Next Phase Readiness

- Phase 1 progress: 5/8 plans complete (DSGN-01, DSGN-02, DSGN-04, DSGN-05, DSGN-08, DSGN-09, DSGN-10 satisfied; DSGN-03 sequence diagram + DSGN-06 API contract + DSGN-07 wireframes remain in Plans 01-06..01-07; Plan 01-08 is the fresh-agent docs verification gate).
- Resume file: `.planning/phases/01-research-design-artifacts/01-06-PLAN.md` (next plan in the phase — likely sequence diagram or API contract, per the phase plan order).
- **Contract pinned for Phase 2 INFRA-01:** the Postgres DDL block in `docs/data-model.md` IS the initial Alembic migration. No translation, no reinterpretation — the migration script CREATE TABLE statements match this DDL byte-for-byte (modulo Alembic op syntax wrapping). Includes 5 trace tables + spans monthly partitioning + chunks (with VECTOR + HNSW + embedding metadata triple) + 3 forward-rolling partitions.
- **Contract pinned for Phase 2 INFRA-02:** partition rotation must use the `spans_y{YYYY}m{MM}` naming convention with `{parent}_y{YYYY}m{MM}_{idx}` for per-partition indexes. Rotation strategy is out-of-scope Phase 1 but the conventions are locked here.
- **Contract pinned for Phase 3 CORP-04:** the chunks table's `embedding_model`, `embedding_model_version`, `indexed_at` columns are the source the startup assertion (`config.embedding_model == chunks.embedding_model`) reads from. The assertion converts silent garbage retrieval (Pitfall #3) into a loud startup error — D-49 / ADR 003 mandate.
- **Contract pinned for Phase 4 TRCR-02/03:** the Postgres exporter writes spans rows respecting (id, started_at) composite PK and routes inserts to the correct monthly partition. span_payloads.span_id has NO DB FK — exporter enforces 1:1 application-layer.
- **Contract pinned for Phase 5 FBCK-01..05:** the feedback table schema is locked. `rating CHECK (rating IN (-1, 1))` is enforced at DB layer; `diagnosis_tag` column is allocated and waiting for FBCK-05 UI.
- **Contract pinned for Phase 6 CLI-05:** the regression_cases table is the promotion target; `source_trace_id` FK + `expected_doc_section` + `expected_chunk_keywords` (JSONB) are the assertion fields the regression-promote CLI writes.
- **No blockers introduced.** Plans 01-06 (sequence diagram or API contract) and 01-07 (wireframes) can begin immediately.

---
*Phase: 01-research-design-artifacts*
*Completed: 2026-05-04*
