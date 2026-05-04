---
phase: 01-research-design-artifacts
plan: 04
subsystem: tracer
tags: [trace, schema, otel, gen_ai, design, observability]

requires:
  - phase: research
    provides: Trace Schema Spec template + verbatim Python constants block + per-span attribute draft table in 01-RESEARCH.md §"Per-Artifact Authoring Guide › Artifact 5" (lines ~243-298)
  - phase: 01-01 (ADRs Wave 1)
    provides: docs/decisions/005-observability-strategy.md — ADR codifying OTel-naming-only / no opentelemetry-sdk runtime / gen_ai.system DEPRECATED / gen_ai.provider.name = "anthropic"
  - phase: 01-CONTEXT
    provides: D-19..D-22 (per-span order, per-section structure, central constants block, OTel deprecation note) + D-47 (payload-storage convention) + D-50 (dated-snapshot judge model) + D-51 (spans table partition by month — referenced for cross-link)
provides:
  - Trace schema specification at docs/trace-schema.md (DSGN-04) — every span name, every attribute, every type, every example payload, every payload-table reference
  - Python attribute-constants block (copy-paste-ready into tracer_ai/tracer/span.py) — IS the contract Phase 4 TRCR-01 imports
  - OTel deprecation note (gen_ai.system) and the central-constants migration mitigation, encoded permanently in /docs/
  - Payload storage convention warning — full prompts/responses MUST go to span_payloads JSONB, not span attributes
affects: [01-05 data model (span_payloads JSONB column referenced here MUST exist in the ERD), 01-06 API contract (POST /chat response includes trace_id from rag.request; POST /feedback writes feedback.trace_id from this schema), 01-08 verification (fresh-agent docs check Q3 "trace schema — list spans, attributes, where payloads live" answerable from this file alone), Phase 4 TRCR-01 (imports the Python constants block verbatim into tracer_ai/tracer/span.py), Phase 4 TRCR-02/03 (per-span attribute lists are the contract for span.py emission helpers + the Postgres exporter), Phase 5 EVAL-01..06 (rag.eval span attributes + judge model dated-snapshot + judge_prompt_version are the eval contract), Phase 5 FBCK-01..05 (feedback.user event-style record + reserved feedback.diagnosis_tag column for FBCK-05)]

tech-stack:
  added: []  # design-only markdown; no runtime deps in Phase 1
  patterns:
    - "OTel GenAI attribute names as Python constants centralized in one file (mitigation for Development-stability spec drift)"
    - "Payload split: small typed metadata on spans.attrs (GIN-indexed JSONB); unbounded text on span_payloads.payload (1:N FK; not GIN-indexed; fetched only on detail drill-in)"
    - "Dated-snapshot model pinning in trace attributes (gen_ai.request.model = 'claude-sonnet-4-5-20250929'; rag.eval.judge_model = 'claude-haiku-4-5-20251001') — never aliases (Pitfall #4)"
    - "Versioned prompt template ID (rag.prompt_template.id, rag.eval.judge_prompt_version) — makes drift correlatable to template version"
    - "Event-style records vs duration spans — feedback.user has no started_at/ended_at; correlated to trace via feedback.trace_id"
    - "Async eval span (rag.eval) attaches to root via OTel context snapshot captured BEFORE root.end() — mitigation for Pitfall #1 documented in the rag.eval section purpose paragraph"

key-files:
  created:
    - docs/trace-schema.md
  modified: []

key-decisions:
  - "Used the verbatim Python constants block from 01-RESEARCH.md lines 258-287 — this preserves the audit trail (research → CONTEXT → PLAN → file) and ensures Phase 4 TRCR-01 can copy-paste without translation. Block uses RAG_RETRIEVED_CHUNK_IDS (not the prompt's abbreviated RAG_RETRIEVED_CHUNKS) — the verbatim research block IS the contract per the PLAN's explicit lines 86-114 mandate."
  - "Per-span H2 headings written WITHOUT backticks (## rag.request, not ## `rag.request`) — the plan's verify automation greps `^## $s` literally, so unbacked headings are required for the contract to pass. The semantic clarity (it's a span name) is preserved by the section's content."
  - "Payload Storage Convention written as a `> **Warning**` callout (Markdown blockquote) — visually distinct, GitHub-renders correctly, and re-reads as load-bearing. Anti-Pattern #2 from ARCHITECTURE.md is the source; D-47 is the local decision ID."
  - "rag.eval section purpose paragraph encodes the OTel context-snapshot mitigation (Pitfall #1) inline — operators reading only this file learn WHY the eval span attaches as a child rather than orphaning, without needing to read the sequence diagram."
  - "Cross-References section uses relative links (./decisions/005-observability-strategy.md, ./data-model.md, etc.) — the file lives at docs/trace-schema.md so a fresh agent navigating the docs/ tree never breaks a link by relocating."
  - "Reserved feedback.diagnosis_tag attribute documented but marked 'no (Phase 5 FBCK-05)' — the schema column is allocated in Phase 1 (per D-13's general 'capture intent without implementing' pattern adapted here); the UI to populate it is Phase 5. Allowed values enumerated inline."

