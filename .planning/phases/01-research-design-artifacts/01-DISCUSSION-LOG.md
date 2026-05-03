# Phase 1: Research & Design Artifacts - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in `01-CONTEXT.md` — this log preserves the alternatives considered.

**Date:** 2026-05-04
**Phase:** 1-Research & Design Artifacts
**Mode:** `--auto` — recommended option auto-selected for every gray area; no AskUserQuestion prompts issued.
**Areas discussed:** ADR template & index, Diagram tooling, Trace schema spec format, API contract format, Wireframes format, Coverage query set format, Voyage AI pricing handling, Risk + scope-trim plan, Verification gate, Embedded anti-patterns

---

## ADR Template & Index

| Option | Description | Selected |
|--------|-------------|----------|
| MADR-lite (Nygard) | Status / Context / Options Considered / Decision / Consequences. ~1 page. | ✓ |
| Full MADR | Adds Problem Statement, Decision Drivers, Pros/Cons per option, Validation. Heavier. | |
| Custom one-liner table | Single ADR doc with rows per decision. | |

**[auto] Selected:** MADR-lite (recommended default)
**Why:** Each ADR codifies an already-resolved research item; full MADR sections would duplicate `.planning/research/`. One-liner table loses the "Options Considered" + "Consequences" structure that future plan-phase agents need to re-evaluate.

---

## ADR Numbering & Index

| Option | Description | Selected |
|--------|-------------|----------|
| 001-009 = GSD-OPEN-1..9; 010 = scope-trim | One ADR per open question + scope-trim ADR. Index README links them. | ✓ |
| Single ADR with sub-sections | One file `decisions/architecture-decisions.md` with H2 per decision. | |
| Topic-grouped (e.g., 001-storage covers vector + trace store) | Fewer files, mixes concerns. | |

**[auto] Selected:** 001-009 = GSD-OPEN-N + 010 = scope-trim
**Why:** REQUIREMENTS.md DSGN-01 explicitly says "one ADR per item, with context/options/decision/consequences". 1:1 mapping eliminates ambiguity for the verification gate.

---

## Diagram Tooling

