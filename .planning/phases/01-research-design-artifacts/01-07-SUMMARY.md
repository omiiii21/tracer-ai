---
phase: 01-research-design-artifacts
plan: 07
subsystem: design
tags: [sequence-diagram, wireframes, ui, design, dsgn-03, dsgn-07]

requires:
  - phase: 01-CONTEXT
    provides: D-16 (sequence diagram = Mermaid sequenceDiagram on the same diagram showing sync POST /chat path AND async BackgroundTasks-driven eval branch with Note over blocks separating phases), D-27 (5 wireframe filenames + routes — chat.md, dashboard-list.md, dashboard-detail.md, bad-answer-queue.md, admin.md), D-28 (per-wireframe required sections — ASCII layout, component inventory, data sources / endpoint binding, empty/loading/error states, interactions), D-29 (markdown only — no images, no Figma, no Excalidraw — diff-able), D-30 (wireframes/README.md links all 5 wireframes + Mermaid click-through map), D-48 (sequence diagram MUST show OTel context snapshot capture BEFORE root.end() with a Note callout — Pitfall #1 mitigation), D-50 (judge model pinned to dated snapshot — claude-haiku-4-5-20251001 — recorded on every rag.eval span)
  - phase: 01-RESEARCH
    provides: §"Per-Artifact Authoring Guide › Artifact 4" (sequence-diagram structure — 8 participants, alt block for eval-failure suppression, GitHub renderer gotchas — no autonumber, uniform participant), §"Per-Artifact Authoring Guide › Artifacts 9-13" (wireframe structure — 6 required h2 sections, ASCII gotchas, component-state coverage rule), §"Artifact 14" (index README + Mermaid click-through map per D-30)
  - phase: 01-02 (architecture)
    provides: docs/architecture.md (actor naming consistency — FastAPI, Pipeline, Tracer, Anthropic, Postgres; module responsibilities table; the dotted async edge api -.async.-> eval is the BackgroundTasks branch the sequence diagram now visualizes in detail)
  - phase: 01-04 (trace schema)
    provides: docs/trace-schema.md (canonical span names — rag.request / rag.retrieve / rag.prompt_assemble / rag.llm_call / rag.eval — used as row labels in the dashboard-detail.md waterfall; gen_ai.* and rag.* attribute names rendered in the JSON viewer mock)
  - phase: 01-06 (api contract)
    provides: docs/api.md (endpoint paths + Pydantic shapes — POST /chat, POST /feedback, GET /traces, GET /traces/{trace_id}, GET /admin/corpus, POST /admin/ingest, PATCH /admin/chunking-config; TraceListQuery filter parameters bound by dashboard-list.md; FeedbackRequest.diagnosis_tag allowed values surfaced by chat.md and dashboard-detail.md Select component)

provides:
  - Chat-request sequence diagram at docs/sequence-diagrams.md (DSGN-03) — one Mermaid sequenceDiagram block; 8 participants; sync request path + async BackgroundTasks eval branch; OTel context-snapshot Note callout encoding Pitfall #1 (D-48); alt/else block enforcing eval-failure suppression (Pitfall #3); dated model snapshots pinned (Pitfall #4 / D-50); 90 LOC
  - 5 route wireframes + index at docs/wireframes/ (DSGN-07) — chat.md (98 LOC), dashboard-list.md (84 LOC), dashboard-detail.md (113 LOC), bad-answer-queue.md (90 LOC), admin.md (95 LOC), README.md (41 LOC); each wireframe contains the 6 required h2 sections (Route, Bound API Endpoints, Component Inventory, Layout, States, Interactions) and 4 named states (Loading / Empty / Error / Populated) per D-28; component inventories cite Tremor v3 (KpiCard, AreaChart) + shadcn/ui (Card, Table, Tabs, Dialog, Badge, Button, Select, Slider, ScrollArea, Tooltip, Toast, Form, Input, Textarea) verbatim
  - Phase 4 TRCR-04 design contract — sequence-diagrams.md Note callout literally states "Snapshot otel_context.get_current() BEFORE root.end()" + the Design Contracts Encoded section restates the 4 normative rules in prose; Phase 4 executor inherits Pitfall #1 / #3 / #4 mitigations as design-time contracts, not runtime discoveries
  - Phase 3/4/5 frontend component-name contract — every wireframe component-inventory table maps regions to specific Tremor v3 / shadcn/ui symbol names; CHAT-*, EXPL-03..04, FBCK-03, DASH-*, ADMN-* implementers copy-paste without symbol drift (mitigates threat T-01-07-03)
  - Phase 3/4/5 endpoint-binding contract — every wireframe binds at least one endpoint string from docs/api.md verbatim; dashboard-list.md surfaces the full TraceListQuery filter parameter set; admin.md surfaces all three admin endpoints plus their Pydantic field constraints (chunk_size 100-4000, overlap 0-500) for client-side <FormMessage> validation
  - Wireframe click-through navigation map — wireframes/README.md Mermaid flowchart LR (D-30) shows the 5 task-driven paths between routes (Chat -> Detail via trace link; List/Queue -> Detail via row click; sidebar fan-out from List)

affects: [01-08 verification (fresh-agent docs check Q2 "how does data flow" answerable from sequence-diagrams.md alone; Q5 "what does the UI look like" answerable from wireframes/README.md + 5 wireframes alone), Phase 4 TRCR-04 (BackgroundTasks dispatch + context-snapshot wiring inherits Pitfall #1 mitigation as a design contract), Phase 3 CHAT-01..05 (chat UI implementers copy component inventory from chat.md; bind to POST /chat + POST /feedback per api.md), Phase 3 ADMN-01..04 (admin UI implementers copy component inventory from admin.md; form validators copy chunk_size 100-4000 / overlap 0-500 constraints), Phase 4 EXPL-03..04 (trace explorer detail page implementers copy waterfall + payload-inspector layout from dashboard-detail.md; render rag.request / rag.retrieve / rag.prompt_assemble / rag.llm_call / rag.eval rows verbatim), Phase 5 DASH-* (dashboard list page implementers copy KPI strip + AreaChart + filter bar from dashboard-list.md), Phase 5 FBCK-03/05 (thumbs-down Dialog with diagnosis_tag Select implementer copies from chat.md; trace-detail diagnosis_tag editor implementer copies from dashboard-detail.md), Phase 6 CLI-05 (Promote-to-Regression-Set workflow surface documented in bad-answer-queue.md; CLI executor inherits the operator's UX expectations as a wireframe-level contract)]

tech-stack:
  added: []  # design-only markdown; no runtime deps in Phase 1
  patterns:
    - "Mermaid sequenceDiagram with phase-separating Note over blocks — three Note over headers (Phase 1 sync request path, Phase 2 async eval branch, Phase 3 judge runs as child via ctx_snapshot) make the request lifecycle visually scannable; readers do not need to parse arrow chronology to understand the boundary between sync and async work"
    - "Design contract encoded literally in diagram source — the Pitfall #1 mitigation appears verbatim in the diagram's Note callout (BEFORE root.end()), not just in the surrounding prose; a Phase 4 implementer reading only the diagram still sees the rule. Belt-and-braces: the Design Contracts Encoded section duplicates it in prose"
    - "GitHub Mermaid renderer guards — uniform `participant` declarations (no `actor` mixing), no `autonumber` directive, no experimental shape syntax; verified by grep assertions in the verify block. Silent render failure on GitHub is the failure mode — there is no on-page error message"
    - "Async dispatch arrow `-)` for fire-and-forget visualization — FastAPI-)BackgroundTasks renders as a half-arrow on GitHub Mermaid, immediately distinguishable from sync `->>` arrows; reader sees the fire-and-forget at a glance"
    - "alt/else block for eval-failure suppression — Mermaid alt syntax compiles to two visible code paths in the rendered diagram, one of which contains the `NEVER re-raise` Note. Pitfall #3 becomes a visual contract, not a footnote"
    - "Per-wireframe 6-section structure — every wireframe has h2 sections in the same order: Route, Bound API Endpoints, Component Inventory, Layout, States, Interactions. Verify-block grep asserts the exact strings; CI catches drift"
    - "4-state coverage rule — every wireframe documents Loading / Empty / Error / Populated states by name (RESEARCH.md component-state coverage rule). Mitigates threat T-01-07-05 — fresh-agent docs check Q5 fails if any wireframe is silent on a state"
    - "Component-inventory tables map regions to Tremor v3 + shadcn/ui symbol names verbatim — STACK.md is the canonical name list; wireframes copy from it without paraphrasing. Mitigates threat T-01-07-03 — drift = wrong import in Phase 3 frontend"
    - "Endpoint binding by literal path string — wireframes cite POST /chat, GET /traces?feedback=down, etc. matching docs/api.md exactly. Verify-block grep asserts each path. Mitigates threat T-01-07-04 — typo propagation"
    - "Async-parentage visual cue in dashboard-detail waterfall — the rag.eval row uses a dashed parent line (└╌╌) instead of solid (├─); the visual difference encodes the cross-task ctx_snapshot relationship documented in sequence-diagrams.md. Operator reading the trace detail sees the async-parentage at the same time they see the underlying mechanism"
    - "Form-level Pydantic-constraint mirroring — admin.md's chunking-config form documents the same chunk_size (100-4000) and overlap (0-500) constraints from ChunkingConfigPatch in api.md; <FormMessage> renders the same field-level errors the server returns at 422. The wireframe mandates client + server validators agree by construction"
    - "Future-stub-without-migration pattern surfaced in UI — dashboard-detail.md and chat.md both show the diagnosis_tag Select with a Phase 5 FBCK-05 future-stub annotation; the UI region is allocated, the API field is allocated, but the actual wiring lands in Phase 5. Bridges the contract from api.md (FeedbackRequest.diagnosis_tag: str | None) to the eventual UX without forcing premature implementation"
    - "Click-through map as Mermaid flowchart LR per D-30 — wireframes/README.md encodes the operator's task-driven paths between routes (Chat -> Detail; List/Queue -> Detail; sidebar fan-out). Phase 3+ frontend nav implementer reads the flowchart and the routes-to-implement list in the same file"

key-files:
  created:
    - "docs/sequence-diagrams.md (90 LOC)"
    - "docs/wireframes/chat.md (98 LOC)"
    - "docs/wireframes/dashboard-list.md (84 LOC)"
    - "docs/wireframes/dashboard-detail.md (113 LOC)"
    - "docs/wireframes/bad-answer-queue.md (90 LOC)"
    - "docs/wireframes/admin.md (95 LOC)"
    - "docs/wireframes/README.md (41 LOC)"
  modified: []

decisions:
  - "Encoded Pitfall #1 mitigation (capture OTel context BEFORE root.end()) as a Mermaid Note callout in the diagram body — not just prose around it — so that a Phase 4 TRCR-04 executor reading only the rendered diagram still sees the rule. The Design Contracts Encoded section duplicates the rule in prose for redundancy"
  - "Used uniform `participant` declarations across all 8 actors (Browser, FastAPI, Pipeline, Tracer, Anthropic, BackgroundTasks, Judge, Postgres) — RESEARCH.md gotcha says mixing `participant` and `actor` causes silent GitHub render failure. Verify-block grep asserts no `actor ` lines"
  - "Pinned dated model snapshots (claude-sonnet-4-5-20250929, claude-haiku-4-5-20251001) directly in the diagram body — Pitfall #4 / D-50. The bot and judge use the same dated-snapshot policy; aliases are explicitly avoided"
  - "Wireframe ASCII layouts go in fenced code blocks with `text` language hint (per RESEARCH.md Pitfall C — non-monospace renderer guard). Unicode box characters (┌─┐│└┘├┤┬┴┼) used uniformly; widths kept ≤80 cols"
  - "Wireframes index README uses Mermaid flowchart LR (not TD) per D-30 — the operator's mental model of the routes is left-to-right (chat surfaces -> diagnostic surfaces). The arrows show task-driven paths, not all-pairs reachability (which is the sidebar's job and is documented in prose alongside the diagram)"
  - "Component-inventory tables list both Tremor v3 (KpiCard, AreaChart) and shadcn/ui components in the same table with a Library column — Phase 3+ implementers see the import boundary at a glance. Custom components (e.g., the waterfall) are explicitly tagged `custom` in the same column"
  - "dashboard-detail.md documents an additional Eval pending state beyond the 4-state rule — when rag.eval has not yet completed, the waterfall renders an animated bar and the faithfulness/relevance badges show em-dashes. This state is the user-visible manifestation of the BackgroundTasks dispatch shown in sequence-diagrams.md — the wireframe and the sequence diagram are mutually consistent"
  - "bad-answer-queue.md documents the Phase 5 FBCK-04 (Resolve) and Phase 6 CLI-05 (Promote) UX surfaces even though the backends do not yet exist — the wireframe is the contract; the Toast text explicitly says 'Resolution recorded — will sync once Phase 5 FBCK-04 ships', so a Phase 1 reader understands the staging without confusion"

metrics:
  duration: "~12 min"
  completed_date: "2026-05-04"
  files_created: 7
  total_loc: 611
---

# Phase 1 Plan 07: Sequence Diagram + 5 Wireframes Summary

**One-liner:** Authored chat-request sequence diagram (DSGN-03) and 5 route wireframes + index README (DSGN-07) — 7 markdown files, 611 LOC; sequence diagram encodes Pitfall #1 OTel context-snapshot rule as a Mermaid `Note over` callout (Phase 4 TRCR-04 design contract); wireframes bind every UI region to a Tremor v3 / shadcn/ui component name and a docs/api.md endpoint path.

## Output Verification

### Sequence diagram (`docs/sequence-diagrams.md`)

- **One** ` ```mermaid sequenceDiagram` block (verified by `grep -c '^```mermaid$' == 1`).
- **8 participants** declared uniformly (no `actor` mixing): `Browser`, `FastAPI`, `Pipeline`, `Tracer`, `Anthropic`, `BackgroundTasks`, `Judge`, `Postgres`.
- **OTel context-snapshot Note callout present:** literal substring `BEFORE root.end()` AND the snapshot phrasing `otel_context.get_current()` AND `ctx_snapshot = capture_context()` both present. References `Pitfall #1` by name.
- **Async dispatch arrow** `FastAPI-)BackgroundTasks` present (fire-and-forget visualization).
- **`alt eval succeeds` / `else eval fails` block** present (Pitfall #3 eval-failure suppression with `NEVER re-raise` Note).
- **Dated model snapshots** present: `claude-sonnet-4-5-20250929` (bot) and `claude-haiku-4-5-20251001` (judge) — Pitfall #4 / D-50.
- **GitHub renderer guards:** no `autonumber` directive; no `actor` declarations.
- **Cross-references** to architecture.md, api.md, trace-schema.md, ADR 005.

### 5 wireframes + index (`docs/wireframes/`)

The 5 routes covered (per D-27):

1. `/chat` → `chat.md` (98 LOC)
2. `/dashboard` → `dashboard-list.md` (84 LOC)
3. `/dashboard/traces/{id}` → `dashboard-detail.md` (113 LOC)
4. `/dashboard/queue` → `bad-answer-queue.md` (90 LOC)
5. `/admin` → `admin.md` (95 LOC)

Plus `README.md` (41 LOC) — index + Mermaid `flowchart LR` click-through map (D-30).

**Per-wireframe 6 required h2 sections present** (verified by grep on each file): `## Route`, `## Bound API Endpoints`, `## Component Inventory`, `## Layout`, `## States`, `## Interactions`.

**Per-wireframe 4 named states present in every file:**

| File | Loading | Empty | Error | Populated |
|------|---------|-------|-------|-----------|
| chat.md | ✓ | ✓ | ✓ | ✓ |
| dashboard-list.md | ✓ | ✓ | ✓ | ✓ |
| dashboard-detail.md | ✓ | ✓ | ✓ | ✓ (+ Eval pending) |
| bad-answer-queue.md | ✓ | ✓ | ✓ | ✓ |
| admin.md | ✓ | ✓ | ✓ | ✓ |

**Endpoint bindings (verified by grep against docs/api.md paths):**

- `chat.md` → `POST /chat`, `POST /feedback`
- `dashboard-list.md` → `GET /traces` (with `TraceListQuery` filter parameters)
- `dashboard-detail.md` → `GET /traces/{trace_id}` (also references span names `rag.request` and `rag.eval` from trace-schema.md)
- `bad-answer-queue.md` → `GET /traces?feedback=down`, `GET /traces?min_faithfulness=0.6`
- `admin.md` → `GET /admin/corpus`, `POST /admin/ingest`, `PATCH /admin/chunking-config`

**Component library coverage:**

- Tremor v3 components cited: `KpiCard` (dashboard-list, admin), `AreaChart` (dashboard-list).
- shadcn/ui components cited: `Card`, `Table`, `Tabs`, `Dialog`, `Badge`, `Button`, `Select`, `Slider`, `ScrollArea`, `Tooltip`, `Toast`, `Form`, `Input`, `Textarea`, `Alert`, `<FormMessage>`.
- Custom components tagged: span waterfall (dashboard-detail), JSON `<pre>` viewer (dashboard-detail).

### Click-through map (`docs/wireframes/README.md`)

- One ` ```mermaid flowchart LR` block (verified by `grep -c == 1`).
- 5 nodes: `Chat`, `List`, `Detail`, `Queue`, `Admin`.
- 7 edges: `Chat -> Detail` (trace link), `Chat -> Chat` (thumbs down), `List -> Detail` (click row), `Queue -> Detail` (click row), `Admin -> List`, `List -> Queue`, `List -> Admin` (sidebar nav).
- Wireframe table links all 5 wireframe filenames + bound endpoints.
- Cross-references to api.md, sequence-diagrams.md, trace-schema.md, architecture.md.

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED

- [x] `docs/sequence-diagrams.md` exists; one Mermaid block; 8 participants; `BEFORE root.end()` Note callout present; `Pitfall #1` referenced; alt/else eval-suppression block present; no `autonumber`; no `actor`; dated model snapshots `claude-sonnet-4-5-20250929` + `claude-haiku-4-5-20251001` present.
- [x] 5 wireframe files exist under `docs/wireframes/` matching D-27 filenames.
- [x] Each wireframe contains the 6 required h2 sections.
- [x] Each wireframe documents the 4 named states (Loading / Empty / Error / Populated).
- [x] Endpoint bindings verified verbatim against `docs/api.md` paths.
- [x] `docs/wireframes/README.md` h1 = `# Wireframes Index`; one Mermaid `flowchart LR`; links all 5 wireframes by filename.
- [x] Tremor v3 + shadcn/ui component names referenced verbatim from STACK.md.
- [x] Commits exist: `4085708` (sequence-diagrams.md) and `4fe0483` (6 wireframe files).
