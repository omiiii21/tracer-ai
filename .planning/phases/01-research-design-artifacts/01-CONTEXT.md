# Phase 1: Research & Design Artifacts - Context

**Gathered:** 2026-05-04
**Status:** Ready for planning
**Mode:** `--auto` (recommended option auto-selected for every gray area)

<domain>
## Phase Boundary

Phase 1 produces **only design artifacts under `/docs/`** — no application code, no infra, no dependencies installed. Deliverables:

1. Nine ADRs in `/docs/decisions/NNN-<slug>.md` (one per `GSD-OPEN-N` item from the foundation PRD §10)
2. System architecture diagram (Mermaid `graph`) at `/docs/architecture.md`
3. Chat-request sequence diagram (Mermaid `sequenceDiagram`) at `/docs/sequence-diagrams.md`
4. Trace schema spec at `/docs/trace-schema.md` — every span name, attribute, type, OTel-conformance status, example payload
5. DB schema / ERD (Mermaid `erDiagram`) at `/docs/data-model.md` covering `traces`, `spans`, `span_payloads`, `feedback`, `regression_cases`, plus the `pgvector` collection schema
6. API contract at `/docs/api.md` with Pydantic-shaped request/response models for `POST /chat`, `GET /traces`, `GET /traces/{id}`, `POST /feedback`, ingest + admin endpoints
7. UI wireframes under `/docs/wireframes/` for chat, trace list, trace detail, bad-answer queue, admin
8. Module dependency diagram at `/docs/module-deps.md` proving the architecture-research module layout has no cycles
9. Risk + scope-trim plan at `/docs/decisions/010-scope-trim.md` — which phases get cut first if budget slips >25%
10. Proactive coverage regression query set at `/docs/eval/coverage_set.yaml` — 12 queries covering each major Claude API doc section (auth, models, prompts, tools, batches, files, citations, vision, errors, prompt-caching, agent-sdk-overview, agent-sdk-tools)

**Verification gate (single):** A fresh agent given only `/docs/` answers — what the system does, how data flows, what the trace schema is, what API endpoints exist, and what the UI looks like — without reading any code.

**Out of scope this phase:** any code in `tracer_ai/`, `frontend/`, `infra/`; any `pip install` / `npm install`; running `docker compose`; writing tests; verifying Voyage AI pricing (that gates Phase 2 INFRA-01, not Phase 1).

</domain>

<decisions>
## Implementation Decisions

### ADR Format & Index
- **D-01:** ADR template = MADR-lite (Nygard-style). Four required sections: `## Status`, `## Context`, `## Options Considered`, `## Decision`, `## Consequences`. Optional `## References`. One page max per ADR. Status starts as `Accepted` since each ADR cites the already-completed research in `.planning/research/`.
- **D-02:** ADR filenames: `/docs/decisions/NNN-<slug>.md` zero-padded 3 digits (`001`–`010`). Slug is hyphen-case noun phrase.
- **D-03:** ADR numbering: `001`–`009` map 1:1 to `GSD-OPEN-1`..`GSD-OPEN-9`. `010` is the scope-trim plan (DSGN-09). An `/docs/decisions/README.md` index lists all ADRs with one-line summaries — fresh agents land here first.
- **D-04:** Every ADR cites the relevant research file (`.planning/research/SUMMARY.md`, `STACK.md`, `ARCHITECTURE.md`, `PITFALLS.md`, `FEATURES.md`) by section anchor. Research is the canonical source — ADRs codify the decision and consequences, not the analysis.

