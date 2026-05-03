---
phase: 01-research-design-artifacts
plan: 01
subsystem: documentation
tags: [adr, design, madr, observability, rag, gsd-open-n, scope-trim]

requires:
  - phase: research
    provides: GSD-OPEN-N resolutions in .planning/research/SUMMARY.md, STACK.md, ARCHITECTURE.md, PITFALLS.md, FEATURES.md
provides:
  - 10 Architecture Decision Records (ADRs 001..010) under docs/decisions/
  - decisions/README.md ADR index linking all 10 ADRs
  - Locked rationale for charting (Tremor v3), vector store (pgvector), embedder (voyage-code-3), trace store (Postgres+JSONB), observability strategy (custom tracer with OTel attribute names), chunking (markdown-header-aware 900/100), re-ranking (none in v1), judge (RAGAS+XML+Haiku dated snapshot), auth (ADR-only direction), and operational scope-trim playbook
affects: [01-02 architecture diagram, 01-03 sequence diagram, 01-04 trace schema, 01-05 data model, 01-06 API contract, 01-07 wireframes, 01-08 module deps + coverage set, Phase 2 INFRA-*, Phase 3 RAG/CHAT/ADMN, Phase 4 TRCR-*, Phase 5 EVAL/FBCK/DASH, Phase 6 CLI-*, Phase 7 DEMO-*]

tech-stack:
  added: []  # design-only phase; no runtime deps installed
  patterns:
    - "MADR-lite ADR format (Status, Context, Options Considered, Decision, Consequences, References)"
    - "ADR filename convention: NNN-<slug>.md zero-padded; immutable once Accepted; superseding ADRs replace, do not edit"
    - "Inline rationale in ADR Context (fresh-agent docs check D-39 must succeed without reading .planning/research)"
    - "Cross-ADR links use relative paths (./00N-...) only"
    - "Centralized OTel GenAI attribute name constants as the migration mitigation for spec drift"

key-files:
  created:
    - docs/decisions/001-charting-library.md
    - docs/decisions/002-vector-store.md
    - docs/decisions/003-embedding-provider.md
    - docs/decisions/004-trace-storage.md
    - docs/decisions/005-observability-strategy.md
    - docs/decisions/006-chunking-strategy.md
    - docs/decisions/007-reranking.md
    - docs/decisions/008-judge-prompts-thresholds.md
    - docs/decisions/009-auth-deployment-direction.md
    - docs/decisions/010-scope-trim.md
    - docs/decisions/README.md
  modified: []

key-decisions:
  - "ADR 001: Tremor v3 charting (~75% LoC reduction vs raw Recharts); Tailwind v3 pin reinforced"
  - "ADR 002: pgvector on the same Postgres 16 instance as the trace store; one Docker service for both"
  - "ADR 003: Voyage voyage-code-3 (1024-dim) primary + sentence-transformers nomic-embed-text-v1.5 (768-dim) fallback; embedding_model + embedding_model_version + indexed_at metadata mandate; startup assertion on mismatch"
  - "ADR 004: Postgres 16 + JSONB GIN-indexed; spans table partitioned by RANGE(started_at) on month boundaries; span_payloads JSONB side table"
  - "ADR 005: Custom tracer; OTel GenAI attribute names as Python constants; gen_ai.system DEPRECATED, use gen_ai.provider.name; no opentelemetry-sdk runtime dep"
  - "ADR 006: Markdown-header-aware chunker; defaults chunk_size=900, overlap=100, top_k=5; admin-tunable; warn against top_k > 8 (lost-in-the-middle)"
  - "ADR 007: No re-ranker in v1; ENABLE_RERANKER reserved for v2 V2-RANK-01"
  - "ADR 008: RAGAS-style judge prompts with XML-delimited untrusted content; Haiku pinned to dated snapshot (verify via client.models.list() pre-launch); judge_model recorded on every rag.eval span; faithfulness < 0.6 initial threshold; calibrate against ~30 hand-labeled traces in Phase 5 EVAL-06"
  - "ADR 009: ADR-only direction for v1.5 single-tenant API-key middleware; no v1 code, no v1 tests, no v1 env vars"
  - "ADR 010: Scope-trim plan triggered at >25% slip (>15h projected); cut order DEMO-02/03/04 -> DASH-04 -> FBCK-05 UI -> CLI-04 -> EVAL-06 30->15; reversible; requires PROJECT.md update on invocation"

patterns-established:
  - "MADR-lite template: 5 required sections (Status, Context, Options Considered, Decision, Consequences) + optional References; 50-100 LOC per ADR"
  - "Per-ADR mandatory clauses encoded as grep-verifiable phrases (e.g., 'PARTITION', 'span_payloads', 'gen_ai.provider.name', 'DEPRECATED', 'dated snapshot', '25%')"
  - "ADRs cite .planning/research/*.md by relative path (../../) but embed enough rationale inline to satisfy fresh-agent docs check (D-39)"
  - "Mandatory follow-ups encoded as TODO checkboxes (`- [ ] ...`) so downstream phases can grep for outstanding ADR action items"

requirements-completed: [DSGN-01, DSGN-09]

duration: ~30 min
completed: 2026-05-04
---

# Phase 1 Plan 01: ADR Authoring (001-010 + index) Summary

**10 MADR-lite ADRs codifying every GSD-OPEN-N resolution and the operational scope-trim playbook, plus a README index — the source of "why we built it this way" for every downstream phase.**

## Performance

- **Duration:** ~30 min
- **Started:** 2026-05-03T20:43:00Z
- **Completed:** 2026-05-03T20:48:00Z
- **Tasks:** 2 (per plan)
- **Files created:** 11 (10 ADRs + README index)
- **Files modified:** 0

## Accomplishments

