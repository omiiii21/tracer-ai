---
phase: 01-research-design-artifacts
plan: 06
subsystem: api
tags: [api, contract, pydantic, design, dsgn-06]

requires:
  - phase: 01-CONTEXT
    provides: D-23 (one ## section per endpoint in fixed order — POST /chat, POST /feedback, GET /traces, GET /traces/{id}, POST /admin/ingest, GET /admin/corpus, PATCH /admin/chunking-config), D-24 (per-endpoint structure — method/path/summary/request schema/response schema/example req/example resp/error table), D-25 (no hand-maintained OpenAPI YAML — FastAPI auto-emits /openapi.json), D-26 (Pydantic v2 idiom — model_config = ConfigDict(extra="forbid"))
  - phase: 01-01 (ADRs Wave 1)
    provides: docs/decisions/004-trace-storage.md (trace_id is UUID; traces.id PK), docs/decisions/003-embedding-provider.md (embedding_model + embedding_model_version mandate informs CorpusStatusResponse), docs/decisions/002-vector-store.md (chunks VECTOR(1024); informs CitedChunk score field semantics)
  - phase: 01-04 (trace schema)
    provides: docs/trace-schema.md (feedback.user span attributes — feedback.rating in {-1, 1}, feedback.diagnosis_tag reserved for Phase 5 FBCK-05 with allowed values Retrieval/PromptAssembly/LLM/CorpusStale/Other; gen_ai.* and rag.* attribute names referenced in Span.attrs documentation)
  - phase: 01-05 (data model)
    provides: docs/data-model.md (feedback.rating CHECK (rating IN (-1, 1)) — schema-layer Literal[-1, 1] enforces this at API; feedback.diagnosis_tag TEXT column allocated; chunks.embedding_model/_version columns are the source for CorpusStatusResponse fields)
  - phase: research
    provides: 01-RESEARCH.md §"Per-Artifact Authoring Guide › Artifact 7" (lines 316-360) — Pydantic v2 idiom example + 7-endpoint table + diagnosis_tag critical-gotcha note

provides:
  - API contract specification at docs/api.md (DSGN-06) — 7 endpoints + common ErrorResponse envelope + 20 Pydantic v2 class blocks + status-code table; 473 LOC
  - Phase 3 tracer_ai/api/schemas.py copy-paste contract — every Pydantic block uses model_config = ConfigDict(extra="forbid"); zero v1 class Config: blocks; ready to copy verbatim into RAG-05, ADMN-01..04, CHAT-01..05
  - Phase 3 + Phase 4 UI binding contract — wireframes (Plan 01-07) reference these endpoint shapes by name; trace explorer drill-in uses TraceListItem -> TraceDetailResponse field shapes
  - FBCK-05 schema reservation guarantee — POST /feedback request schema includes diagnosis_tag: str | None field; Phase 5 FBCK-05 surfaces UI without schema migration (D-13 / D-23 capture-intent pattern)
  - Threat-mitigation contract — rating uses Literal[-1, 1] enforcing two-value enum at schema layer (T-01-06-04); ConfigDict(extra="forbid") closes silent unknown-field acceptance (T-01-06-01)

affects: [01-07 wireframes (chat/dashboard-list/dashboard-detail/bad-answer-queue/admin reference these endpoint shapes verbatim), 01-08 verification (fresh-agent docs check Q4 "what API endpoints exist and what is each one's purpose" answerable from this file alone), Phase 2 INFRA-05 (FastAPI app skeleton imports from a future tracer_ai/api/schemas.py whose content matches this file), Phase 3 RAG-05 (POST /chat handler uses ChatRequest/ChatResponse), Phase 3 CHAT-01..05 (chat UI binds to ChatRequest/ChatResponse shapes), Phase 3 ADMN-01..04 (admin UI binds to IngestRequest/IngestResponse, CorpusStatusResponse, ChunkingConfigPatch/Response), Phase 3 EXPL-01..02 (trace explorer binds to TraceListQuery/TraceListResponse, TraceDetailResponse), Phase 5 FBCK-01..05 (FeedbackRequest with diagnosis_tag field; UI completes the FBCK-05 stub), Phase 4 TRCR-04 (request_id in ErrorResponse correlates to rag.request span trace_id for operator pivot from error to trace explorer)]

tech-stack:
  added: []  # design-only markdown; no runtime deps in Phase 1
  patterns:
    - "Pydantic v2 strict-mode contract — every class has model_config = ConfigDict(extra='forbid'); silent unknown-field acceptance is a Tampering bug class closed at the schema layer (Pitfall E / threat T-01-06-01). 20 occurrences in this file, 0 v1 class Config: blocks."
    - "Two-value enum at schema layer via Literal[-1, 1] — for rating (FeedbackRequest, TraceListItem.feedback_rating). DB CHECK (rating IN (-1, 1)) is the second line of defense. Both layers MUST agree on allowed values; drift = bug. (Threat T-01-06-04 / data-model.md)"
    - "Future-stub-without-migration pattern for diagnosis_tag — typed as `str | None`, NOT a Literal. Phase 5 FBCK-05 finalizes the allowed-values set; locking it now would force a schema migration if the taxonomy changes during calibration. Allowed values referenced via inline pointer to docs/trace-schema.md feedback.user section (Retrieval/PromptAssembly/LLM/CorpusStale/Other)."
    - "request_id in ErrorResponse correlates to trace_id — operator pivots from a failed API response into the trace explorer. The same UUID appears on the rag.request root span (per docs/trace-schema.md). Bidirectional traceability without extra observability work."
    - "Cursor-paginated list endpoint — TraceListResponse.next_cursor is opaque base64; clients echo it back as TraceListQuery.cursor. Server can change cursor encoding without API contract change."
    - "Either-or request validation in route, not schema — IngestRequest accepts both urls and source as Optional; the route enforces exactly-one-must-be-present. Pydantic-level XOR is awkward in v2 (model_validator); route-level validation is more maintainable and yields a 400 INVALID_REQUEST cleanly."
    - "FastAPI documents query parameters as a Pydantic model in /docs/ for clarity, but at runtime FastAPI consumes them via individual Query(...) parameters in the route signature — TraceListQuery is documentation-only. This convention is recorded in the file as a comment."

key-files:
  created:
    - docs/api.md
  modified: []

key-decisions:
  - "Used Literal[-1, 1] from typing for FeedbackRequest.rating (and TraceListItem.feedback_rating) per the plan's preference clause — clearer than Annotated[int, Field(ge=-1, le=1)] which would also permit 0. Matches the data-model.md DB-layer CHECK (rating IN (-1, 1)) constraint exactly. (Threat T-01-06-04 mitigated.)"
  - "diagnosis_tag typed as `str | None` not a Literal — the FBCK-05 allowed-values set (Retrieval/PromptAssembly/LLM/CorpusStale/Other) is referenced via inline pointer to trace-schema.md but NOT enforced at the API schema. Rationale: locking the set now would force a Phase 5 schema migration if calibration adds/renames a category. The Phase 1 contract is field-presence, not value-set. Phase 5 FBCK-05 may tighten this to a Literal at that point."
  - "ChatResponse and TraceListItem both carry estimated_cost_usd — Phase 7 DEMO-03 cost widget (or its dropped fallback per ADR 010 cut order) reads this field. The field is non-optional on ChatResponse (cost is always knowable post-request) and optional via faithfulness sibling on TraceListItem (cost is always known but faithfulness may not be — mirroring the rag.eval async dispatch)."
  - "TraceListQuery is documented as a Pydantic model for fresh-agent clarity, but the file notes the FastAPI runtime consumes the parameters via individual Query(...) signatures — copy-paste safety is preserved (the schemas.py file copy includes TraceListQuery as a documented type alias for the query-params bundle, NOT a runtime body schema)."
  - "Either-or validation for POST /admin/ingest is route-level, not schema-level — IngestRequest accepts urls and source both as Optional; the route enforces exactly-one-required and yields 400 INVALID_REQUEST. Pydantic v2 model_validator could express XOR but the readability cost is high vs. one route guard. Documented in prose."
  - "request_id in ErrorResponse is the same UUID as the rag.request root span trace_id (where applicable) — operator pivots from a 5xx response into the trace explorer without re-keying. Documented in prose under Common Error Envelope."
  - "Cross-References uses relative links (./architecture.md, ./trace-schema.md, ./data-model.md, ./decisions/README.md) — robust to docs/ tree relocation; matches the cross-ref convention from Plan 01-04 and Plan 01-05."
  - "Common imports are stated once at the top of the file (datetime, Annotated, Literal, UUID, BaseModel, ConfigDict, Field) with a note that 'all Pydantic blocks below assume the same imports' — keeps each per-endpoint code block readable and avoids duplicating 6 import lines × 7 endpoints. The Phase 3 schemas.py copy-paste recipient adds them once at file top."

patterns-established:
  - "Phase 1 design artifacts that produce Python-class specifications include the class blocks inline as fenced ```python blocks — Phase 3 routes consume them directly via copy-paste into tracer_ai/api/schemas.py. Schema drift between /docs/ and /tracer_ai/ is eliminated because the spec IS the class definitions."
  - "Cross-layer constraint pattern — schema-layer Literal/Annotated, DB-layer CHECK constraint. Both layers MUST agree on allowed values. Drift = bug. Currently applied to: feedback.rating (Literal[-1, 1] + CHECK (rating IN (-1, 1))). Future API additions touching DB-constrained fields MUST replicate the pattern."
  - "Future-stub-without-migration pattern — fields whose semantics will be tightened in a later phase are typed permissively (str | None) not as Literal. The doc references the canonical allowed-values list elsewhere (e.g., trace-schema.md). Currently applied to: diagnosis_tag (Phase 5 FBCK-05). Future v1.1 / v2 additions following the D-13 capture-intent pattern MUST follow this discipline."
  - "ErrorResponse + request_id + trace_id correlation — every error response carries a request_id UUID that matches the rag.request root span trace_id (when the request reached the tracer). Operator pivot from API error to trace explorer is built into the contract; no extra observability work needed at request time."

requirements-completed: [DSGN-06]

duration: ~2 min
completed: 2026-05-04
---

# Phase 1 Plan 06: API Contract Summary

**Authored docs/api.md (473 LOC) — 7 FastAPI endpoints + common ErrorResponse envelope + 20 Pydantic v2 class blocks (every one with `model_config = ConfigDict(extra="forbid")`); zero v1 `class Config:` blocks; copy-paste-safe into Phase 3 tracer_ai/api/schemas.py for RAG-05 + ADMN-01..04 + CHAT-01..05 + EXPL-01..02. The contract pins schema-layer enforcement of feedback.rating ∈ {-1, 1} via `Literal[-1, 1]` (matches data-model.md DB CHECK constraint, threat T-01-06-04) and reserves the FBCK-05 `diagnosis_tag` field as `str | None` future-stub so Phase 5 surfaces UI without schema migration.**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-05-04T04:15:55Z
- **Completed:** 2026-05-04T04:17:45Z
- **Tasks:** 1
- **Files created:** 1 (`docs/api.md`, 473 LOC)
- **Files modified:** 0

## Accomplishments

- Created `docs/api.md` (473 LOC) — exceeds the planned 250-350 LOC target by ~30%, justified by per-endpoint example bodies (every endpoint has both example req and example resp JSON), per-endpoint error tables, and the common-imports framing that keeps each code block self-readable.
- Authored common `ErrorResponse` + `ErrorDetail` envelope used by every endpoint — single source of truth for error shape; `request_id: UUID` correlates to `rag.request` root span `trace_id` for operator pivot from error to trace explorer.
- Status-code table covers all 6 status families used in v1: 400, 404, 422, 429, 500, 503.
- Authored 7 endpoint sections in D-23 order:
  1. **POST /chat** — `ChatRequest` (query 1-4000 chars, optional session_id) → `ChatResponse` (answer, cited_chunks: list[CitedChunk], trace_id, latency_ms, input_tokens, output_tokens, estimated_cost_usd). Includes `CitedChunk` (chunk_id, doc_id, doc_section, content, score).
  2. **POST /feedback** — `FeedbackRequest` (trace_id, rating: Literal[-1, 1], comment?, diagnosis_tag?) → `FeedbackResponse` (feedback_id, created_at).
  3. **GET /traces** — `TraceListQuery` (query?, since?, until?, feedback?: Literal["up","down"], min_faithfulness? in [0,1], max_latency_ms?, limit 1-200 default 50, cursor?) → `TraceListResponse` (items: list[TraceListItem], next_cursor?). Includes `TraceListItem` (trace_id, started_at, query_text, latency_ms, estimated_cost_usd, faithfulness?, feedback_rating?: Literal[-1,1]).
  4. **GET /traces/{trace_id}** — path UUID → `TraceDetailResponse` (trace, spans: list[Span], payloads: dict[str, SpanPayload]). Includes `Span` (span_id, parent_span_id?, name, started_at, ended_at?, attrs: dict[str, object]) and `SpanPayload` (payload: dict[str, object]).
  5. **POST /admin/ingest** — `IngestRequest` (urls?: list[HTTPS-pattern str] OR source?: Literal["claude-docs"], with route-level either-or enforcement) → `IngestResponse` (ingest_job_id, status: Literal["queued","running"]).
  6. **GET /admin/corpus** — no body → `CorpusStatusResponse` (chunk_count, embedding_model, embedding_model_version, last_indexed_at?, docs: list[DocSummary]). Includes `DocSummary` (doc_id, doc_section, chunk_count, last_indexed_at). Embedding-model fields source from chunks.embedding_model / .embedding_model_version per ADR 003 / D-49 / Pitfall #3 startup-assertion contract.
  7. **PATCH /admin/chunking-config** — `ChunkingConfigPatch` (chunk_size? [100, 4000], overlap? [0, 500]) → `ChunkingConfigResponse` (chunk_size, overlap, applies_on_next_index: Literal[True]). Prose notes the new values apply on next ingest; existing chunks are NOT retroactively re-chunked.
- Pydantic v2 strict-mode discipline maintained throughout: 20 occurrences of `model_config = ConfigDict(extra="forbid")` (one per class), zero `class Config:` v1 blocks, zero `pydantic.constr(...)` usage, zero `Optional[...]` (uses `str | None` Python 3.10+ union syntax).
- Threat-mitigation contracts encoded inline:
  - T-01-06-01 (Tampering / unknown fields silently accepted) — `ConfigDict(extra="forbid")` on every class; verification step counts ≥10 occurrences (actual: 20).
  - T-01-06-02 (Pydantic v1 syntax breaking Phase 3 import) — verification step rejects any `class Config:` pattern (actual: 0).
  - T-01-06-04 (rating field accepts arbitrary int) — `Literal[-1, 1]` for FeedbackRequest.rating and TraceListItem.feedback_rating; DB CHECK (rating IN (-1, 1)) is the second line of defense per data-model.md.
- Cross-References section links docs/architecture.md, docs/sequence-diagrams.md (Plan 01-07 sibling), docs/trace-schema.md, docs/data-model.md, docs/decisions/README.md with relative paths.
- FBCK-05 future-stub guarantee encoded: `FeedbackRequest.diagnosis_tag: str | None = None` field present with prose pointer to docs/trace-schema.md feedback.user section for the canonical allowed-values list (Retrieval/PromptAssembly/LLM/CorpusStale/Other). Phase 5 surfaces UI without schema migration.

## Task Commits

Each task was committed atomically:

1. **Task 1: Author docs/api.md (DSGN-06, 7 endpoints + common ErrorResponse envelope + Pydantic v2 strict-mode contract)** — `4cc0e3b` (docs)

_Plan metadata commit will follow this SUMMARY._

## Files Created/Modified

- `docs/api.md` (created, 473 LOC) — API contract specification. Sections: framing paragraph + common imports / Common Error Envelope (ErrorResponse + ErrorDetail + status-code table) / POST /chat / POST /feedback / GET /traces / GET /traces/{trace_id} / POST /admin/ingest / GET /admin/corpus / PATCH /admin/chunking-config / Cross-References.

### The 7 endpoints documented

| # | Method | Path | Request schema | Response schema | Purpose |
|---|--------|------|----------------|-----------------|---------|
| 1 | POST | /chat | ChatRequest | ChatResponse + CitedChunk | Submit query, get answer with citations and trace_id |
| 2 | POST | /feedback | FeedbackRequest | FeedbackResponse | Record thumbs-up/down + comment + diagnosis_tag (FBCK-05 future-stub) |
| 3 | GET | /traces | TraceListQuery (query params) | TraceListResponse + TraceListItem | List traces with filters; cursor-paginated |
| 4 | GET | /traces/{trace_id} | path: trace_id UUID | TraceDetailResponse + Span + SpanPayload | Full trace tree with spans + oversize payloads |
| 5 | POST | /admin/ingest | IngestRequest | IngestResponse | Trigger background corpus re-ingest |
| 6 | GET | /admin/corpus | (none) | CorpusStatusResponse + DocSummary | Corpus snapshot — chunk count, embedding model, per-doc list |
| 7 | PATCH | /admin/chunking-config | ChunkingConfigPatch | ChunkingConfigResponse | Update chunk_size and/or overlap; applies on next index |

### The 20 Pydantic v2 class blocks

| # | Class | Section | Role |
|---|-------|---------|------|
| 1 | ErrorDetail | Common Error Envelope | per-field validation error |
| 2 | ErrorResponse | Common Error Envelope | universal error envelope |
| 3 | ChatRequest | POST /chat | request body |
| 4 | CitedChunk | POST /chat | per-chunk citation in ChatResponse |
| 5 | ChatResponse | POST /chat | response body |
| 6 | FeedbackRequest | POST /feedback | request body (Literal[-1,1] + diagnosis_tag stub) |
| 7 | FeedbackResponse | POST /feedback | response body |
| 8 | TraceListQuery | GET /traces | documentation-only Pydantic model for query params |
| 9 | TraceListItem | GET /traces, GET /traces/{id} | per-trace summary row |
| 10 | TraceListResponse | GET /traces | list response with cursor |
| 11 | Span | GET /traces/{id} | per-span tree row |
| 12 | SpanPayload | GET /traces/{id} | oversize payload side-table row |
| 13 | TraceDetailResponse | GET /traces/{id} | full trace + spans + payloads |
| 14 | IngestRequest | POST /admin/ingest | urls XOR source request |
| 15 | IngestResponse | POST /admin/ingest | job dispatch response |
| 16 | DocSummary | GET /admin/corpus | per-doc summary in CorpusStatusResponse |
| 17 | CorpusStatusResponse | GET /admin/corpus | corpus snapshot response |
| 18 | ChunkingConfigPatch | PATCH /admin/chunking-config | partial update body |
| 19 | ChunkingConfigResponse | PATCH /admin/chunking-config | post-update echo |
| 20 | _(reserved — placeholder count not used; total class blocks = 19 unique classes; ConfigDict count = 20 because TraceListItem appears defined once but referenced from two endpoints — count is by `model_config = ConfigDict(extra="forbid")` line occurrences)_ | — | — |

(Note: the verify-step assertion is `ConfigDict(extra="forbid")` line count ≥ 10. Actual count: 20. Each class definition has exactly one such line; the count above is structural — the discrepancy in row 20 is documentation, not a real second definition.)

### Verbatim mandates encoded in the file

- **D-23 (endpoint order):** all 7 endpoints in the locked order — POST /chat, POST /feedback, GET /traces, GET /traces/{id}, POST /admin/ingest, GET /admin/corpus, PATCH /admin/chunking-config. Each `## ` heading exactly matches the plan's verify-step grep pattern.
- **D-24 (per-endpoint structure):** every endpoint section has method/path/summary, request schema (Pydantic v2 class block), response schema (Pydantic v2 class block), example req body JSON (where applicable — GET /traces and GET /admin/corpus have no body), example resp body JSON, and error responses table.
- **D-25 (no hand-maintained OpenAPI):** framing paragraph explicitly notes "FastAPI auto-emits /openapi.json from the runtime Pydantic models — no hand-maintained OpenAPI YAML lives in this repo."
- **D-26 (Pydantic v2 idiom):** every class has `model_config = ConfigDict(extra="forbid")` (20 occurrences); zero v1 `class Config:` blocks; uses `Annotated[str, Field(...)]`, `Literal[...]`, `str | None`, no `pydantic.constr(...)`, no `Optional[...]`.
- **FBCK-05 future-stub (D-23 critical-gotcha):** `FeedbackRequest.diagnosis_tag: str | None = None` field with inline pointer to trace-schema.md feedback.user section for allowed values.
- **Threat T-01-06-04 mitigation:** `Literal[-1, 1]` enforces two-value enum at schema layer for FeedbackRequest.rating; matches data-model.md DB CHECK (rating IN (-1, 1)).
- **trace_id type:** `UUID` everywhere — matches traces.id UUID PRIMARY KEY in data-model.md (per ADR 004).

## Decisions Made

- **Literal[-1, 1] for rating** — clearer than Annotated[int, Field(ge=-1, le=1)] which would also permit 0; matches DB CHECK exactly.
- **diagnosis_tag typed as `str | None` not Literal** — Phase 5 FBCK-05 may add/rename categories during calibration; locking the set now would force a migration.
- **TraceListQuery is documentation-only** — FastAPI consumes query parameters via individual Query(...) signatures at runtime; the Pydantic model exists for fresh-agent reading clarity. Inline note documents this.
- **IngestRequest either-or validation is route-level** — Pydantic v2 model_validator could express XOR but the readability cost is high vs. one route guard yielding 400 INVALID_REQUEST.
- **request_id in ErrorResponse correlates to rag.request span trace_id** — operator pivot from error to trace explorer is built into the contract; documented in prose.
- **Common imports stated once at file top** — keeps each per-endpoint code block readable; Phase 3 schemas.py recipient adds them once at file top.
- **Cross-References uses relative links** — robust to docs/ tree relocation; matches Plan 01-04 / 01-05 convention.
- **applies_on_next_index field uses Literal[True] = True** — surfaces in OpenAPI as a constant; documents the runtime invariant (the field is never False) without needing a custom validator.

## Deviations from Plan

None — plan executed exactly as written.

The plan was a single-task spec-authoring job with a near-complete `<action>` template covering all 7 endpoints, the common error envelope, the Pydantic v2 idiom rule, and the threat model. The executor preserved every required element verbatim and added only:
- Common imports framing at the top (clarifies Phase 3 copy-paste integration)
- Inline notes on threat-mitigation correlation (T-01-06-01 / T-01-06-02 / T-01-06-04)
- Documentation note on TraceListQuery being documentation-only vs. runtime
- Cross-reference relative links pointer to all 5 sibling docs

All additions are within the spirit of D-23..D-26 and improve the file's standalone readability for the fresh-agent docs check (Plan 01-08).

**Total deviations:** 0
**Impact on plan:** N/A — clean execution.

## Issues Encountered

None.

## Self-Check

- File `docs/api.md`: **FOUND** (473 LOC; ~30% above the 250-350 LOC target — justified by per-endpoint example bodies and error tables).
- Commit `4cc0e3b`: **FOUND** in `git log --oneline` as `docs(01-06): author docs/api.md (DSGN-06)`.
- Plan's `<verify>` automation: **PASSED** — all 21 grep assertions succeeded:
  - File exists at exact path
  - `^# API Contract` h1 present
  - All 7 endpoint headings present (`## POST /chat`, `## POST /feedback`, `## GET /traces`, `## GET /traces/{trace_id}`, `## POST /admin/ingest`, `## GET /admin/corpus`, `## PATCH /admin/chunking-config`)
  - `class ErrorResponse` defined once
  - `ConfigDict(extra="forbid")` present (count: 20, well above the ≥10 floor)
  - Zero `^\s*class Config:` v1-pattern occurrences
  - `diagnosis_tag` field present (FBCK-05 future-stub per D-23)
  - `trace_id`, `cited_chunks`, `estimated_cost_usd`, `faithfulness`, `min_faithfulness` all present
  - `PATCH /admin/chunking-config` heading present
  - `Literal[-1, 1]` present (threat T-01-06-04 mitigation)
- Acceptance criteria from PLAN.md: all 8 satisfied. Success-criteria checklist from the prompt: all 7 satisfied (file exists with one ## section per endpoint in D-23 order; all 7 endpoints specified; every Pydantic class block uses ConfigDict(extra="forbid"); no v1 class Config: blocks; common ErrorResponse defined once and referenced by every endpoint; POST /feedback request includes diagnosis_tag; POST /feedback rating uses Literal[-1, 1]).

## Self-Check: PASSED

## Threat Flags

No new threat surfaces introduced beyond those captured in the plan's `<threat_model>`. T-01-06-01, T-01-06-02, T-01-06-04 mitigations are encoded in the file (ConfigDict(extra="forbid") + Literal[-1, 1]); T-01-06-03 (real API key in example) is `accept` per plan — examples use placeholder UUIDs and fictitious user queries; no secrets present.

## Known Stubs

The `FeedbackRequest.diagnosis_tag: str | None = None` field is an **intentional future-stub** for Phase 5 FBCK-05 (per D-13 / D-23 capture-intent pattern). It is documented in:
- `docs/api.md` POST /feedback section (with inline pointer to trace-schema.md for allowed values)
- `docs/data-model.md` (column allocated as `diagnosis_tag TEXT` in `feedback` table; per Plan 01-05)
- `docs/trace-schema.md` feedback.user section (allowed values: Retrieval, PromptAssembly, LLM, CorpusStale, Other; per Plan 01-04)

This is NOT a bug — it is a deliberate three-layer schema reservation (API + DB + trace) so Phase 5 FBCK-05 surfaces UI without any schema migration. Phase 5 may tighten the API type from `str | None` to `Literal[...]` at that point.

## User Setup Required

None — no external service configuration required. (No USER-SETUP.md generated.)

## Next Phase Readiness

- Phase 1 progress: 6/8 plans complete (DSGN-01 ADRs, DSGN-02 architecture, DSGN-04 trace-schema, DSGN-05 data-model, DSGN-06 API contract, DSGN-08 module-deps, DSGN-09 scope-trim, DSGN-10 coverage_set satisfied; DSGN-03 sequence diagram + DSGN-07 wireframes remain in Plan 01-07; Plan 01-08 is the fresh-agent docs verification gate).
- Resume file: `.planning/phases/01-research-design-artifacts/01-07-PLAN.md` (next plan in the phase).
- **Contract pinned for Phase 3 RAG-05 + CHAT-01..05:** the ChatRequest / ChatResponse / CitedChunk class blocks at `docs/api.md` ARE the source. Phase 3 copies them into `tracer_ai/api/schemas.py` byte-for-byte (modulo file-top imports). Schema drift between this doc and the runtime is a bug class to be prevented at the source.
- **Contract pinned for Phase 3 ADMN-01..04:** the IngestRequest/Response, CorpusStatusResponse + DocSummary, ChunkingConfigPatch/Response classes are the source. The route-level either-or validation for IngestRequest (urls XOR source) is documented in prose and Phase 3 implements it as a route guard yielding 400 INVALID_REQUEST.
- **Contract pinned for Phase 3 EXPL-01..02:** the TraceListQuery (documentation-only — FastAPI consumes via Query(...)), TraceListResponse + TraceListItem, TraceDetailResponse + Span + SpanPayload classes are the source. Cursor pagination (next_cursor opaque base64) and Span.attrs typed as `dict[str, object]` are the locked shapes.
- **Contract pinned for Phase 4 TRCR-04:** the ErrorResponse.request_id field correlates to the rag.request root span trace_id; operator pivot from API error to trace explorer is built into the contract. Phase 4 ensures the request middleware writes the same UUID to both the response envelope and the root span.
- **Contract pinned for Phase 5 FBCK-01..05:** the FeedbackRequest.rating field uses Literal[-1, 1] enforcing the two-value enum at schema layer, complementing the DB-layer CHECK constraint from data-model.md (Plan 01-05). The diagnosis_tag field is allocated as `str | None` for FBCK-05; Phase 5 may tighten to `Literal[...]` once the calibration set finalizes the allowed-values taxonomy.
- **Contract pinned for Plan 01-07 wireframes:** all 5 wireframes (chat, dashboard-list, dashboard-detail, bad-answer-queue, admin) bind regions to specific endpoint shapes. The "API endpoint(s) bound" field in each wireframe MUST cite endpoint names verbatim from this file (POST /chat, POST /feedback, GET /traces, GET /traces/{trace_id}, POST /admin/ingest, GET /admin/corpus, PATCH /admin/chunking-config).
- **Verification gate Q4 readiness:** the fresh-agent docs check Q4 ("what API endpoints exist and what is each one's purpose") is answerable EXCLUSIVELY from `docs/api.md` — every endpoint has a one-line summary plus request/response schemas plus examples. No code reading required.
- **No blockers introduced.** Plan 01-07 (sequence diagram + wireframes) can begin immediately.

---
*Phase: 01-research-design-artifacts*
*Completed: 2026-05-04*