### Decisions Already Locked (codified into ADRs without re-discussion)
The 9 `GSD-OPEN-N` items are all resolved by research (`SUMMARY.md` §"GSD-OPEN-N Resolution Status"). Phase 1 is mechanical ADR drafting from those resolutions:
- **D-05:** ADR 001 (charting) → Tremor v3.
- **D-06:** ADR 002 (vector store) → pgvector on the same Postgres 16 instance as the trace DB.
- **D-07:** ADR 003 (embedder) → Voyage AI `voyage-code-3` primary; `sentence-transformers` `nomic-embed-text-v1.5` fallback for offline dev / pricing escape hatch. **Pricing verification is a Phase 2 prereq, not a Phase 1 blocker** — the ADR captures both paths and a `[ ] Verify Voyage pricing before INFRA-01 closes` checkbox.
- **D-08:** ADR 004 (trace store) → Postgres 16 + JSONB, GIN-indexed. Single instance with pgvector.
- **D-09:** ADR 005 (observability strategy) → Custom tracer with OTel GenAI **attribute names only** as constants in `tracer/span.py`. **Do NOT take a runtime dependency on `opentelemetry-sdk`.** Use `gen_ai.provider.name` (NOT deprecated `gen_ai.system`). Naming-compatible export to OTel collectors deferred to a future module under `tracer/exporters/otel/`.
- **D-10:** ADR 006 (chunking) → Markdown-header-aware splitter at `##`/`###`; never splits inside fenced code blocks; configurable size + overlap; admin-tunable. Default `chunk_size=900 tokens`, `overlap=100 tokens` (revisit during Phase 5 calibration).
- **D-11:** ADR 007 (re-ranking) → None in v1. Config flag `ENABLE_RERANKER` reserved for v2; no implementation in v1.
- **D-12:** ADR 008 (judge prompts + thresholds) → RAGAS-style faithfulness + relevance prompts. **Untrusted content (retrieved chunks, assistant answers) wrapped in XML delimiters** (`<retrieved_chunk>`, `<assistant_answer>`), system instruction declares them as inert data. Initial threshold `faithfulness < 0.6` flags bad-answer; **calibrated against ~30 hand-labeled traces in Phase 5 (EVAL-06)** — Phase 1 only writes the prompts and the calibration plan.
- **D-13:** ADR 009 (auth + v1.5 deployment) → ADR-only direction; do NOT implement in v1. Captures intent: future single-tenant API-key middleware in front of FastAPI; future deployment to single-node cloud host via the same Compose file. No code, no tests, no env vars added in v1.