patterns-established:
  - "Phase 1 design artifacts that are direct contracts for future-phase code paths (this file → Phase 4 TRCR-01..03; docs/eval/coverage_set.yaml → Phase 6 CLI-02; docs/api.md → Phase 3 schemas) live under /docs/ as the canonical source-of-truth — fresh agents and downstream phases read /docs/ before /tracer_ai/ or /.planning/."
  - "When a design artifact's content becomes runtime code (the Python constants block), embed the runtime form (fenced ```python block) inside the markdown — not pseudocode, not a description — so downstream consumers copy-paste, not retype. Drift between spec and code is a class of bug eliminated."
  - "Per-span attribute tables use a fixed 5-column shape (name | type | required | OTel status | example) — uniform shape lets reviewers scan quickly across spans and lets future automated validation grep for the column header."
  - "Heading conventions matter for verify-automation contracts: when a downstream grep is part of the plan's <verify> block, headings MUST match the grep pattern literally — write the headings to satisfy the contract, then add inline backticks within the prose where typographic distinction is desirable."

requirements-completed: [DSGN-04]

duration: ~12 min
completed: 2026-05-04
---

# Phase 1 Plan 04: Trace Schema Specification Summary

**Authored docs/trace-schema.md (296 LOC) — central Python attribute-constants block (copy-paste-ready into tracer_ai/tracer/span.py for Phase 4 TRCR-01) plus 6 fully-specified span sections (rag.request, rag.retrieve, rag.prompt_assemble, rag.llm_call, rag.eval, feedback.user) with OTel deprecation note (gen_ai.system DEPRECATED; gen_ai.provider.name = "anthropic" is the live name) and payload-storage convention warning (full prompts/responses MUST go to span_payloads JSONB, not span attributes).**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-05-04T02:25:00Z (approx)
- **Completed:** 2026-05-04T02:37:00Z (approx)
- **Tasks:** 1
- **Files created:** 1 (`docs/trace-schema.md`, 296 LOC)
- **Files modified:** 0

## Accomplishments

- Created `docs/trace-schema.md` (296 LOC) — the canonical trace schema specification. Within the planned ~250-350 LOC target.
- Embedded the verbatim Python constants block (24 named constants spanning the OTel `gen_ai.*` namespace and the custom `rag.*` namespace) — copy-paste-ready into `tracer_ai/tracer/span.py` in Phase 4 TRCR-01.
- Encoded the OTel deprecation note (D-22) permanently in /docs/: `gen_ai.system` is DEPRECATED in the OTel GenAI spec; `gen_ai.provider.name` (= "anthropic") is the live name. The constant `# GEN_AI_SYSTEM = "gen_ai.system"` is commented out with a `# DEPRECATED; do not use` note in the Python block — making accidental re-introduction visible at code-review time.
- Encoded the payload storage convention (D-47) as a `> **Warning**` blockquote: full prompts/responses MUST go to the `span_payloads` JSONB side table (referenced by `span_id`); span attributes hold only typed metadata. Cited Anti-Pattern #2 from ARCHITECTURE.md.
- Authored 6 span sections in D-19 order — `rag.request`, `rag.retrieve`, `rag.prompt_assemble`, `rag.llm_call`, `rag.eval`, `feedback.user` — each with: one-line purpose, 5-column attribute table (name | type | required | OTel status | example), JSON example payload, and payload-table reference.
- Pinned dated-snapshot model IDs in examples (D-50): `gen_ai.request.model = "claude-sonnet-4-5-20250929"` on rag.llm_call; `rag.eval.judge_model = "claude-haiku-4-5-20251001"` on rag.eval. Inline rationale cites Pitfall #4 (alias drift breaks faithfulness baselines).
- Documented the Phase 5 FBCK-05 reservation: `feedback.diagnosis_tag` is allocated in the schema but marked `no (Phase 5 FBCK-05)` — schema column lives now, UI defers.
- Added Cross-References section linking docs/architecture.md, docs/sequence-diagrams.md (Plan 01-05/06 deliverable), docs/data-model.md (Plan 01-05 deliverable), docs/decisions/005-observability-strategy.md, docs/module-deps.md, and ARCHITECTURE.md research file by section anchor.

