---
phase: 01-research-design-artifacts
plan: 03
subsystem: eval
tags: [eval, coverage, yaml, regression, design]

requires:
  - phase: research
    provides: Coverage Query Set Draft (12 verbatim YAML entries) in 01-RESEARCH.md §"Coverage Query Set Draft" lines ~666-768
  - phase: 01-01 (ADRs)
    provides: D-31..D-35 schema + canonical 12-section taxonomy locked in 01-CONTEXT.md
provides:
  - Proactive coverage regression query set at docs/eval/coverage_set.yaml — 12 hand-curated queries spanning all 12 canonical doc_sections (DSGN-10)
  - Canonical doc_section taxonomy strings (auth, models, messages, tools, batches, files, citations, vision, errors-and-rate-limits, prompt-caching, agent-sdk-overview, agent-sdk-tools) — Phase 3 chunker MUST use these exact strings
  - YAML schema contract for Phase 6 CLI-02 (eval/regression.py) — yaml.safe_load() consumer of this file
affects: [01-04 sequence diagram (none), 01-05 data model (regression_cases table schema must store doc_section + id from this file), 01-06 API contract (none direct), 01-07 wireframes (none direct), 01-08 verification (none direct), Phase 3 CORP-01/02 (chunker doc_section taxonomy MUST match these 12 strings — Pitfall F), Phase 5 EVAL-06 (calibrates expected_min_score and expected_chunk_keywords per query), Phase 6 CLI-02 (loads + asserts retrieval coverage per query)]

tech-stack:
  added: []  # design-only YAML; no runtime deps
  patterns:
    - "YAML list of mappings — top-level array; each entry is a mapping with 6 required fields"
    - "expected_chunk_keywords as inline YAML list (readable in any viewer; preserves provenance from research draft)"
    - "Header comment block citing requirement ID (DSGN-10) + decision IDs (D-31..D-35) + downstream consumer (Phase 6 CLI-02) + calibration owner (Phase 5 EVAL-06)"
    - "Verbatim copy from 01-RESEARCH.md draft — no phrasing refinements; preserves the audit trail from research → CONTEXT → PLAN → file"
    - "Zero-padded sequential IDs COV-01..COV-12 — stable identifiers for cross-phase references"

key-files:
  created:
    - docs/eval/coverage_set.yaml
  modified: []

key-decisions:
  - "Copied the 12 queries verbatim from 01-RESEARCH.md §'Coverage Query Set Draft' (lines 679-761) — the planner pre-drafted the YAML and the executor's job per the plan was strict transcription, not refinement. Zero phrasing changes."
  - "Created docs/eval/ directory in Phase 1 (per D-31 explicit override) even though /docs/eval/ is otherwise a Phase 6 directory — the coverage set is the contract Phase 6 CLI-02 consumes, so Phase 1 owns its authoring."
  - "All 12 expected_min_score values pinned to 0.6 placeholder — Phase 5 EVAL-06 owns calibration against ~30 hand-labeled traces; Phase 1 does not pre-calibrate."
  - "doc_section taxonomy uses kebab-case for multi-word values (errors-and-rate-limits, prompt-caching, agent-sdk-overview, agent-sdk-tools) — pinned exactly per D-33 and the contract_note in 01-03-PLAN.md so Phase 3 CORP-01/02 chunker can use the same strings without translation."
  - "Schema contract: 6 required fields per entry (id, query, doc_section, expected_chunk_keywords, expected_min_score, notes) — matches D-32 exactly; Phase 6 CLI-02 yaml.safe_load() will rely on this shape."

patterns-established:
  - "Phase 1 design artifacts that are direct contracts for future-phase code paths (this file → Phase 6 CLI-02; docs/api.md → Phase 3 schemas; trace-schema.md → Phase 4 tracer constants) live under /docs/ as the canonical source-of-truth — fresh agents and downstream phases read /docs/ before /tracer_ai/ or /.planning/."
  - "When research already drafted the deliverable verbatim, the executor's job is transcription with structural validation, not refinement — this preserves the audit trail and prevents drift between research, plan, and artifact."
  - "Programmatic structural validation (yaml.safe_load + assertions on cardinality, field presence, taxonomy set equality, ID set equality) is the gate, not human review of YAML indentation."

requirements-completed: [DSGN-10]

duration: ~6 min
completed: 2026-05-04
---

# Phase 1 Plan 03: Proactive Coverage Regression Query Set Summary

**Authored `docs/eval/coverage_set.yaml` — 12 hand-curated coverage queries (COV-01..COV-12) spanning all 12 canonical Claude API doc_sections (auth, models, messages, tools, batches, files, citations, vision, errors-and-rate-limits, prompt-caching, agent-sdk-overview, agent-sdk-tools), pinning the contract that Phase 3 CORP chunker and Phase 6 CLI-02 regression runner both consume.**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-05-04T02:14:00Z
- **Completed:** 2026-05-04T02:20:08Z
- **Tasks:** 1
- **Files created:** 1 (`docs/eval/coverage_set.yaml`, 104 LOC)

## Accomplishments

- Created `docs/eval/` directory (Phase 1 explicit override per D-31; otherwise a Phase 6 directory).
- Authored `docs/eval/coverage_set.yaml` with 12 entries (exceeds the DSGN-10 floor of 10) copied verbatim from `01-RESEARCH.md §"Coverage Query Set Draft"`.
- Pinned the 12-section canonical taxonomy as YAML strings — Phase 3 chunker contract is now machine-readable.
- Validated the file passes the executor's full structural assertion suite: 12 entries, all 6 required fields per entry, exact `doc_section` set equality with the D-33 12-string taxonomy, exact ID set equality with `{COV-01..COV-12}`.
- Header comment block in the YAML cites DSGN-10 + D-31..D-35 inline so a fresh agent reading only `/docs/eval/coverage_set.yaml` can trace the file's provenance.