### Diagram Tooling
- **D-14:** All diagrams use Mermaid in fenced code blocks inside markdown files. No PNG/SVG exports, no Excalidraw, no PlantUML. Justification: REQUIREMENTS.md DSGN-02..05 lock Mermaid; renders natively in GitHub README; zero tool install.
- **D-15:** System architecture diagram = Mermaid `flowchart TD` (top-down) with subgraphs for Frontend / FastAPI / Persistence. Mirrors the ASCII tree in `.planning/research/ARCHITECTURE.md` §"System Overview".
- **D-16:** Sequence diagram = Mermaid `sequenceDiagram` showing the sync `POST /chat` request path AND the async `BackgroundTasks`-driven eval branch on the same diagram (with `Note over` blocks separating the phases). Includes the OTel context-snapshot hand-off (mitigation for Pitfall #1).
- **D-17:** ERD = Mermaid `erDiagram` with all 5 tables and FKs: `traces`, `spans`, `span_payloads` (1:N off `spans`), `feedback` (N:1 off `traces`), `regression_cases`. pgvector collection schema documented as a separate fenced SQL block alongside the ERD.
- **D-18:** Module dependency diagram = Mermaid `flowchart LR` with one node per module (`config`, `tracer/`, `rag/`, `eval/`, `corpus/`, `api/`, `cli/`, `errors`). Edges = imports. Validation in this phase is **visual** (acyclicity by inspection); a runtime check belongs to Phase 2 pre-commit.

### Trace Schema Spec Format
- **D-19:** `/docs/trace-schema.md` is organized as one `##` section per span, in this order: `rag.request` (root), `rag.retrieve`, `rag.prompt_assemble`, `rag.llm_call`, `rag.eval`, `feedback.user`.
- **D-20:** Each span section contains: (a) one-line purpose, (b) attribute table with columns `name | type | required | OTel status | example`, (c) a JSON example payload of the full span, (d) any payload-table reference (large prompts/responses live in `span_payloads` JSONB column, not on the span row).
- **D-21:** All `gen_ai.*` and `rag.*` attribute names are codified once at the top of `/docs/trace-schema.md` and copy-paste-ready as Python constants — Phase 4 TRCR-01 imports the same names into `tracer/span.py`.
- **D-22:** Document the **OTel deprecation note explicitly**: `gen_ai.system` is deprecated; we use `gen_ai.provider.name`. The doc states the spec stability is Development/Experimental — naming may change — and mitigation is the central constants file.

### API Contract Format
- **D-23:** `/docs/api.md` is one `##` section per endpoint, in this order: `POST /chat`, `POST /feedback`, `GET /traces`, `GET /traces/{id}`, `POST /admin/ingest`, `GET /admin/corpus`, `PATCH /admin/chunking-config`.
- **D-24:** Each endpoint section contains: (a) HTTP method + path + summary, (b) request schema as a Pydantic v2 class code block (Python), (c) response schema as a Pydantic v2 class code block, (d) example request body JSON, (e) example response body JSON, (f) error responses table (status code + Pydantic error envelope).
- **D-25:** **Do NOT generate an OpenAPI YAML in Phase 1.** FastAPI auto-generates `/openapi.json` from the Pydantic models in Phase 2 — duplicating now creates drift.
- **D-26:** Pydantic shapes use `model_config = ConfigDict(extra="forbid")` and explicit field types — copy-paste safe into `tracer_ai/api/schemas.py` in Phase 2/3.

### Wireframes Format
- **D-27:** Wireframes are markdown files under `/docs/wireframes/` with **embedded ASCII box layouts** + bullet-point annotations. One file per route: `chat.md`, `dashboard-list.md` (trace list), `dashboard-detail.md` (trace detail), `bad-answer-queue.md`, `admin.md`.
- **D-28:** Each wireframe file documents: (a) ASCII layout, (b) component inventory (which shadcn/ui + Tremor components compose it — `Card`, `Table`, `Tabs`, `AreaChart`, etc.), (c) data sources (which API endpoint each region binds to), (d) empty / loading / error states, (e) interactions ("clicking row N navigates to /dashboard/traces/{id}").
- **D-29:** No image files, no Figma, no Excalidraw. Reasons: (i) version-controlled diff visibility, (ii) no tool install on a fresh machine to read them, (iii) ASCII fidelity is sufficient for an SPA whose components are pre-decided (Tremor + shadcn/ui).
- **D-30:** Wireframes index file `/docs/wireframes/README.md` links all five wireframes and shows the click-through map between them.

### Coverage Query Set Format & Authoring
- **D-31:** File path `/docs/eval/coverage_set.yaml`. (Note: `/docs/eval/` is created in Phase 1 even though it is otherwise a Phase 6 directory — the coverage set is authored here per DSGN-10.)
- **D-32:** Schema per query:
  ```yaml
  - id: COV-01
    query: "How do I authenticate to the Anthropic Messages API?"
    doc_section: auth
    expected_chunk_keywords: ["x-api-key", "authentication", "API key"]
    expected_min_score: 0.6   # initial; calibrated in Phase 5
    notes: ""
  ```
- **D-33:** **12 queries** covering: `auth`, `models`, `messages` (basic prompts), `tools` (tool use), `batches`, `files`, `citations`, `vision`, `errors-and-rate-limits`, `prompt-caching`, `agent-sdk-overview`, `agent-sdk-tools`. Exceeds the DSGN-10 floor of 10.
- **D-34:** Authoring approach = hand-curated against a Claude API docs TOC (top-level pages of docs.claude.com), not LLM-generated. Each query is a real question a developer would ask. Phase 1 author writes them; calibration in Phase 5 may rewrite `expected_min_score` and `expected_chunk_keywords`.
- **D-35:** **No ground-truth answer text.** Coverage queries assert *retrieval coverage* (right chunks come back) — not answer correctness, which is the LLM judge's job.

### Risk + Scope-Trim Plan (DSGN-09)
- **D-36:** Codified as ADR `010-scope-trim.md`. Single trigger: build budget slips >25% (i.e., projected hours > 15 against the ~12-hour target).
- **D-37:** Cut order on trigger:
  1. Phase 7 polish items DEMO-02 (GIF/screenshots), DEMO-03 (cost widget), DEMO-04 (JSON export) — keep README + clean-state test only.
  2. Phase 5 dashboard chart DASH-04 (manual feedback ratio over time) — KPI tile only.
  3. Phase 5 FBCK-05 (per-stage failure diagnosis tag UI) — keep schema column, drop UI.
  4. Phase 6 CLI markdown report (CLI-04) — keep JSON output only.
  5. Phase 5 EVAL-06 calibration set size — drop from ~30 to ~15 hand-labeled traces.
- **D-38:** Cuts are **listed but not pre-approved** — invoking the trim plan still requires updating PROJECT.md "Out of Scope" and noting the reason.

### Verification Gate (DSGN, single check before Phase 2)
- **D-39:** Phase 1 verification step (planned in plan-phase) = a "fresh-agent docs check": spawn a sub-agent given ONLY `/docs/` and ask it the 5 questions from ROADMAP.md success criteria 2. Pass requires correct answers without reading any code or `.planning/`.
- **D-40:** No per-ADR review gate. ADRs go straight to "Accepted" since they codify completed research; if the user objects to any ADR, that's a discussion in this phase, not a Phase 2 blocker.

### Dependency Map (which deliverable enables which downstream phase)
- **D-41:** Coverage query set → required by Phase 6 CLI-02. ✅ Phase 1.
- **D-42:** Trace schema spec → required by Phase 4 TRCR-01..03 (attribute constants). ✅ Phase 1.
- **D-43:** API contract → required by Phase 3 RAG-05 + ADMN-01..04 + CHAT-01..05 + Phase 4 EXPL-01..02. ✅ Phase 1.
- **D-44:** Wireframes → required by Phase 3 + 4 + 5 UI work (CHAT-*, ADMN-*, EXPL-03..04, FBCK-03, DASH-*). ✅ Phase 1.
- **D-45:** Module dep diagram → required by Phase 2 INFRA-01 (repo scaffold) + import-cycle pre-commit hook (INFRA-04). ✅ Phase 1.
- **D-46:** ADR 005 (observability) → required by ALL of `tracer/` work in Phases 2 & 4 (TRCR-01..10). ✅ Phase 1.

### Anti-Patterns to Bake into Artifacts
- **D-47:** Trace schema spec MUST flag in writing: do NOT store full prompt/response text as span attributes (4–16 KB OTel limit) — use `span_payloads` JSONB side table. (Pitfall #2 in `.planning/research/ARCHITECTURE.md` §"Anti-Patterns".)
- **D-48:** Sequence diagram MUST show OTel context snapshot capture **before** `root.end()`, with a `Note` callout explaining that omitting this snapshot orphans the eval span. (Pitfall #1 / #4.)
- **D-49:** ADR 003 (embedder) MUST require `embedding_model` + `embedding_model_version` + `indexed_at` columns on the chunk table and a startup assertion that `config.embedding_model == corpus.embedding_model`. (Pitfall #2 in research SUMMARY.)
- **D-50:** ADR 008 (judge) MUST require pinning Haiku to a **dated snapshot** (e.g., `claude-haiku-4-5-20251001`), not the alias `claude-haiku`. Record `judge_model` on every `rag.eval` span. (Pitfall #3 in research SUMMARY.)
- **D-51:** ADR 004 (trace store) MUST require partitioning the `spans` table by `started_at` month — easy at write time, expensive to retrofit later.

### Claude's Discretion
- The discuss step ran in `--auto` mode: every decision above is the **recommended option** drawn from `.planning/research/SUMMARY.md` and `ARCHITECTURE.md`. None required user judgment beyond what was already validated when the research was accepted.
- Open to user override on any of D-32 query schema fields, D-37 cut order, and D-10 default chunk size/overlap during planning if a different signal emerges.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents (researcher, planner) MUST read these before planning or implementing.**

### Foundation & Vision
- `tracer-ai-foundation-prd.md` — locked foundation PRD; canonical "why" + "what" + GSD-OPEN-N origin
- `About.md` — original brief; one-paragraph framing
- `.planning/PROJECT.md` — project guardrails, locked tech stack, Out of Scope list, Open Questions tracker
- `.planning/REQUIREMENTS.md` — 75 v1 requirements, traceability table, v2 deferral list. **DSGN-01..10 are this phase's deliverables.**
- `.planning/ROADMAP.md` §"Phase 1: Research & Design Artifacts" — phase goal, success criteria, requirements list

### Research (already done — Phase 1 codifies these into ADRs)
- `.planning/research/SUMMARY.md` — executive summary; GSD-OPEN-N resolution status table; gaps to address
- `.planning/research/STACK.md` — locked stack validation, alternatives, version compatibility (cite in ADR 001/002/003/004)
- `.planning/research/ARCHITECTURE.md` — module layout, dep graph, span/eval patterns, OTel GenAI status, anti-patterns (cite in ADR 005, sequence + module-deps diagrams)
- `.planning/research/PITFALLS.md` — 12 pitfalls with phase mapping (cite in every ADR's Consequences section where relevant)
- `.planning/research/FEATURES.md` — competitor parity + differentiator gap (cite in scope-trim ADR 010)

### Phase 1 State / Memory
- `.planning/STATE.md` §"Decisions" — confirms research-backed recommendations are ready for ADR drafting
- `.planning/STATE.md` §"Blockers/Concerns" — Voyage pricing gap, judge calibration set, Tailwind v3 pin (cite in ADR 003 / ADR 008 / ADR 001 respectively)

### External (cited by research, link from ADRs only — do not re-fetch in Phase 1)
- OpenTelemetry GenAI semantic conventions (Development stability) — cited via Context7 in `ARCHITECTURE.md` §"OTel GenAI Semantic Conventions — Status as of 2026"
- Anthropic Python SDK docs — cited via Context7 in `STACK.md`
- Voyage AI docs (`docs.voyageai.com/docs/pricing`) — pricing verification deferred to Phase 2 prereq

### Outputs (created during this phase, become canonical for later phases)
- `/docs/decisions/001-charting-library.md` through `/docs/decisions/009-auth-deployment-direction.md` — ADRs
- `/docs/decisions/010-scope-trim.md` — DSGN-09
- `/docs/decisions/README.md` — ADR index
- `/docs/architecture.md` — DSGN-02
- `/docs/sequence-diagrams.md` — DSGN-03
- `/docs/trace-schema.md` — DSGN-04
- `/docs/data-model.md` — DSGN-05
- `/docs/api.md` — DSGN-06
- `/docs/wireframes/{chat,dashboard-list,dashboard-detail,bad-answer-queue,admin,README}.md` — DSGN-07
- `/docs/module-deps.md` — DSGN-08
- `/docs/eval/coverage_set.yaml` — DSGN-10

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **None yet** — greenfield repo. The only files in the repo root are `About.md`, `CLAUDE.md`, `tracer-ai-foundation-prd.md`. No `tracer_ai/`, `frontend/`, `infra/`, or `docs/` directories exist. Scaffolding starts in Phase 2.

### Established Patterns
- **GSD planning lifecycle** — `.claude/get-shit-done/` workflows + `.planning/` state. Phase 1 follows the GSD discuss → plan → execute pattern. Plans + commits live under `.planning/phases/01-research-design-artifacts/`.
- **Research is canonical, ADRs codify it** — `.planning/research/*.md` was already produced and accepted. ADRs are short codifications, not re-analyses.

### Integration Points
- `/docs/decisions/` directory must exist before Phase 2 INFRA-05 closes (already specified in INFRA-05). Phase 1 creates it and populates it.
- `/docs/architecture.md` is referenced by Phase 7 DEMO-01 ("README includes architecture diagram from Phase 1") — Phase 1 must produce a diagram embeddable into a README without further editing.
- `/docs/eval/coverage_set.yaml` is loaded by Phase 6 `eval/regression.py`. Phase 1's schema choice (D-32) IS the contract.
- `/docs/api.md`'s Pydantic shapes are the spec that Phase 2/3 routes import (via copy-paste into `tracer_ai/api/schemas.py`). Schema drift = bug — keep authoritative copy in `/docs/api.md` until Phase 3, then promote `schemas.py` to source-of-truth.

</code_context>

<specifics>
## Specific Ideas

- **"Fresh-agent docs check" is the verification mechanism** (per ROADMAP.md success criteria 2). Plan-phase should add a verification task that spawns an `Explore` sub-agent given ONLY `/docs/` and asks the 5 onboarding questions. This is the gate.
- **Self-referential narrative** (PROJECT.md §"Project framing") — the system being designed will eventually answer questions about *its own corpus* (Anthropic Claude API docs). The wireframes and example queries should lean into this where natural (e.g., the chat UI mockup can show a sample Q like "How do I use prompt caching?").
- **Memory note honored:** "Design artifacts before any coding" — Phase 1 = pure docs, no `mkdir tracer_ai/` until Phase 2.
- **Memory note honored:** "List alternatives in PRDs for downstream-agent research" — every ADR has an "Options Considered" section listing alternatives + the reason they were rejected. Future plan-phase agents reading the ADR can re-evaluate if a constraint changes.

</specifics>

<deferred>
## Deferred Ideas

- **Voyage AI pricing verification** — deferred to Phase 2 (a prereq checkbox on INFRA-01, not a Phase 1 blocker).
- **Judge calibration set authoring (~30 hand-labeled traces)** — deferred to Phase 5 EVAL-06.
- **Snapshot of demo corpus to a fixture file** — deferred to Phase 7 DEMO-07.
- **OpenAPI YAML / JSON schema export** — deferred to Phase 2 (FastAPI auto-generates `/openapi.json`).
- **Per-stage failure diagnosis tag UI** — deferred to Phase 5 (FBCK-05). Phase 1 only locks its presence in the trace schema (D-47) and the API contract (D-23 / `POST /feedback` body field).
- **Cross-encoder reranker** — deferred to v2 (V2-RANK-01); Phase 1 ADR 007 captures the v2 direction only.
- **Streaming responses, auth/multi-tenant, multi-modal input, agentic multi-hop** — all v2 / out of scope per PROJECT.md and REQUIREMENTS.md. Phase 1 does not produce ADRs for these (PROJECT.md "Out of Scope" is the canonical record).

</deferred>

---

*Phase: 1-Research & Design Artifacts*
*Context gathered: 2026-05-04*
*Mode: --auto (recommended decisions auto-selected and logged inline above)*