| Option | Description | Selected |
|--------|-------------|----------|
| Mermaid in markdown | All diagrams as fenced ```mermaid blocks. Renders in GitHub, no tool install. | ✓ |
| Excalidraw exports (.excalidraw + PNG) | Hand-drawn aesthetic; binary file friction. | |
| PlantUML | More expressive but requires `java -jar plantuml.jar`. | |

**[auto] Selected:** Mermaid (recommended; locked by REQUIREMENTS.md DSGN-02..05)
**Why:** Already locked by requirements; no choice to make.

---

## Sequence Diagram Scope

| Option | Description | Selected |
|--------|-------------|----------|
| One combined diagram (sync + async) | Single `sequenceDiagram` showing /chat path AND BackgroundTasks eval branch with `Note over` callouts. | ✓ |
| Two separate diagrams | sync-chat-flow.md + async-eval-flow.md. | |

**[auto] Selected:** One combined diagram with section dividers
**Why:** The OTel context-snapshot hand-off (mitigation for Pitfall #1) only makes sense when both halves are visible together.

---

## Trace Schema Spec Format

| Option | Description | Selected |
|--------|-------------|----------|
| Per-span markdown sections + attribute tables + JSON example | One H2 per span with attr table (name/type/required/OTel-status/example) + payload. | ✓ |
| JSON Schema files (.schema.json) | Machine-readable but tooling immature for OTel attribute names. | |
| Pydantic class drafts only | Code-first; harder for fresh-agent doc check. | |

**[auto] Selected:** Per-span markdown sections (recommended)
**Why:** Fresh-agent docs check (ROADMAP success criteria 2) requires reading prose + tables. Pydantic constants block at top of file gives Phase 4 a copy-paste source.

---

## API Contract Format

| Option | Description | Selected |
|--------|-------------|----------|
| Markdown tables + Pydantic v2 code blocks per endpoint | Human-readable; copy-paste safe into Phase 2 schemas.py. | ✓ |
| OpenAPI YAML | Authoritative but duplicates what FastAPI auto-generates. | |
| Pydantic-only spec (.py file) | Code-first; less readable for the docs check. | |

**[auto] Selected:** Markdown + Pydantic code blocks (recommended)
**Why:** FastAPI auto-generates `/openapi.json` from Pydantic models in Phase 2 — duplicating the YAML in Phase 1 creates schema-drift risk.

---

## Wireframe Format

| Option | Description | Selected |
|--------|-------------|----------|
| ASCII layouts in markdown + annotations | Versioned, diff-able, no tool install. | ✓ |
| Figma exports (.png) | Highest fidelity; binary; off-platform. | |
| Excalidraw (.excalidraw) | Quick to draw; binary. | |
| HTML throwaway sketches (`/gsd-sketch`) | Highest fidelity, extra tooling. | |

**[auto] Selected:** ASCII + annotations (recommended)
**Why:** Components are pre-decided (shadcn/ui + Tremor); wireframes need to convey LAYOUT + DATA SOURCE + STATES, not pixel fidelity. ASCII is sufficient and version-controlled.

---

## Coverage Query Set Format

| Option | Description | Selected |
|--------|-------------|----------|
| YAML file with id/query/doc_section/expected_chunk_keywords/expected_min_score | Human-authorable, machine-loadable in Phase 6. | ✓ |
| JSON file | Machine-friendly, less human-friendly. | |
| Markdown table | Human-friendly, harder to load. | |
| Plain `.txt` of queries | No retrieval-coverage metadata. | |

**[auto] Selected:** YAML (recommended)
**Why:** Phase 6 `eval/regression.py` needs to load expected_chunk_keywords + expected_min_score programmatically; YAML strikes the human/machine balance.

---

## Coverage Query Count & Authoring

| Option | Description | Selected |
|--------|-------------|----------|
| 12 hand-curated against Claude API docs TOC | Slightly above the 10-floor; covers all major sections. | ✓ |
| 10 (minimum per DSGN-10) | Floor only; no headroom. | |
| 20+ generated then filtered | LLM-generated; risks training-data leakage. | |

**[auto] Selected:** 12 hand-curated (recommended)
**Why:** Buffer above the floor lets Phase 5 calibration drop low-quality queries without falling below DSGN-10 minimum. Hand-curation avoids self-referential bias from generating queries with the same model that will answer them.

---

## Voyage AI Pricing — Block Phase 1 or Defer?

| Option | Description | Selected |
|--------|-------------|----------|
| Defer pricing verification to Phase 2 INFRA-01 prereq | Write GSD-OPEN-3 ADR with Voyage primary + `nomic-embed-text-v1.5` fallback; checkbox to verify before INFRA-01 closes. | ✓ |
| Block Phase 1 until pricing verified | Halts ADR drafting; user must check pricing now. | |
| Switch primary to sentence-transformers preemptively | Loses Voyage's quality for code/technical docs. | |

**[auto] Selected:** Defer to Phase 2 prereq (recommended)
**Why:** Phase 1 is design-only; the ADR can capture both options. Pricing only matters when we're about to call the API in Phase 2/3.

---

## Risk + Scope-Trim Plan Structure

| Option | Description | Selected |
|--------|-------------|----------|
| Single trigger (>25% slip) + ordered cut list | One threshold, one prioritized list; easy to invoke. | ✓ |
| Multi-tier trigger (10% / 25% / 50%) | More granular, more decision overhead. | |
| Plan-by-phase trim list (per-phase) | Per-phase budget guardrails; complex. | |

**[auto] Selected:** Single >25% trigger + ordered cuts (recommended)
**Why:** A ~12-hour portfolio project doesn't justify multi-tier overhead. One clear trigger = easier to act on.

---

## Verification Gate Mechanism (Phase 1 → Phase 2)

| Option | Description | Selected |
|--------|-------------|----------|
| Single fresh-agent docs check (5 onboarding questions) | Spawn `Explore` sub-agent given ONLY `/docs/`; pass = correct answers. | ✓ |
| Per-ADR user sign-off | User reads each of 10 ADRs and approves; high friction. | |
| Reviewer sub-agent comparing /docs/ to research | Internal consistency check; doesn't validate fresh-reader experience. | |

**[auto] Selected:** Fresh-agent docs check (recommended; matches ROADMAP success criteria 2)
**Why:** Tests the property the requirement actually wants — that `/docs/` alone is sufficient onboarding.

---

## Module Dependency Diagram Validation

| Option | Description | Selected |
|--------|-------------|----------|
| Visual inspection in Phase 1, runtime check in Phase 2 | Phase 1 produces diagram; Phase 2 INFRA-04 adds an import-cycle pre-commit hook. | ✓ |
| Static-analysis tool now (`pydeps`, `import-linter`) | Premature — no code yet to analyze. | |
| Skip — let Phase 2 catch cycles | Loses the design-time intent capture. | |

**[auto] Selected:** Visual now + runtime check Phase 2
**Why:** Diagram captures intent before code exists; pre-commit hook (Phase 2 INFRA-04 territory) enforces it after code lands.

---

## Anti-Patterns to Bake Into Artifacts

The following are NOT gray areas (no choice) but are recorded here so the audit trail shows they were considered for inclusion in the artifacts:

- Span-attribute size limit warning in `/docs/trace-schema.md` (Pitfall #2)
- OTel context snapshot before `root.end()` in `/docs/sequence-diagrams.md` (Pitfall #1, #4)
- `embedding_model` + `indexed_at` chunk metadata mandate in ADR 003 (Pitfall #2 in research SUMMARY)
- Haiku dated-snapshot pin in ADR 008 (Pitfall #3 in research SUMMARY)
- `spans` table monthly partitioning note in ADR 004

All five pre-decided as `[auto]` mandatory inclusions.

---

## Claude's Discretion

In `--auto` mode, every decision is the recommended default drawn from `.planning/research/SUMMARY.md` and `ARCHITECTURE.md`. The user may override any of the following during plan-phase if a different signal emerges:
- D-32 query-schema field set
- D-37 cut order in scope-trim plan
- D-10 default chunk size / overlap
- D-12 initial faithfulness threshold (`< 0.6` is a placeholder; calibration in Phase 5 sets the real value)

## Deferred Ideas

(Identical to `<deferred>` block in `01-CONTEXT.md`. Repeated here only so this file is self-contained for future audits.)

- Voyage AI pricing verification → Phase 2 INFRA-01 prereq
- Judge calibration set (~30 hand-labeled traces) → Phase 5 EVAL-06
- Demo corpus snapshot to fixture → Phase 7 DEMO-07
- OpenAPI YAML / JSON schema export → Phase 2 (auto-generated by FastAPI)
- Per-stage failure diagnosis tag **UI** → Phase 5 FBCK-05 (schema column locked in Phase 1)
- Cross-encoder reranker → v2 V2-RANK-01
- Streaming, auth/multi-tenant, multi-modal, agentic multi-hop → v2 / out of scope per PROJECT.md
