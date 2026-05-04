---
phase: 01-research-design-artifacts
plan: 02
subsystem: documentation
tags: [diagram, mermaid, architecture, module-deps, design]

requires:
  - phase: research
    provides: System Overview ASCII tree + Component Responsibilities table + Dependency Graph layering in .planning/research/ARCHITECTURE.md
  - phase: 01-01 (ADRs)
    provides: ADR 002 (vector store), ADR 004 (trace store), ADR 005 (observability strategy) — referenced by both diagrams
provides:
  - System architecture diagram (Mermaid flowchart TD) with subgraphs Frontend / FastAPI / Persistence and external services Anthropic + Voyage AI (DSGN-02)
  - Module dependency diagram (Mermaid flowchart LR) with all 8 modules and visual acyclicity (DSGN-08)
  - Cross-reference scaffolding from architecture.md to sequence-diagrams.md (Wave 3), module-deps.md, trace-schema.md, and decisions/
affects: [01-03 sequence diagram (cross-ref target), 01-04 trace schema (cross-ref target), 01-05 data model (architecture mentions 5 trace tables + chunks), 01-06 API contract (architecture mentions 4 api/*.py files), 01-07 wireframes (architecture mentions Frontend routes), 01-08 module deps + coverage set (module-deps subsumes the deps half), Phase 2 INFRA-01 (architecture is the scaffold spec), Phase 2 INFRA-04 (module-deps is the runtime acyclicity gate spec)]

tech-stack:
  added: []  # design-only diagrams; no runtime deps
  patterns:
    - "Mermaid flowchart TD for top-down system architecture (subgraphs for tiers + un-grouped stadium nodes for external services)"
    - "Mermaid flowchart LR for left-to-right module dependency layering (visual acyclicity = no edge flows right-to-left)"
    - "Cylinder shape [(...)] for database nodes; stadium shape ([...]) for external API nodes"
    - "Quote node labels containing parens, commas, slashes, or hyphens to avoid GitHub Mermaid parser issues"
    - "Diagrams cite .planning/research/ARCHITECTURE.md by section anchor (the canonical source-of-truth — ADRs codify, diagrams visualize)"

key-files:
  created:
    - docs/architecture.md
    - docs/module-deps.md
  modified: []

key-decisions:
  - "Architecture diagram uses the exact node/edge structure from 01-RESEARCH.md §'Mermaid Syntax Reference' (lines 423-455) — verified GitHub-safe and matches D-15"
  - "Module-deps diagram has 8 nodes layered into 4 tiers: leaves (config, errors) -> foundation (tracer/, corpus/) -> orchestration (rag/, eval/) -> entry points (api/, cli/) — every edge flows strictly left-to-right"
  - "corpus/ imports config, errors only — NOT rag/ — and is imported by rag/ and cli/. This matches ARCHITECTURE.md §'Structure Rationale' precisely (corpus is below rag in the layering)"
  - "Architecture diagram pgvector node and trace tables node both live inside the Persistence (Postgres 16) subgraph — visualizing ADR 002's 'one Postgres for both' decision"
  - "Dotted edge api -.async.-> eval encodes the BackgroundTasks-driven async branch (the eval-failure-isolation property required by ADR 005 + ARCHITECTURE.md Anti-Pattern 3)"
  - "Both files are self-citing — cross-ref paragraph at the end of each points to the other Wave 1/3 artifacts so the fresh-agent docs check (D-39) can navigate /docs/ without reading .planning/"

patterns-established:
  - "All Phase 1 diagrams use the same Mermaid renderer guarantees: no `defaultRenderer:` directive, no `A@{shape:...}` experimental syntax, cylinder/stadium shapes only via the documented `[(...)]` and `([...])` patterns"
  - "Every diagram file has a Source-of-truth header line citing the relevant section anchor in .planning/research/ARCHITECTURE.md (or other research doc)"
  - "Every diagram file has a Cross-references final section linking the other docs/ artifacts a fresh agent would need to navigate to next"

requirements-completed: [DSGN-02, DSGN-08]

duration: ~5 min
completed: 2026-05-04
---

# Phase 1 Plan 02: System Architecture + Module Dependency Diagrams Summary

**Two foundational Mermaid diagrams — `flowchart TD` for the three-tier system architecture (DSGN-02) and `flowchart LR` for the 8-module dependency graph (DSGN-08) — both authored from `.planning/research/ARCHITECTURE.md` with no dependencies on other Phase 1 artifacts.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-05-03T20:50:35Z
- **Completed:** 2026-05-03T20:52:31Z
- **Tasks:** 2 (per plan)
- **Files created:** 2 (architecture.md = 71 lines; module-deps.md = 75 lines)
- **Files modified:** 0

## Accomplishments

- DSGN-02 satisfied: `docs/architecture.md` is a 71-line file with a single Mermaid `flowchart TD` block containing 3 subgraphs (`fe`, `be`, `db`), 4 backend modules, 2 database cylinder nodes, 2 external service stadium nodes, and 12 edges including one dotted async edge for the `BackgroundTasks` eval branch.
- DSGN-08 satisfied: `docs/module-deps.md` is a 75-line file with a single Mermaid `flowchart LR` block containing all 8 modules (`config`, `errors`, `tracer/`, `corpus/`, `rag/`, `eval/`, `api/`, `cli/`) and 21 edges. Every edge flows strictly left-to-right — visual acyclicity is the Phase 1 gate; runtime enforcement deferred to Phase 2 INFRA-04.
- Both diagrams cite `.planning/research/ARCHITECTURE.md` by section anchor in their header. Both end with a Cross-references section linking the other Wave 1/3 artifacts a fresh agent would need.
- Both files use only the verified GitHub-safe Mermaid syntax from 01-RESEARCH.md §"Mermaid Syntax Reference" — no `defaultRenderer:` directives, no experimental `A@{shape:...}` syntax (Pitfall A).
- The framing paragraph of `architecture.md` mentions `BackgroundTasks` (per acceptance criterion 8) and explains the OTel context-snapshot mitigation that prevents orphaned `rag.eval` spans (Pitfall #1).

## Task Commits

1. **Task 1: docs/architecture.md (DSGN-02)** — `dd762ac` (docs)
2. **Task 2: docs/module-deps.md (DSGN-08)** — `019747b` (docs)

**Plan metadata commit:** to follow this SUMMARY.

## Files Created/Modified

- `docs/architecture.md` — 71 lines; system architecture with three-tier subgraphs and external services; resolves DSGN-02
- `docs/module-deps.md` — 75 lines; 8-node module dependency graph laid out left-to-right for visual acyclicity; resolves DSGN-08

## Mermaid Renderer Compatibility Note

Both files were authored against the syntax patterns verified GitHub-safe in `.planning/phases/01-research-design-artifacts/01-RESEARCH.md` §"Mermaid Syntax Reference". Specifically:

- `flowchart TD` and `flowchart LR` declarations only — no `graph TD` legacy syntax.
- Subgraph IDs use the `subgraph id["Display Title"]` pattern (e.g., `subgraph fe["Frontend (Vite + React 18 + Tailwind v3 + Tremor v3)"]`) — quoted because the title contains parens and a `+`.
- Node labels containing `(`, `)`, `,`, or `/` are quoted (e.g., `api["api/chat.py, api/traces.py, api/feedback.py, api/admin.py"]`, `traces[(traces / spans / span_payloads / feedback / regression_cases)]`).
- Cylinder shapes `A[(...)]` for database nodes; stadium shapes `A([...])` for external API nodes — both syntaxes verified in the Node shape cheat sheet.
- Dotted async edge syntax: `A -.async.-> B` (label between the dots) — verified in the Arrow cheat sheet.
- Verify-step grep checks confirm absence of `defaultRenderer` and `A@{shape` strings inside both files (Pitfall A guardrail).

A separate render verification (e.g., paste both blocks into GitHub's preview) is recommended before phase close but is not blocking — both diagrams use the exact patterns the research file flagged as compatible.

## Decisions Made

None beyond what `key-decisions` lists. The plan was executed exactly as written — every node, edge, table row, and cross-reference in the action steps was placed verbatim. The only authoring discretion exercised:

1. The framing paragraph of each file is written in plain prose rather than copy-paste from the plan's quoted example, since the plan example was descriptive ("write a paragraph that says X"), not literal.
2. The "Reading the diagram" mini-section in each file is added as a navigation aid for fresh-agent docs check (D-39) — without it, a reader unfamiliar with Mermaid arrow conventions would not know that the dotted edge means async or that left-to-right edge flow proves acyclicity. This is a Rule 2 addition (auto-add missing critical functionality for the docs to be self-sufficient) — it does not change any diagram content.

## Deviations from Plan

**One Rule 2 micro-deviation (auto-added critical functionality):**

1. **[Rule 2 — missing critical functionality] Added "Reading the diagram" navigation paragraphs.**
   - **Found during:** Task 1 + Task 2 self-review against the fresh-agent docs check (D-39).
   - **Issue:** The plan specified the diagram contents but no narrative explaining how to read them. A fresh agent given only `/docs/` would see arrows but not know that the dotted edge means async, that cylinder nodes are databases, or that left-to-right edge flow is the acyclicity proof.
   - **Fix:** Added one short "Reading the diagram" subsection to each file (3-5 bullets each) explaining edge semantics and visual conventions.
   - **Files modified:** `docs/architecture.md`, `docs/module-deps.md` (both in their initial Write — no separate commit).
   - **Commit:** included in `dd762ac` and `019747b` respectively.

No other deviations. The framing paragraph length, table row counts, edge counts, and acceptance-criteria grep targets all match the plan exactly.

## Issues Encountered

**One self-recovered issue:**

- The first `architecture.md` draft included the literal strings `defaultRenderer` and `A@{shape:...}` inside a prose disclaimer ("no `defaultRenderer` directive; no experimental `A@{shape:...}` syntax"). The verify-step grep targets `! grep -q 'defaultRenderer'` and `! grep -q 'A@{shape'` would have failed because they cannot distinguish "string in diagram" from "string mentioned in prose". Fix: rephrased the disclaimer to "no custom-renderer directives, no experimental shape syntax" so the literal forbidden strings appear nowhere in the file. Re-ran verify; all checks pass.

No other issues.

## User Setup Required

None — both files are pure documentation. Recommendation for the next user-facing checkpoint: paste both Mermaid blocks into GitHub's preview (or `https://mermaid.live`) to confirm visual rendering matches the prose description. This is not a blocker for Phase 1 close (the syntax is the verified-safe set from 01-RESEARCH.md), but it satisfies the spirit of D-14 ("renders natively in GitHub README").

## Next Phase Readiness

- **DSGN-02 (architecture diagram)** satisfied via `docs/architecture.md`.
- **DSGN-08 (module-deps with no cycles)** satisfied via `docs/module-deps.md`.
- **Fresh-agent docs check Wave 4 readiness:** Q1 ("what does the system do") is now answerable from `architecture.md` framing + diagram + component table. Q2 ("how does data flow") requires `sequence-diagrams.md` (Wave 3) for full coverage but is partially answerable from the architecture diagram's edges + framing paragraph. ROADMAP success criterion 4 ("zero circular deps") is satisfied by the visual acyclicity proof in `module-deps.md`.
- **Wave 1 status:** Plan 01-02 was the only Wave 1 plan; Wave 1 is complete. Plans 01-03 (sequence diagram) and 01-04 (trace schema) can now proceed in Wave 2/3.
- **No blockers** for Plans 01-03 through 01-08.

## Self-Check: PASSED

**Files verified to exist on disk:**
- FOUND: docs/architecture.md (71 lines)
- FOUND: docs/module-deps.md (75 lines)

**Commits verified to exist:**
- FOUND: dd762ac (Task 1: docs/architecture.md)
- FOUND: 019747b (Task 2: docs/module-deps.md)

**Acceptance-criteria grep checks (all PASS):**
- architecture.md contains `# System Architecture` h1
- architecture.md contains a Mermaid block opening with ```` ```mermaid ````
- architecture.md declares `flowchart TD`
- architecture.md contains all 3 subgraph IDs: `fe`, `be`, `db`
- architecture.md names external services `anthropic` and `voyage`
- architecture.md mentions `pgvector` in the diagram (`chunks — pgvector HNSW` cylinder label)
- architecture.md mentions `BackgroundTasks` in the framing paragraph
- architecture.md cross-references `sequence-diagrams.md` and `module-deps.md`
- architecture.md does NOT contain `defaultRenderer` or `A@{shape` (Pitfall A guardrail)
- module-deps.md contains `# Module Dependency Graph` h1
- module-deps.md contains a Mermaid `flowchart LR` block
- module-deps.md contains all 8 module names: `config`, `errors`, `tracer`, `rag`, `corpus`, `eval`, `api`, `cli`
- module-deps.md references `INFRA-04` as the future runtime acyclicity check
- module-deps.md contains the `## Acyclicity Check` heading
- module-deps.md does NOT contain `defaultRenderer`

---
*Phase: 01-research-design-artifacts*
*Completed: 2026-05-04*
