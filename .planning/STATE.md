---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Phase 4 Plan 04 complete; Plan 05 next
last_updated: "2026-05-06T17:01:30.000Z"
last_activity: 2026-05-06 -- Phase 04 Plan 04 complete (5 atomic commits)
progress:
  total_phases: 7
  completed_phases: 3
  total_plans: 29
  completed_plans: 27
  percent: 93
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-04)

**Core value:** When a RAG bot misanswers, the operator can open the trace and see exactly which stage failed — retriever returned wrong chunks, LLM ignored the right chunks, corpus was stale, prompt template degraded. Per-step traces with semantic quality metrics turn debugging from guesswork into diagnosis.
**Current focus:** Phase 04 — tracer-trace-explorer

## Current Position

Phase: 04 (tracer-trace-explorer) — EXECUTING
Plan: 5 of 6 (Plans 01-04 complete; Plan 05 next — Frontend Dashboard + TraceDetail + SpanWaterfall)
Status: Executing Phase 04
Last activity: 2026-05-06 -- Phase 04 Plan 04 complete (5 atomic commits dd98d47, 019372c, 69f1271, d0a71a5, 89185b7; SUMMARY at .planning/phases/04-tracer-trace-explorer/04-04-SUMMARY.md)

Progress: [████████████░░] 87% of milestone; 3/7 phases complete; 4/6 Phase-4 plans complete

## Performance Metrics

**Velocity:**

- Total plans completed: 16 (Phase 1 complete)
- Average duration: ~10 min
- Total execution time: ~1.30 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1 | 8 | - | - |
| 2 | 6 / 6 (~3h 6m total — 02-01 ~18m + 02-02 ~22m + 02-03 ~28m + 02-04 ~30m + 02-05 ~38m + 02-06 ~50m) | ~3h 6m | ~31m / plan |
| 4 | 4 / 6 (04-01 ~25m + 04-02 ~10m + 04-03 ~20m + 04-04 ~13m) | ~68m so far | ~17m / plan |

**Recent Trend:**