## Task Commits

Each task was committed atomically:

1. **Task 1: Author docs/eval/coverage_set.yaml (12 queries, DSGN-10)** — `35aa281` (docs)

_Plan metadata commit will follow this SUMMARY._

## Files Created/Modified

- `docs/eval/coverage_set.yaml` (created, 104 LOC) — Proactive coverage regression query set: 12 hand-curated queries covering each major Claude API doc section, schema per D-32 (id, query, doc_section, expected_chunk_keywords, expected_min_score=0.6, notes). Header comment block cites DSGN-10 + D-31..D-35.

### The 12 doc_sections covered

| ID     | doc_section              | Source URL hint                            |
|--------|--------------------------|--------------------------------------------|
| COV-01 | auth                     | /api/getting-started auth section          |
| COV-02 | models                   | /docs/about-claude/models                  |
| COV-03 | messages                 | /api/messages basic prompt structure       |
| COV-04 | tools                    | /docs/agents-and-tools/tool-use            |
| COV-05 | batches                  | /docs/build-with-claude/batch-processing   |
| COV-06 | files                    | /docs/build-with-claude/files              |
| COV-07 | citations                | /docs/build-with-claude/citations          |
| COV-08 | vision                   | /docs/build-with-claude/vision             |
| COV-09 | errors-and-rate-limits   | /api/errors and /api/rate-limits           |
| COV-10 | prompt-caching           | /docs/build-with-claude/prompt-caching     |
| COV-11 | agent-sdk-overview       | /docs/claude-agent-sdk overview            |
| COV-12 | agent-sdk-tools          | /docs/claude-agent-sdk/mcp                 |

### Phrasing refinements vs. research draft

**None.** The plan instructed the executor to copy the 12 entries verbatim from `01-RESEARCH.md §"Coverage Query Set Draft"`. All 12 query strings, all 60 keyword entries (5 entries × 12 queries average — actually 4-5 keywords per entry), all 12 notes strings, and all 12 doc_section values match the research draft exactly. Zero refinements.

## Decisions Made

- **Verbatim transcription** over executor refinement — the planner's draft was the contract; preserving exact phrasing protects the research → plan → artifact audit trail and prevents silent drift.
- **`expected_min_score: 0.6` pinned across all 12 entries** — calibration is explicitly Phase 5 EVAL-06's job; Phase 1 sets a uniform placeholder.
- **Inline YAML lists for `expected_chunk_keywords`** — `["...", "...", ...]` flow style is more readable for a 4-5 element keyword list than block style `- "..."` per element across 4-5 lines, and it matches the research draft format exactly.

## Deviations from Plan

None — plan executed exactly as written.

The plan was a single-task strict-transcription job with a programmatic verify step. No bugs to auto-fix (Rule 1), no missing critical functionality (Rule 2), no blocking issues (Rule 3), no architectural decisions (Rule 4). The verify-step Python assertions all passed on the first run.

**Total deviations:** 0
**Impact on plan:** N/A — clean execution.

## Issues Encountered

None.

## Self-Check

- File `docs/eval/coverage_set.yaml`: **FOUND** (104 LOC, parses as YAML list of 12 mappings).
- Commit `35aa281`: **FOUND** in `git log --oneline` as `docs(01-03): author docs/eval/coverage_set.yaml (DSGN-10)`.
- Programmatic validation: **PASSED** — `python -c "import yaml; data=yaml.safe_load(open('docs/eval/coverage_set.yaml')); ..."` reported `YAML coverage set valid: 12 entries, all 12 doc_sections present, IDs COV-01..COV-12`.
- Acceptance criteria from PLAN.md: all 6 satisfied (file exists at exact path; 12 mappings; all 6 fields per entry; doc_section set matches D-33 taxonomy exactly; ID set is {COV-01..COV-12}; header cites DSGN-10 + D-31..D-35).

## Self-Check: PASSED

## User Setup Required

None — no external service configuration required. (No USER-SETUP.md generated.)

## Next Phase Readiness

- Phase 1 progress: 3/8 plans complete (DSGN-01, DSGN-02, DSGN-08, DSGN-09, DSGN-10 satisfied; DSGN-03..DSGN-07 remain in Plans 01-04..01-07; Plan 01-08 is the fresh-agent docs verification).
- Resume file: `.planning/phases/01-research-design-artifacts/01-04-PLAN.md` (next plan in the phase — chat-request sequence diagram, DSGN-03).
- **Contract pinned for Phase 3:** the 12 doc_section strings in this file are the canonical chunker taxonomy. Phase 3 CORP-01/02 plan-phase agent must reference this file when authoring the chunker config (Pitfall F mitigation).
- **Contract pinned for Phase 6:** Phase 6 CLI-02 (`eval/regression.py`) loads this file via `yaml.safe_load()` and consumes the 6-field schema. Phase 5 EVAL-06 may rewrite `expected_min_score` and `expected_chunk_keywords` during calibration; the 6-field shape and the 12 IDs are stable.
- **No blockers introduced.** Plan 01-04 (sequence diagram) can begin immediately.

---
*Phase: 01-research-design-artifacts*
*Completed: 2026-05-04*