- All 9 GSD-OPEN-N items from the foundation PRD §10 resolved as Accepted ADRs (001..009).
- DSGN-09 scope-trim playbook codified as ADR 010 with the exact cut order.
- decisions/README.md links all 10 ADRs with one-line summaries — the fresh-agent docs check (D-39, Wave 4) lands here first.
- Every per-ADR mandatory clause from the plan's `must_haves.truths` is present and grep-verifiable.
- All ADRs follow the MADR-lite template (5 required sections + References) and stay within the 50–100 LOC envelope (range: 46–57 lines).

## Task Commits

1. **Task 1: ADRs 001-005 (charting, vector store, embedding, trace store, observability)** — `439639e` (docs)
2. **Task 2: ADRs 006-010 (chunking, reranking, judge, auth, scope-trim) + decisions/README.md** — `194ccf6` (docs)

**Plan metadata commit:** to follow this SUMMARY.

## Files Created/Modified

- `docs/decisions/001-charting-library.md` — Tremor v3 charting decision (resolves GSD-OPEN-1)
- `docs/decisions/002-vector-store.md` — pgvector decision (resolves GSD-OPEN-2)
- `docs/decisions/003-embedding-provider.md` — Voyage voyage-code-3 + ST fallback decision; embedding_model metadata + startup assertion mandate (resolves GSD-OPEN-3)
- `docs/decisions/004-trace-storage.md` — Postgres+JSONB trace store; partitioned spans table; span_payloads side table (resolves GSD-OPEN-4)
- `docs/decisions/005-observability-strategy.md` — Custom tracer; OTel GenAI attribute names as constants; gen_ai.system DEPRECATED (resolves GSD-OPEN-5)
- `docs/decisions/006-chunking-strategy.md` — Markdown-header-aware chunker; 900/100/top_k=5 defaults (resolves GSD-OPEN-6)
- `docs/decisions/007-reranking.md` — No re-ranker in v1; ENABLE_RERANKER reserved (resolves GSD-OPEN-7)
- `docs/decisions/008-judge-prompts-thresholds.md` — RAGAS-style judge with XML-delimited untrusted content; Haiku dated snapshot (resolves GSD-OPEN-8)
- `docs/decisions/009-auth-deployment-direction.md` — ADR-only direction; no v1 code (resolves GSD-OPEN-9)
- `docs/decisions/010-scope-trim.md` — DSGN-09 scope-trim playbook with 25% trigger and 5-step cut order
- `docs/decisions/README.md` — ADR index with one-line summaries linking all 10 ADRs

## Decisions Made

None beyond the per-ADR decisions listed in `key-decisions` above. All 10 ADRs codify decisions that were already locked in `.planning/research/SUMMARY.md` §"GSD-OPEN-N Resolution Status" and the phase context (D-01..D-51). No discretionary judgments were made during authoring — the plan was followed exactly.

## Deviations from Plan

None — plan executed exactly as written. All per-ADR mandatory clauses (D-22, D-49, D-50, D-51, plus the D-37 cut-order tags) are present and grep-verifiable. No deviation rules triggered.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required for this design-only plan. Two follow-up checkboxes are recorded INSIDE the relevant ADRs (not deferred-items.md) for downstream phases:

- ADR 003: `[ ] Verify Voyage pricing at https://docs.voyageai.com/docs/pricing before INFRA-01 closes` — Phase 2 prereq.
- ADR 008: `[ ] Pin Haiku judge to a dated snapshot, verify exact ID via client.models.list() before going live` — Phase 5 EVAL-06 prereq.

## Next Phase Readiness

- DSGN-01 (9 GSD-OPEN-N items resolved as ADRs 001-009) is satisfied.
- DSGN-09 (scope-trim playbook as ADR 010) is satisfied.
- The fresh-agent docs check (Wave 4) will be able to answer Q1 ("what does the system do") from `decisions/README.md` ADR index.
- Ready for Plans 01-02 through 01-08 (architecture diagram, sequence diagram, trace schema, data model, API contract, wireframes, module deps + coverage set).
- No blockers for the remainder of Phase 1.

## Self-Check: PASSED

**Files verified to exist on disk:**
- FOUND: docs/decisions/001-charting-library.md
- FOUND: docs/decisions/002-vector-store.md
- FOUND: docs/decisions/003-embedding-provider.md
- FOUND: docs/decisions/004-trace-storage.md
- FOUND: docs/decisions/005-observability-strategy.md
- FOUND: docs/decisions/006-chunking-strategy.md
- FOUND: docs/decisions/007-reranking.md
- FOUND: docs/decisions/008-judge-prompts-thresholds.md
- FOUND: docs/decisions/009-auth-deployment-direction.md
- FOUND: docs/decisions/010-scope-trim.md
- FOUND: docs/decisions/README.md

**Commits verified to exist:**
- FOUND: 439639e (Task 1: ADRs 001-005)
- FOUND: 194ccf6 (Task 2: ADRs 006-010 + README index)

**Per-ADR mandatory-clause grep checks (all PASS):**
- ADR 001 contains "Tremor v3"
- ADR 002 contains "pgvector"
- ADR 003 contains "voyage-code-3", "embedding_model", "Verify Voyage"
- ADR 004 contains "PARTITION", "span_payloads"
- ADR 005 contains "gen_ai.provider.name", "DEPRECATED"
- ADR 006 contains "900"
- ADR 007 contains "ENABLE_RERANKER"
- ADR 008 contains "claude-haiku", "dated snapshot", "XML"
- ADR 009 contains "ADR-only"
- ADR 010 contains "25%", "DEMO-02", "DASH-04", "FBCK-05", "CLI-04", "EVAL-06"
- README contains "010-scope-trim" and 10 relative ADR links

---
*Phase: 01-research-design-artifacts*
*Completed: 2026-05-04*