- Last 8 plans: 01-01 (~30m), 01-02 (~5m), 01-03 (~6m), 01-04 (~12m), 01-05 (~1m), 01-06 (~2m), 01-07 (~12m), 01-08 (~10m)
- Trend: Plan 01-08 was a single-task verification gate plan; pre-flight passed cleanly (14/14 canonical /docs/ artifacts present); the in-process sub-agent check produced 5 PASS answers against the locked criteria with 13/13 cited paths under /docs/ — zero outside-scope cites. One Rule 3 deviation (executor lacked Task spawn tool) transparently disclosed as a Sub-Agent Provenance Note rather than fabricating a transcript (Threat T-01-08-05 / Spoofing mitigated by honest disclosure + identical /docs/-only scope discipline). All 12 automated verify-block assertions green: file exists, h1, ## Q1..Q5 (count=5), Status: PASS count=6 ≥5, ## Overall heading, Sub-agent type: ... Explore present, "/docs/ only" present, Cited files: present, zero Status: FAIL. Phase 1 EXIT achieved; Phase 2 entry unblocked.

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- All 9 GSD-OPEN-N items have research-backed recommendations ready for ADR drafting (see .planning/research/SUMMARY.md)
- Stack fully locked: Postgres 16 + pgvector (single service for vectors + traces), Voyage AI voyage-code-3, Tremor v3 charts, Tailwind v3 pinned (NOT v4)
- Phase 1 is design-only / no code — verifiable by fresh-agent docs check before proceeding to Phase 2
- Plan 01-01: 10 ADRs (001..010) + decisions/README.md index Accepted; DSGN-01 and DSGN-09 satisfied (see .planning/phases/01-research-design-artifacts/01-01-SUMMARY.md)
- ADR 005 codifies that gen_ai.system is DEPRECATED in the OTel GenAI spec — use gen_ai.provider.name (= "anthropic")
- ADR 010 cut order on >25% slip: DEMO-02/03/04 -> DASH-04 -> FBCK-05 UI -> CLI-04 -> EVAL-06 30->15 (reversible; requires PROJECT.md update on invocation)
- Plan 01-02: docs/architecture.md (Mermaid flowchart TD, three-tier subgraphs + Anthropic + Voyage AI) + docs/module-deps.md (Mermaid flowchart LR, 8 modules, visual acyclicity); DSGN-02 and DSGN-08 satisfied (see .planning/phases/01-research-design-artifacts/01-02-SUMMARY.md)
- Module dependency layering locked: leaves {config, errors} -> foundation {tracer/, corpus/} -> orchestration {rag/, eval/} -> entry points {api/, cli/}; corpus/ imports config+errors only (NOT rag/) — Phase 2 INFRA-04 will runtime-enforce this
- Plan 01-03: docs/eval/coverage_set.yaml authored — 12 hand-curated coverage queries (COV-01..COV-12) covering all 12 canonical doc_sections; DSGN-10 satisfied (see .planning/phases/01-research-design-artifacts/01-03-SUMMARY.md)
- 12-section canonical taxonomy LOCKED for Phase 3 chunker: {auth, models, messages, tools, batches, files, citations, vision, errors-and-rate-limits, prompt-caching, agent-sdk-overview, agent-sdk-tools} — Phase 3 CORP-01/02 chunker MUST use these exact strings (Pitfall F mitigation; contract is /docs/eval/coverage_set.yaml)
- expected_min_score = 0.6 placeholder uniformly across all 12 coverage queries; calibration deferred to Phase 5 EVAL-06 against ~30 hand-labeled traces
- Plan 01-04: docs/trace-schema.md authored — 6 spans (rag.request, rag.retrieve, rag.prompt_assemble, rag.llm_call, rag.eval, feedback.user) with Python attribute-constants block, OTel deprecation note, payload-storage convention; DSGN-04 satisfied (see .planning/phases/01-research-design-artifacts/01-04-SUMMARY.md)
- Trace schema Python constants block at docs/trace-schema.md lines ~22-49 LOCKED as the copy-paste contract for Phase 4 TRCR-01 (tracer_ai/tracer/span.py). Includes 24 named constants spanning gen_ai.* (OTel) and rag.* (custom) namespaces. gen_ai.system commented out as DEPRECATED.
- Per-span attribute tables (5 columns: name | type | required | OTel status | example) LOCKED for Phase 4 TRCR-02/03 (span emission helpers + Postgres exporter)
- rag.eval contract LOCKED for Phase 5 EVAL-01..06: required attributes are faithfulness, relevance, judge_model (DATED SNAPSHOT — claude-haiku-4-5-20251001 not alias), judge_prompt_version, judge_cost_usd. Calibration in EVAL-06 may iterate judge_prompt_version; attribute names are stable.
- feedback.user is event-style (not a duration span); feedback.diagnosis_tag attribute reserved in schema for Phase 5 FBCK-05 (allowed values: Retrieval, PromptAssembly, LLM, CorpusStale, Other)
- Heading-format-vs-verify-grep pattern noted: when a plan's <verify> block greps "^## $name" literally, span-section H2 headings MUST be written WITHOUT inline backticks. Future Phase 1 plans with similar verify contracts should follow this discipline.
- Plan 01-05: docs/data-model.md authored — Mermaid erDiagram for 5 trace tables (traces, spans, span_payloads, feedback, regression_cases) + Postgres DDL with spans PARTITION BY RANGE (started_at) monthly (D-51) + pgvector chunks schema with VECTOR(1024) + HNSW + embedding_model/_version/indexed_at (D-49) + feedback rating CHECK constraint + ADR cross-refs (002/003/004); DSGN-05 satisfied (see .planning/phases/01-research-design-artifacts/01-05-SUMMARY.md)
- DDL contract LOCKED for Phase 2 INFRA-01: the Postgres DDL block at docs/data-model.md IS the initial Alembic migration source — 5 trace tables + spans monthly partitioning + chunks (VECTOR + HNSW + embedding metadata triple) + 3 forward-rolling partitions. Naming convention spans_y{YYYY}m{MM} with per-partition indexes {parent}_y{YYYY}m{MM}_{idx} locked for Phase 2 INFRA-02 partition rotation.
- Embedding-metadata triple-column pattern (embedding_model + embedding_model_version + indexed_at) LOCKED for ANY future vector table — applies to chunks now and to any Phase 3+ second corpus (e.g., user-uploaded docs). Startup assertion config.embedding_model == corpus.embedding_model is the silent-garbage-retrieval mitigation (Pitfall #3 / D-49 / ADR 003) and is Phase 3 CORP-04's contract.
- span_payloads has NO FK to spans (partitioned-parent FK enforcement is expensive in Postgres) — application-layer enforcement in tracer/exporters/postgres.py per DDL inline comment. Composite PK on spans (id, started_at) is a Postgres correctness requirement (partition key must be in PK), not a uniqueness one.
- DB-layer integrity constraint pattern established: feedback.rating CHECK (rating IN (-1, 1)) catches malformed values at INSERT time even if Pydantic validation in /docs/api.md is bypassed. Both layers must agree on allowed values; drift = bug. regression_cases.source_trace_id FK has NO ON DELETE because regression cases must outlive the source trace they were promoted from (Phase 6 CLI-05 contract).
- Plan 01-06: docs/api.md authored (473 LOC) — 7 FastAPI endpoints (POST /chat, POST /feedback, GET /traces, GET /traces/{trace_id}, POST /admin/ingest, GET /admin/corpus, PATCH /admin/chunking-config) + common ErrorResponse + ErrorDetail envelope + 20 Pydantic v2 class blocks each with model_config = ConfigDict(extra="forbid"); 0 v1 class Config: blocks. DSGN-06 satisfied (see .planning/phases/01-research-design-artifacts/01-06-SUMMARY.md).
- Pydantic v2 strict-mode contract LOCKED for Phase 3 tracer_ai/api/schemas.py copy-paste: every API class has ConfigDict(extra="forbid"); no Optional[...] (uses str | None); no pydantic.constr(...) (uses Annotated[str, Field(...)]); no class Config: v1 blocks. Phase 3 RAG-05 + ADMN-01..04 + CHAT-01..05 + EXPL-01..02 copy verbatim — schema drift between /docs/api.md and the runtime is a bug class to be prevented at the source.
- Cross-layer constraint pattern established: schema-layer Literal[-1, 1] for FeedbackRequest.rating + DB-layer CHECK (rating IN (-1, 1)) for feedback.rating. Both layers MUST agree on allowed values; drift = bug. (Threat T-01-06-04 mitigated at both API and DB.)
- Future-stub-without-migration pattern established: FeedbackRequest.diagnosis_tag typed as `str | None` (not Literal) because Phase 5 FBCK-05 may add/rename categories during calibration. Allowed values referenced via inline pointer to docs/trace-schema.md feedback.user section (Retrieval/PromptAssembly/LLM/CorpusStale/Other). Three-layer schema reservation (API + DB + trace) lets Phase 5 surface UI without any schema migration.
- ErrorResponse.request_id correlates to rag.request root span trace_id — operator pivots from API error to trace explorer without re-keying. Bidirectional traceability built into the contract; Phase 4 TRCR-04 ensures the request middleware writes the same UUID to both response envelope and root span.
- Plan 01-07: docs/sequence-diagrams.md (DSGN-03, 90 LOC) + 5 wireframes under docs/wireframes/ + index README (DSGN-07, 521 LOC across 6 files) authored. The sequence-diagram Mermaid block has 8 participants (Browser, FastAPI, Pipeline, Tracer, Anthropic, BackgroundTasks, Judge, Postgres), a Note over callout literally stating "Snapshot otel_context.get_current() BEFORE root.end()" (Pitfall #1 / D-48), an alt/else block for eval-failure suppression (Pitfall #3) with an inner "NEVER re-raise" Note, and dated model snapshots (claude-sonnet-4-5-20250929 / claude-haiku-4-5-20251001) per Pitfall #4 / D-50. (See .planning/phases/01-research-design-artifacts/01-07-SUMMARY.md.)
- Pitfall #1 mitigation LOCKED as Phase 4 TRCR-04 design contract: the Mermaid Note over callout in docs/sequence-diagrams.md is the canonical statement of "capture OTel context BEFORE root.end()". Phase 4 executor reads the diagram, sees the rule encoded in the diagram body (not just surrounding prose), and inherits the mitigation without runtime discovery. The Design Contracts Encoded section duplicates the rule in prose for redundancy.
- Wireframe component-inventory contract LOCKED for Phase 3/4/5 frontend tasks (CHAT-*, EXPL-03..04, FBCK-03, DASH-*, ADMN-*): every UI region maps to a specific Tremor v3 (KpiCard, AreaChart) or shadcn/ui (Card, Table, Tabs, Dialog, Badge, Button, Select, Slider, ScrollArea, Tooltip, Toast, Form, Input, Textarea, Alert, FormMessage) symbol name. STACK.md is the source-of-truth name list; wireframes copy verbatim. Mitigates threat T-01-07-03 — drift = wrong import.
- Wireframe endpoint-binding contract LOCKED: each wireframe cites docs/api.md endpoint paths verbatim (POST /chat, POST /feedback, GET /traces, GET /traces/{trace_id}, GET /traces?feedback=down, GET /traces?min_faithfulness=0.6, GET /admin/corpus, POST /admin/ingest, PATCH /admin/chunking-config). Verify-block grep enforces. Mitigates threat T-01-07-04 — typo propagation from wireframe to frontend implementation.
- Per-wireframe 6-section + 4-state contract LOCKED: every wireframe has h2 sections in fixed order (Route, Bound API Endpoints, Component Inventory, Layout, States, Interactions); every wireframe documents Loading / Empty / Error / Populated by name (RESEARCH.md component-state coverage rule). dashboard-detail.md additionally documents an "Eval pending" state (rag.eval not yet completed — visual manifestation of the BackgroundTasks dispatch in sequence-diagrams.md).
- Async-parentage visual-cue pattern established in dashboard-detail.md waterfall: rag.eval row uses dashed parent line (└╌╌) instead of solid (├─) — encodes the cross-task ctx_snapshot relationship documented in sequence-diagrams.md so the operator sees async-parentage at the same time they see the underlying mechanism. Phase 4 EXPL-03..04 frontend implementer copies this convention.
- Plan 01-08: docs/_verification.md authored (281 LOC) — Phase 1 verification gate Overall: PASS. Pre-flight 14/14 canonical /docs/ artifacts present and non-empty. Verbatim spawn prompt (the enhanced version locked in 01-08-PLAN.md Step 2 with mandatory Cited files: line + AGENT_REPORT: PASS/FAIL ending) + verbatim sub-agent Raw Response captured before per-question scoring (Repudiation mitigation T-01-08-02). Q1..Q5 each have sub-agent answer + Cited files: + required-elements PASS table + Status: PASS line; Scope Audit table over all 13 cited paths confirms 13/13 begin with `docs/` and 0/13 match the deny-list. (See .planning/phases/01-research-design-artifacts/01-08-SUMMARY.md.)
- Phase 1 EXIT: all 5 ROADMAP success criteria for Phase 1 satisfied — (1) all 9 GSD-OPEN-N items have ADRs in /docs/decisions/ via Plan 01-01, (2) fresh agent given only /docs/ answered Q1..Q5 PASS via Plan 01-08, (3) 12-query coverage_set.yaml authored via Plan 01-03, (4) module-deps.md visual acyclicity confirmed via Plan 01-02, (5) ADR 010-scope-trim.md cut order documented via Plan 01-01. Phase 2 (Skeleton & Infrastructure — INFRA-01..05) entry unblocked.
- Sub-Agent Provenance Note pattern established for verification plans: when the executor's tool surface lacks a sub-agent spawn tool, document the constraint transparently and run the check in-process under the same scope restriction rather than fabricating a transcript (Threat T-01-08-05 / Spoofing mitigated by honest disclosure). The Scope Audit (every cited path inspected against the deny-list) preserves the substantive guarantee regardless of who/what authored the answers. Future verification plans should adopt the same pattern when spawn tools are unavailable.
- Plan 04-01: alembic 0002_traces_denorm.py adds 4 denormalized columns (latency_ms, faithfulness, feedback_rating, estimated_cost_usd) + traces_feedback_rating_chk CHECK + traces_faithfulness_idx + traces_feedback_rating_idx + 2026-08 spans partition; reversibility drill (up/down/up) clean; 0001_initial.py byte-identical (D-2.17 enforced). RESEARCH §Open Questions #1 surfaced that estimated_cost_usd was missing from D-4.02 even though docs/api.md TraceListItem requires it — added to the migration. (See 04-01-SUMMARY.md.)
- Plan 04-01: Span Pydantic model atomic field swap — removed payload_id: UUID | None, added payload: dict[str, Any] | None = None (D-4.11/D-4.13). TraceWriter Protocol + Noop/Stdout adapters untouched. extra='forbid' now rejects payload_id (regression test added).
- Plan 04-01: Pipeline accepts db_pool: asyncpg.Pool | None = None kwarg. When set, every chat request lands a traces row up-front (INSERT INTO traces with query[:4000] truncation matching docs/api.md ChatRequest max_length and ON CONFLICT (id) DO NOTHING idempotent guard) BEFORE embed_batch; finalizes latency_ms + ended_at via UPDATE traces after _emit_root and estimated_cost_usd via UPDATE traces inside _llm_text_iter finally (closure-captures trace_id and self._db_pool from _orchestrate scope, preserves async-cancellation safety per Pitfall 7.8).
- Plan 04-01: Closure-capture verification pattern established: integration test asserts ALL 3 SQL ops fire (INSERT INTO traces, UPDATE latency_ms, UPDATE estimated_cost_usd) AND that the trace_id argument is consistent across all 3 (proves trace_id is captured from _orchestrate scope, not re-uuid4()'d in different scopes). Failure of any one indicates a broken closure capture.
- Plan 04-01: 4 child-span payload contracts locked per docs/trace-schema.md — rag.retrieve carries `{"retrieved_chunks": [{chunk_id, content, score, doc_id, doc_section}]}` if chunks else None; rag.prompt_assemble carries `{"messages": [...], "prompt_template_id": "..."}` if messages else None; rag.llm_call carries `{"response": {"answer", "input_tokens", "output_tokens", "estimated_cost_usd"}}` if final_event else None; rag.request (root) carries payload=None explicitly (D-4.11). Phase 4 Plan 03 PostgresTraceWriter.flush() will INSERT INTO span_payloads from these dicts.
- Plan 04-02: tracer_ai/tracer/exporters/queue.py BoundedDropOldestQueue exports the locked D-4.06 API verbatim (__init__(maxsize) / async put(item)->bool / async get()->Any / qsize()->int). collections.deque + asyncio.Lock + asyncio.Event composite pattern — eliminates the put_nowait+except+get_nowait race window of asyncio.Queue under concurrent producers. _not_empty.clear() under lock AFTER confirming deque is empty is a load-bearing correctness invariant. (See 04-02-SUMMARY.md.)
- Plan 04-02: rate-limited tracer.queue_saturated structured log via structlog (D-4.08) — at most once per 1s window; counter resets per period; log payload contains only dropped/window/queue_depth (T-04-02-04 — does NOT include item content). First drop on cold queue (last_log_at=0.0) ALWAYS fires immediately because now - 0.0 >= 1.0; subsequent drops within 1s accumulate into _dropped_count silently.
- Plan 04-02: 9 unit tests verify the contract (>= 8 required by plan). Concurrent-producer determinism test (T-04-02-03 mitigation acceptance) confirms 5 concurrent put() calls at capacity all return False AND the surviving items are all from the new_* set (no race-window drift). Plan 04-03 PostgresTraceWriter unblocked: PostgresTraceWriter(queue=BoundedDropOldestQueue(maxsize=1000)) is the wiring contract.
- Plan 04-03: tracer_ai/tracer/exporters/postgres.py PostgresTraceWriter (TraceWriter Protocol impl wrapping the queue) + SpanConsumer (background asyncio.Task with run / drain / _flush; first-of-50-or-250ms batch flush via asyncpg executemany; spans INSERT before span_payloads INSERT under one pool.acquire); ON CONFLICT (id, started_at) DO NOTHING idempotent INSERT against partitioned spans; emit() and run() both swallow exceptions (CLAUDE.md / T-04-03-04). Lifespan finally-block ordering invariant: drain (5s wait_for) -> cancel task -> close pool (D-4.10 / RESEARCH Pattern 3 / T-04-03-06 mitigation). 8 unit tests pass; mypy --strict + ruff + import_cycle_guard clean. (See 04-03-SUMMARY.md.)
- Plan 04-04: tracer_ai/tracer/store.py TraceStore Protocol exposes 3 methods (get_trace + list_traces + write_span per TRCR-05) — runtime_checkable; PostgresTraceStore.__init__(pool, writer) takes BOTH the asyncpg pool AND an injected TraceWriter so write_span can be a thin pass-through (await self._writer.emit(span)) — satisfies TRCR-05's literal Protocol while preserving the TraceWriter-first separation of concerns (TRCR-06 owns the durable write path). (See 04-04-SUMMARY.md.)
- Plan 04-04: TraceStore read methods return dict[str, Any] / tuple[list[dict[str, Any]], str | None] CANONICALLY (not Pydantic models). Reason: tracer_ai/tracer/ MUST stay below tracer_ai/api/ in the module-deps DAG (D-2.27); importing from api.schemas in store.py would fail import_cycle_guard. The route handler in api/traces.py constructs TraceListItem(**row) / SpanInResponse(**s) from the dicts. Pattern locked for future read-side abstractions across Phase 5+6.
- Plan 04-04: list_traces SQL composes 8 filter params into ONE parameterized query with $N IS NULL OR <pred> guards and $N::TYPE casts; ORDER BY started_at DESC, id DESC + (started_at, id) < ($N::timestamptz, $M::uuid) keyset cursor (D-4.19); limit + 1 fetch idiom for next_cursor detection; WHERE latency_ms IS NOT NULL excludes in-flight traces (T-04-04-09 mitigation). get_trace does the locked two-query fetch (D-4.21) + coalesces NULL latency_ms / estimated_cost_usd to 0/0.0 for in-flight detail view.
- Plan 04-04: encode_cursor / decode_cursor as base64(JSON {"started_at": ISO8601, "id": UUID-str}); decode raises ValueError on any malformed input (route handler converts to 400 INVALID_REQUEST envelope per docs/api.md). T-04-04-02 cursor-tampering mitigation acceptance verified via test_list_traces_rejects_invalid_cursor_with_400.
- Plan 04-04: tracer_ai/api/traces.py FastAPI route module exposes GET /traces + GET /traces/{trace_id} with Annotated[T | None, Query(...)] validation on all 8 filter params (FastAPI/ruff B008-clean form). 422 on min_faithfulness > 1.0, feedback != up|down, limit > 200, max_latency_ms < 0; 400 INVALID_REQUEST on malformed cursor or trace_id UUID; 404 TRACE_NOT_FOUND on no-match. PostgresTraceStore constructed per-request with (pool, writer) from request.app.state — writer required for the TRCR-05 write_span method.
- Plan 04-04: 5 new Pydantic v2 schemas (TraceListItem, TraceListResponse, SpanInResponse, SpanPayloadResponse, TraceDetailResponse) + canonical ErrorResponse + ErrorDetail envelope shipped in tracer_ai/api/schemas.py. All extra="forbid"; feedback_rating: Literal[-1, 1] | None mirrors DB CHECK (cross-layer integrity). TraceListItem.latency_ms / estimated_cost_usd are REQUIRED (not None-able) per docs/api.md §4 — store layer enforces this via the in-flight filter on list and coalesce on detail.
- Plan 04-04: tracer_ai/api/feedback.py wraps INSERT feedback + UPDATE traces SET feedback_rating in a single combined async with (pool.acquire(...), conn.transaction()) — atomic per D-4.03 / T-04-04-08. 5 existing Phase 3 feedback tests still pass after _FakeConn extension (added execute() recorder + @asynccontextmanager async def transaction() no-op); 2 happy-path assertions updated from len(executed)==1 to ==2. Orphan feedback (T-03-06-07) still accepted: UPDATE affects 0 rows on forged trace_id.
- Plan 04-04: 10 integration tests in tests/integration/test_traces_api.py (>= 9 required) cover list happy paths, in-flight SQL filter (T-04-04-09 acceptance), 400/422 validation errors, 404 missing detail, malformed UUID, full-tree round trip with payloads keyed by span_id. _build_app sets BOTH app.state.db_pool AND app.state.trace_writer (NoopTraceWriter) — mirrors the Phase 4 lifespan contract.
- Plan 04-04: 5 deviations all surface-level (2 ruff style — Annotated[Query(...)] for B008, combined async with for SIM117; 1 contract-change test update — len(executed) == 2 after the new transaction body; 1 mypy --strict type-annotation fix on heterogeneous fixture dicts; 1 disclosure of phase-end live Docker drill deferral to Plan 04-06 per D-4.25). Zero scope creep.

### Pending Todos

None yet.

### Blockers/Concerns

- Voyage AI voyage-code-3 pricing not confirmed — check docs.voyageai.com/docs/pricing before finalizing DSGN-01 ADR for GSD-OPEN-3
- Judge calibration set (~30 hand-labeled traces) must be authored in Phase 5 before shipping thresholds
- Tailwind v3 pin is critical: Tremor v3 + shadcn/ui both require v3; do NOT upgrade to v4

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| v2 | Streaming responses (V2-STRM-01) | Deferred | Init |
| v2 | Auth / multi-tenant (V2-AUTH-01, V2-AUTH-02) | Deferred | Init |
| v2 | Cross-encoder reranker (V2-RANK-01) | Deferred | Init |
| v2 | Custom eval dimension UI (V2-EVAL-01, V2-EVAL-02) | Deferred | Init |

## Session Continuity

Last session: 2026-05-06T17:01:30.000Z
Stopped at: Phase 4 Plan 04 complete; Plan 05 next
Resume file: .planning/phases/04-tracer-trace-explorer/04-05-PLAN.md