## Task Commits

Each task was committed atomically:

1. **Task 1: Author docs/trace-schema.md (DSGN-04, full spec with 6 spans + Python constants block)** — `d6d91dd` (docs)

_Plan metadata commit will follow this SUMMARY._

## Files Created/Modified

- `docs/trace-schema.md` (created, 296 LOC) — Trace schema specification. Sections: Overview / OTel Status Disclaimer / Attribute Constants / Payload Storage Convention / 6 per-span sections (rag.request, rag.retrieve, rag.prompt_assemble, rag.llm_call, rag.eval, feedback.user) / Cross-References. Python constants block at lines ~22-49 is the load-bearing contract for Phase 4 TRCR-01.

### The 6 spans documented (D-19 order)

| Order | Span | Lifetime | Purpose | Payload to span_payloads? |
|-------|------|----------|---------|---------------------------|
| 1 | rag.request | sync (root) | Trace root; one per POST /chat | no |
| 2 | rag.retrieve | sync (child of root) | Embed query + pgvector top-k | yes (full chunk text + scores) |
| 3 | rag.prompt_assemble | sync (child of root) | Templating: chunks + query + system into final prompt | yes (full assembled prompt) |
| 4 | rag.llm_call | sync (child of root) | Anthropic Messages API call | yes (full LLM response) |
| 5 | rag.eval | async (child of root via context snapshot) | Haiku judge: faithfulness + relevance | yes (full judge prompt + response) |
| 6 | feedback.user | event (not a duration span) | User thumbs-up/down correlated via feedback.trace_id | no |

### Verbatim mandates encoded in the file

- **D-21 (central constants):** Python block at top with all `gen_ai.*` and `rag.*` names — `GEN_AI_PROVIDER_NAME = "gen_ai.provider.name"`, `RAG_EVAL_FAITHFULNESS = "rag.eval.faithfulness"`, etc. Note inline: "These constants are imported into `tracer_ai/tracer/span.py` in Phase 4 TRCR-01."
- **D-22 (OTel deprecation):** `## OTel Status Disclaimer` section — `gen_ai.system` DEPRECATED; `gen_ai.provider.name` is the live name; mitigation = central constants file.
- **D-47 (payload storage):** `## Payload Storage Convention` section as `> **Warning**` callout — full prompts/responses to `span_payloads` JSONB; not span attributes; cites Anti-Pattern #2.
- **D-50 (dated snapshot judge):** `rag.eval.judge_model = "claude-haiku-4-5-20251001"` in examples; inline rationale.

## Decisions Made

- **Verbatim Python constants block from 01-RESEARCH.md lines 258-287** — preserves the research → CONTEXT → PLAN → file audit trail; Phase 4 TRCR-01 copy-pastes without translation.
- **Per-span H2 headings without backticks** (`## rag.request`, not `` ## `rag.request` ``) — required by the plan's verify automation grep pattern `^## $s`. The semantic clarity is preserved by the section content. Documented in patterns-established because future plans with verify-grep contracts need the same discipline.
- **Payload Storage Convention as Markdown blockquote `> **Warning**`** — visually distinct in GitHub render and reads as load-bearing.
- **`feedback.diagnosis_tag` attribute reserved but not yet populated** — schema column allocated in Phase 1; UI is Phase 5 FBCK-05. Pattern adapted from D-13 (capture intent without implementing).
- **Cross-References section uses relative links** — robust to docs/ tree relocation.
- **Inline OTel context-snapshot rationale in rag.eval purpose paragraph** — operators reading only this file understand WHY rag.eval attaches as a child rather than orphaning; the sequence diagram (Plan 01-05/06) is the visual companion, not the only source.

## Deviations from Plan

None — plan executed exactly as written.

The plan was a single-task spec-authoring job with a programmatic verify step. The verify-step grep assertions all pass (see Self-Check below). One minor mid-execution correction was needed and was NOT a deviation: the initial draft used backticked H2 headings (`` ## `rag.request` ``) for typographic clarity, but the plan's `<verify>` block greps `^## rag.request` literally. The headings were updated to plain (`## rag.request`) before commit so the verify automation passes. This is satisfying the plan's explicit verify contract, not a Rule 1-4 deviation.

**Total deviations:** 0
**Impact on plan:** N/A — clean execution.

## Issues Encountered

None — single mid-execution heading-format correction was a contract-conformance fix, not a problem.

## Self-Check

- File `docs/trace-schema.md`: **FOUND** (296 LOC; matches the ~250-350 LOC target).
- Commit `d6d91dd`: **FOUND** in `git log --oneline` as `docs(01-04): author docs/trace-schema.md (DSGN-04)`.
- Plan's `<verify>` automation: **PASSED** — all 13 grep assertions succeeded:
  - `^# Trace Schema Specification` h1 present
  - `GEN_AI_PROVIDER_NAME = "gen_ai.provider.name"` constant present
  - `gen_ai.system` AND `DEPRECATED` both present
  - `span_payloads` present (D-47 payload-storage convention encoded)
  - `rag.eval.faithfulness` and `rag.eval.relevance` constants present
  - `rag.retrieval.score.mean` and `rag.prompt_template.id` constants present
  - All 6 `## <span_name>` headings present in correct names
  - `claude-haiku` present (judge model dated snapshot)
  - `005-observability-strategy` cross-reference present
- Acceptance criteria from PLAN.md: all 10 satisfied. Success-criteria checklist from the prompt: all satisfied (the abbreviated `RAG_RETRIEVED_CHUNKS` in the prompt's checklist is satisfied by `RAG_RETRIEVED_CHUNK_IDS = "rag.retrieved_chunk_ids"` in the verbatim research-mandated block; the PLAN's `<action>` block 86-114 explicitly uses the `_IDS` form, which is the contract).

## Self-Check: PASSED

## User Setup Required

None — no external service configuration required. (No USER-SETUP.md generated.)

## Next Phase Readiness

- Phase 1 progress: 4/8 plans complete (DSGN-01, DSGN-02, DSGN-04, DSGN-08, DSGN-09, DSGN-10 satisfied; DSGN-03 sequence diagram + DSGN-05 data model + DSGN-06 API contract + DSGN-07 wireframes remain in Plans 01-05..01-07; Plan 01-08 is the fresh-agent docs verification gate).
- Resume file: `.planning/phases/01-research-design-artifacts/01-05-PLAN.md` (next plan in the phase — data model / ERD, DSGN-05).
- **Contract pinned for Phase 4 TRCR-01:** the Python constants block in `docs/trace-schema.md` (lines ~22-49) is the verbatim source `tracer_ai/tracer/span.py` will import. No translation, no rephrasing — copy-paste contract.
- **Contract pinned for Phase 4 TRCR-02/03:** the per-span attribute tables are the contract for the span emission helpers (`tracer/context.py`) and the Postgres exporter (`tracer/exporters/postgres.py`). The 5-column shape (name | type | required | OTel status | example) is the schema doc.
- **Contract pinned for Phase 5 EVAL-01..06:** the `rag.eval` section's required attributes (`rag.eval.faithfulness`, `rag.eval.relevance`, `rag.eval.judge_model`, `rag.eval.judge_prompt_version`, `rag.eval.judge_cost_usd`) are the eval contract. Dated-snapshot model pinning is mandated; calibration in EVAL-06 may iterate `judge_prompt_version` but the attribute name is stable.
- **Contract pinned for Phase 5 FBCK-01..05:** the `feedback.user` section locks the event-style record shape and reserves `feedback.diagnosis_tag` for FBCK-05; allowed values enumerated.
- **No blockers introduced.** Plan 01-05 (data model / ERD) can begin immediately; the `span_payloads` JSONB table the data model must produce is referenced from this trace-schema spec.

---
*Phase: 01-research-design-artifacts*
*Completed: 2026-05-04*
