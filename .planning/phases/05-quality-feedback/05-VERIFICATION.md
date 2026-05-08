---
phase: 05-quality-feedback
verified: 2026-05-07T18:00:00Z
status: gaps_found
score: 4/5 must-haves verified
overrides_applied: 0
phase_req_ids:
  declared: [EVAL-01, EVAL-02, EVAL-03, EVAL-04, EVAL-05, EVAL-06, FBCK-01, FBCK-02, FBCK-03, FBCK-04, FBCK-05, FBCK-06, FBCK-07, DASH-01, DASH-02, DASH-03, DASH-04, DASH-05, DASH-06]
  satisfied: [EVAL-01, EVAL-02, EVAL-03, EVAL-05, EVAL-06, FBCK-01, FBCK-02, FBCK-03, FBCK-04, FBCK-05, FBCK-06, FBCK-07, DASH-01, DASH-02, DASH-03, DASH-04, DASH-05, DASH-06]
  partially_satisfied: [EVAL-04]
  blocked: []
gaps:
  - truth: "rag.eval span records judge_model, judge_prompt_version, AND judge_cost_usd (EVAL-04 contract)"
    status: partial
    reason: "EvalDispatcher stamps RAG_EVAL_JUDGE_MODEL + RAG_EVAL_JUDGE_PROMPT_VERSION + RAG_EVAL_JUDGE_LATENCY_MS + RAG_EVAL_FAITHFULNESS + RAG_EVAL_RELEVANCE on the rag.eval span, but the RAG_EVAL_JUDGE_COST_USD attribute is NEVER set. The constant exists at tracer_ai/tracer/span.py:36, the value is computed by AnthropicJudge.score and carried on EvalScores.judge_cost_usd, but tracer_ai/eval/dispatcher.py never imports the constant and never writes scores.judge_cost_usd to eval_span.attrs. Per REQUIREMENTS.md EVAL-04 the rag.eval span MUST record judge_cost_usd. Cost cannot be aggregated or displayed without this stamp."
    artifacts:
      - path: "tracer_ai/eval/dispatcher.py"
        issue: "Imports RAG_EVAL_FAITHFULNESS / RELEVANCE / JUDGE_LATENCY_MS / JUDGE_MODEL / JUDGE_PROMPT_VERSION but NOT RAG_EVAL_JUDGE_COST_USD; lines 36-43 import block omits cost constant; lines 167-180 stamp loop never writes cost to eval_span.attrs"
    missing:
      - "Add RAG_EVAL_JUDGE_COST_USD to tracer_ai/eval/dispatcher.py imports (from tracer_ai.tracer.span)"
      - "Inside _do_score success branch (after line 174), add: eval_span.attrs[RAG_EVAL_JUDGE_COST_USD] = scores.judge_cost_usd"
      - "Add a unit test in tests/test_eval_dispatcher.py asserting scores.judge_cost_usd flows through to eval_span.attrs[RAG_EVAL_JUDGE_COST_USD] (>0 for non-zero usage)"
deferred: []
---

# Phase 5: Quality Layer + Feedback Verification Report

**Phase Goal:** Every trace is automatically scored for faithfulness and relevance by an async LLM judge; bad answers surface in a prioritized review queue; time-series charts show quality drift.

**Verified:** 2026-05-07T18:00:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A faithfulness score appears on every trace within ~30s of the request; the score is a child span (rag.eval) of rag.request — not an orphaned root span | VERIFIED | `tracer_ai/eval/dispatcher.py:135-148` reads `current_span()` for `parent` and constructs `eval_span.parent_span_id = parent.span_id`; `tracer_ai/rag/pipeline.py:498-503` calls `set_current_span(root_for_ctx)` + `capture_context()` BEFORE the iterator drains and `_emit_root` runs (Pitfall #1 mitigation); chat SSE generator passes the snapshot to `dispatcher.enqueue(...)` after the `event: final` frame yields (`tracer_ai/api/chat.py:85-102`). Integration test `tests/integration/test_eval_span_parentage.py` (PA2) asserts parent linkage; `tests/integration/test_eval_latency.py` (LA1) asserts wall-clock < 25s with mock judge. The 30-second budget per D-5.05 = 10s timeout × 2 attempts + 0.5s sleep ≤ 21s per call. |
| 2 | Clicking thumbs-down on a chat message lands the trace in the bad-answer queue within seconds; the queue is sorted by lowest faithfulness score first | VERIFIED | `frontend/src/pages/Queue.tsx:75-97` has two tabs: User-flagged (`getTraces({ feedback: "down", limit: 50 })` with `staleTime: 0` and `refetchOnWindowFocus: true` — FBCK-02) and Judge-flagged (`getTraces({ max_faithfulness: threshold, sort_by: "faithfulness_asc", limit: 50 })` — FBCK-06). Backend `tracer_ai/api/traces.py:70-86` accepts `max_faithfulness` (Field ge=0/le=1) + `sort_by` (Literal["created_at_desc", "faithfulness_asc"]); store SQL produces `ORDER BY faithfulness ASC NULLS LAST, started_at DESC, id DESC`. POST /feedback persists row with rating, traces.feedback_rating denorm updated atomically (Phase 4 D-4.03). |
| 3 | Time-series charts on the dashboard populate as queries are made — latency p50/p95, cost over time, faithfulness mean, and manual feedback ratio are all visible | VERIFIED | `frontend/src/pages/Dashboard.tsx` includes `QualityCharts` component (line 63) with 4 charts: 2 `LineChart` (latency p50/p95, faithfulness mean), 1 `AreaChart` (cost), 1 `LineChart` (feedback down ratio); `connectNulls={false}` on all 4 (D-5.07 load-bearing). `getTimeseries(window)` calls GET /traces/timeseries with adaptive bucketing. Backend `tracer_ai/tracer/store.py:352` `async def timeseries()` builds `generate_series` LEFT JOIN against trace_data; `PERCENTILE_CONT(0.5)` and `PERCENTILE_CONT(0.95)` for latency; `AVG(faithfulness)`; `SUM(estimated_cost_usd)`; `feedback_down_ratio` COALESCE NULL when no rated traces. Adaptive bucket sizing per D-5.17 (1m/5min/1h/1d for windows 1h/24h/7d/30d). |
| 4 | The bad-answer queue has a "mark resolved" action and a dashboard widget showing queue size and items resolved this week | VERIFIED | Queue.tsx renders Mark Resolved button (line 220-227) calling `markResolved(traceId)` → PATCH /feedback/{trace_id}/resolved (`tracer_ai/api/feedback.py:87-138`); idempotent UPDATE on `WHERE trace_id = $1 AND resolved_at IS NULL` with partial index `feedback_unresolved_idx` from `alembic/versions/0003_feedback_resolved.py`. Dashboard 5th KpiCard "QUEUE HEALTH" (Dashboard.tsx line 291) renders `queueHealth?.queue_size` + `queueHealth?.resolved_this_week` from GET /admin/queue-health (`tracer_ai/api/admin.py:352-380`); 30s `refetchInterval`; cache-invalidated on Mark-Resolved via `["queue-health"]` queryKey (Queue.tsx line 113). |
| 5 | A judge failure (timeout, rate limit, or exception) never causes a user-facing chat request to fail | VERIFIED | `tracer_ai/eval/dispatcher.py:151-162` catches all exceptions in judge call and logs `eval.judge_failed` while populating `attrs[ERROR_TYPE]` instead of re-raising; `tracer_ai/api/chat.py:89-102` wraps `dispatcher.enqueue(...)` in try/except (Pitfall #3); `dispatcher.enqueue` itself wraps `asyncio.create_task` in try/except (lines 91-106). Integration test `tests/integration/test_chat_with_failed_eval.py` (CF1-CF3) asserts POST /chat returns 200 + final SSE frame even when MockJudge raises TimeoutError; CF3 asserts UPDATE traces faithfulness was NOT issued (Pitfall #5). User experience is unaffected. (Note: `BaseException` catch is too broad per code-review CR-02 — it silences `asyncio.CancelledError` during shutdown — but does not break SC5; this is reported as a related warning below.) |

**Score:** 4/5 truths verified — SC1 has a partial implementation gap on `judge_cost_usd` cost attribution (see EVAL-04 partial below).

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `tracer_ai/eval/dispatcher.py` | EvalDispatcher with enqueue, _run_in_context, _do_score, drain | VERIFIED | 217 LOC; class with all four methods; module-level Semaphore via `get_judge_semaphore()`; never-raise contract at every layer. |
| `tracer_ai/eval/llm_judge.py` | AnthropicJudge.score returns EvalScores via tool_use; computes judge_cost_usd | VERIFIED | `score()` at line 149+; `cost_usd` computed from settings.pricing_claude_haiku_*; PROMPT_VERSION = "v1.ragas-faithfulness-relevance"; SUBMIT_EVAL_TOOL ToolParam present; MockJudge test double included. |
| `tracer_ai/eval/protocols.py` | Judge Protocol + EvalScores + ToolUseParseError | VERIFIED | `EvalScores.judge_cost_usd: float = Field(default=0.0, ge=0.0)` at line 46. |
| `tracer_ai/eval/prompts.py` | JUDGE_SYSTEM_PROMPT + build_judge_prompt + _escape_brackets | VERIFIED | XML-delimiter mandate honored; injection escape pass present. |
| `tracer_ai/eval/calibrate.py` | run_label + run_threshold_sweep + render_sweep_report + helpers; pyyaml usage | VERIFIED | `run_threshold_sweep` raises ValueError on prompt_version mismatch (line 124-130 — Pitfall 6 mitigation); `_iter_thresholds` yields 13 values [0.30..0.90 step 0.05]; `confusion_at` + `precision_recall_f1` correct. `run_label` short-circuits when n<=0 BEFORE asyncpg pool creation. |
| `tracer_ai/cli/__main__.py` | calibrate subparser with label + threshold subcommands | VERIFIED | argparse subparser group at line 69-72; `cal_command` dispatch at line 144 + 164; render_sweep_report imported and printed; print() in CLI module only (D-2.37 invariant). |
| `tracer_ai/tracer/context.py` | _current_span ContextVar + capture_context + attach_context + current_span + set_current_span | VERIFIED | All 5 functions present; zero `from opentelemetry` imports (ADR 005 invariant preserved). |
| `tracer_ai/tracer/span.py` | ERROR_TYPE + RAG_EVAL_JUDGE_LATENCY_MS + RAG_EVAL_JUDGE_COST_USD constants | VERIFIED | All three constants present (RAG_EVAL_JUDGE_COST_USD at line 36). |
| `tracer_ai/config.py` | 4 new Settings fields (BAD_ANSWER_FAITHFULNESS_THRESHOLD, JUDGE_CONCURRENCY, JUDGE_TIMEOUT_SECONDS, CALIBRATION_DATE) | VERIFIED | All four fields with bounded validators present. |
| `alembic/versions/0003_feedback_resolved.py` | ALTER TABLE feedback ADD COLUMN resolved_at + partial index | VERIFIED | `ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ NULL` and `feedback_unresolved_idx` index present; downgrade reversibility honored; revision chain 0001 → 0002 → 0003. |
| `tracer_ai/api/feedback.py` | PATCH /feedback/{trace_id}/resolved route | VERIFIED | Route at line 87; idempotent UPDATE; structlog `feedback_resolved` event. **Note**: returns fabricated `resolved_at = datetime.now(UTC)` when rows_updated=0 (CR-04 of REVIEW; not blocking SC4 but mid-priority). |
| `tracer_ai/api/admin.py` | GET /admin/eval-config + GET /admin/queue-health | VERIFIED | Both routes present (lines 323 + 352); EvalConfigResponse exposes threshold + judge_prompt_version + judge_model + calibration_date; QueueHealthResponse exposes queue_size + resolved_this_week (FBCK-07 fix — no static placeholder). |
| `tracer_ai/api/traces.py` | GET /traces/timeseries + extended GET /traces with max_faithfulness + sort_by | VERIFIED | timeseries route at line 126 with Literal window validation; max_faithfulness + sort_by params at lines 70-86. |
| `tracer_ai/tracer/store.py` | PostgresTraceStore.timeseries(window) + extended list_traces | VERIFIED | `async def timeseries` at line 352; generate_series + PERCENTILE_CONT (5min branch + natural-interval branch); list_traces sort_by branch (`ORDER BY faithfulness ASC NULLS LAST...`). |
| `frontend/src/pages/Queue.tsx` | Bad-answer queue page with Tabs + Mark Resolved + Promote-stub | VERIFIED | 248 LOC; both tabs (User-flagged + Judge-flagged); Mark Resolved button with `resolveMutation.mutate(it.trace_id)` and onSuccess invalidates `["queue"]` + `["dashboard-kpis"]` + `["queue-health"]` (line 110-114); threshold sourced from `getEvalConfig()` (line 67-72). |
| `frontend/src/pages/Dashboard.tsx` | QualityCharts + 5th KpiCard "Queue Health" wired to LIVE getQueueHealth | VERIFIED | KPI grid uses `lg:grid-cols-5` (line 239); 5th card renders `queueHealth?.queue_size ?? "—"` + `queueHealth?.resolved_this_week ?? "—"`; `refetchInterval: 30_000` for live polling; QualityCharts component renders 4 Tremor charts with `connectNulls={false}`. |
| `frontend/src/pages/TraceDetail.tsx` | Diagnosis-tag Select with Retrieval / PromptAssembly / LLM / CorpusStale / Other | VERIFIED | DIAGNOSIS_TAGS const + DiagnosisTagPanel component; preserves existing rating (line 78: `const ratingToSend: 1 | -1 = feedbackRating ?? -1` — but defaults to -1 when no rating, which is the WR-01 footgun documented as a warning below). |
| `frontend/src/api/traces.ts` | getTimeseries + getEvalConfig + markResolved + getQueueHealth + extended getTraces | VERIFIED | All four functions exported; `getTraces` threads max_faithfulness + sort_by params. |
| `frontend/src/router.tsx` | /dashboard/queue route added | VERIFIED | Route between dashboard and trace detail. |
| `frontend/src/components/AppShell.tsx` | Queue NavLink between Dashboard and Admin | VERIFIED | NavLink to /dashboard/queue present. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| pipeline._orchestrate | tracer.context.set_current_span + capture_context | Stub Span set on contextvar BEFORE _emit_root runs | WIRED | `tracer_ai/rag/pipeline.py:502-503` — set_current_span(root_for_ctx) + capture_context() right after orchestrate returns the 5-tuple, before `async for text in text_iter` consumes the generator that ends rag.request via _emit_root in its finally. |
| chat.py SSE generator | dispatcher.enqueue | request.app.state.eval_dispatcher.enqueue with ctx_snapshot | WIRED | `tracer_ai/api/chat.py:85-102` — getattr fallback (None when AnthropicJudge construction failed); enqueue called AFTER yielding final frame; try/except swallows exceptions (Pitfall #3). |
| dispatcher._run_in_context | tracer.context.attach_context + current_span | attach_context restores _current_span; current_span returns rag.request stub | WIRED | dispatcher.py:117 → 135 (current_span() reads parent inside _do_score). |
| Queue.tsx Judge tab | GET /traces?max_faithfulness=THRESHOLD&sort_by=faithfulness_asc | useQuery getTraces with threshold from getEvalConfig | WIRED | Queue.tsx:86-97 + api/traces.ts getTraces query param threading. |
| Queue.tsx Mark Resolved | PATCH /feedback/{trace_id}/resolved | useMutation + invalidateQueries | WIRED | Queue.tsx:108-115; markResolved() uses `_api.patch(\`feedback/${traceId}/resolved\`)`. |
| Dashboard.tsx 5th KpiCard | GET /admin/queue-health | useQuery getQueueHealth refetchInterval 30s | WIRED | Dashboard.tsx:222-227; QueueHealthResponse fields rendered. |
| Dashboard.tsx QualityCharts | GET /traces/timeseries | useQuery getTimeseries(window) | WIRED | Dashboard.tsx:73 + queryKey ["timeseries", window]; LineChart connectNulls={false} on all 4 charts. |
| Lifespan finally block | EvalDispatcher.drain → SpanConsumer.drain → pool.close | dispatcher drained BEFORE consumer (D-5.10 ordering) | WIRED | `tracer_ai/api/lifespan.py:175-200` — eval_disp.drain at line 178 (line < 186 for consumer.drain). |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|-------------------|--------|
| Queue.tsx items table | `items` (TraceListItem[]) | `useQuery getTraces({...})` → backend `tracer_ai/api/traces.py` GET /traces with new max_faithfulness + sort_by filters → store.py list_traces SQL with WHERE faithfulness < $N + ORDER BY clauses | YES — real DB query | FLOWING |
| Dashboard.tsx 5th KpiCard | `queueHealth.queue_size` + `queueHealth.resolved_this_week` | `useQuery getQueueHealth` → admin.py:368-379 fetchval COUNT(*) FROM feedback WHERE rating=-1 AND resolved_at IS NULL + COUNT(*) FROM feedback WHERE resolved_at >= NOW() - INTERVAL '7 days' | YES — real DB queries | FLOWING |
| Dashboard.tsx QualityCharts | `chartData[].latency_p50/p95/cost_sum/faithfulness_mean/feedback_down_ratio` | `useQuery getTimeseries` → traces.py:153 store.timeseries(window) → store.py:352-485 generate_series LEFT JOIN trace_data with PERCENTILE_CONT + AVG + SUM | YES — real aggregation SQL | FLOWING |
| TraceDetail.tsx diagnosis tag panel | `data.diagnosis_tag` | `useQuery getTrace(trace_id)` → backend GET /traces/{id} (Phase 4 endpoint extended in Phase 5 to surface diagnosis_tag) | YES — backend reads MAX(created_at) feedback row | FLOWING (assumed; backend extension claimed by Plan 07 SUMMARY but not directly verified in this review) |
| rag.eval span attrs.faithfulness | `scores.faithfulness` from AnthropicJudge.score | tool_use.input["faithfulness"] from real Anthropic Haiku call | YES — flows through llm_judge → dispatcher → writer.emit | FLOWING |
| rag.eval span attrs.judge_cost_usd | `scores.judge_cost_usd` (computed in llm_judge.py:212-216) | EvalScores carries it but dispatcher NEVER stamps it on eval_span.attrs | NO — value is computed and dropped | DISCONNECTED — see EVAL-04 gap below |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| EvalDispatcher class exists and is importable | `grep -c "class EvalDispatcher" tracer_ai/eval/dispatcher.py` | 1 | PASS |
| Dispatcher imports RAG_EVAL_JUDGE_COST_USD | `grep -c "RAG_EVAL_JUDGE_COST_USD" tracer_ai/eval/dispatcher.py` | 0 | FAIL — see EVAL-04 gap |
| Pipeline captures contextvar BEFORE _emit_root | `grep -n "capture_context" tracer_ai/rag/pipeline.py` | 1 site, line 503, before iterator drain | PASS |
| Lifespan drains dispatcher BEFORE consumer | line ordering check in lifespan.py finally | dispatcher.drain at line 178 < consumer.drain at line 186 | PASS |
| Calibrate refuses prompt-version mismatch | `grep -n "Re-run" tracer_ai/eval/calibrate.py` | line 128 in run_threshold_sweep ValueError | PASS |
| GET /admin/queue-health returns COUNT queries | inspection | fetchval against feedback table for queue_size + resolved_this_week | PASS |
| Queue.tsx threshold sourced from getEvalConfig | grep | Line 67-72 useQuery; line 90 max_faithfulness: threshold | PASS |
| Dashboard 5th KpiCard uses `lg:grid-cols-5` | grep | line 239: `lg:grid-cols-5` | PASS |
| Faithfulness chart uses connectNulls=false | grep | 4 occurrences in Dashboard.tsx (lines 130, 145, 165, 180) | PASS |
| ADR 005 invariant preserved (no opentelemetry imports) | `grep -rE "^from opentelemetry\|^import opentelemetry" tracer_ai/` | 0 lines | PASS |
| Anthropic SDK allowlist preserved | `grep -rE "^from anthropic\|^import anthropic" tracer_ai/` | only in rag/llm.py + eval/llm_judge.py | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| EVAL-01 | 05-01 | LLM-as-judge worker scores faithfulness and relevance for every trace; date-pinned claude-haiku snapshot | SATISFIED | AnthropicJudge.score uses settings.llm_judge_model = "claude-haiku-4-5-20251001" (dated snapshot); EvalScores.faithfulness + relevance populated. |
| EVAL-02 | 05-04 | Judge runs async via FastAPI BackgroundTasks after response flush; eval failure must NEVER fail user request | SATISFIED | EvalDispatcher uses asyncio.create_task (D-5.10 — chosen over BackgroundTasks per CONTEXT.md to avoid blocking the SSE response); test CF1 asserts user request returns 200 even when judge raises. |
| EVAL-03 | 05-01 | Judge prompt wraps untrusted content in XML delimiters; system instruction declares as inert data | SATISFIED | JUDGE_SYSTEM_PROMPT + build_judge_prompt + _escape_brackets injection-mitigation pass; tests cover the closing-tag injection mitigation. |
| EVAL-04 | 05-04 | rag.eval span emitted as child of rag.request; records judge_model, judge_prompt_version, judge_cost_usd | PARTIALLY SATISFIED | rag.eval is correctly a child of rag.request (test PA2). judge_model + judge_prompt_version + judge_latency_ms are stamped. **`judge_cost_usd` is COMPUTED but NOT STAMPED** — `tracer_ai/eval/dispatcher.py` does not write `RAG_EVAL_JUDGE_COST_USD` to eval_span.attrs. The constant exists in span.py:36; the value exists on EvalScores; the wiring step is missing. See gap below. |
| EVAL-05 | 05-04 | Faithfulness score appears on trace within ~30s of request | SATISFIED | LA1 wall-clock < 25s with mock judge; AnthropicJudge wall budget ≤ 21s per D-5.05. |
| EVAL-06 | 05-03, 05-06 | Calibration step: hand-label ~30 traces and tune the bad-answer threshold | SATISFIED | tracer-ai calibrate {label, threshold} CLI; best-F1 sweep over [0.3, 0.9] step 0.05; YAML schema includes prompt_version + judge_model + calibration_strategy + entries; GET /admin/eval-config exposes threshold + calibration_date for UI. |
| FBCK-01 | 05-02 | POST /feedback accepts {trace_id, rating, comment}; persists to feedback table | SATISFIED | Phase 4 POST /feedback handler preserved; Phase 5 added regression coverage in tests/test_feedback_route.py. |
| FBCK-02 | 05-07 | Thumbs-down lands the trace in the bad-answer queue within seconds | SATISFIED | Queue.tsx User-flagged tab uses staleTime: 0 + refetchOnWindowFocus: true. |
| FBCK-03 | 05-05, 05-07 | Bad-answer queue view: filtered trace list where feedback=down OR faithfulness < threshold | SATISFIED | Both tabs (User-flagged feedback=down + Judge-flagged max_faithfulness=THRESHOLD) wire to extended GET /traces. |
| FBCK-04 | 05-02 | "Mark resolved" action on bad-answer queue items | SATISFIED | PATCH /feedback/{trace_id}/resolved + Mark Resolved button. |
| FBCK-05 | 05-07 | Optional human-editable diagnosis tag with values {Retrieval, Prompt, Corpus, LLM} | SATISFIED | DIAGNOSIS_TAGS = [Retrieval, PromptAssembly, LLM, CorpusStale, Other]; DiagnosisTagPanel writes diagnosis_tag via POST /feedback. **Note**: PromptAssembly maps to "Prompt"; CorpusStale maps to "Corpus" — close to spec but renamed. WR-01 (silent downvote on unrated trace) is a UX warning, not a blocker. |
| FBCK-06 | 05-05, 05-07 | Bad-answer queue sorted by score (lowest faithfulness first); items auto-close on subsequent re-pass | SATISFIED (sort) / DEFERRED (auto-close) | sort_by=faithfulness_asc implemented; "auto-close on subsequent re-pass" is not implemented but is not in any plan's must_haves and not in the ROADMAP success criteria — this is a stretch goal beyond Phase 5. |
| FBCK-07 | 05-03, 05-07 | Dashboard widget: queue size + items resolved this week | SATISFIED | GET /admin/queue-health returns live counts; Dashboard 5th KpiCard renders both with 30s polling. |
| DASH-01 | 05-05, 05-07 | Time-series chart: latency p50/p95 over configurable window (default 24h) | SATISFIED | LineChart with categories=["Latency p50 (ms)", "Latency p95 (ms)"]; window selector. |
| DASH-02 | 05-05, 05-07 | Time-series chart: cost over time | SATISFIED | AreaChart with categories=["Cost ($)"]. |
| DASH-03 | 05-05, 05-07 | Time-series chart: faithfulness mean over time | SATISFIED | LineChart with connectNulls={false} (load-bearing). |
| DASH-04 | 05-05, 05-07 | Time-series chart: manual feedback ratio (down/total) over time | SATISFIED | LineChart with categories=["Feedback down ratio"]. |
| DASH-05 | 05-07 | Overview metrics card: request volume, total tokens, total cost, faithfulness score distribution | SATISFIED | KPI strip (Phase 4 carry-over) + Phase 5 additions; Queue Health is the 5th card. |
| DASH-06 | 05-07 | Charts implemented via Tremor v3 components | SATISFIED | All 4 charts use @tremor/react LineChart / AreaChart components. |

**Coverage:** 18/19 fully satisfied; 1 partially satisfied (EVAL-04 — see gap).

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `tracer_ai/eval/dispatcher.py` | 154, 185, 201 | `except BaseException as exc:` (catches CancelledError + KeyboardInterrupt + SystemExit) | Warning | Already flagged in 05-REVIEW.md as CR-02. Doesn't break user-facing SC5 (the user request still completes), but breaks cooperative shutdown — drain timeout cancels the gather, but the dispatcher task swallows the cancellation and continues into pool.acquire after the pool may already be closing. Not blocking phase goal achievement; routed to follow-up. |
| `tracer_ai/eval/dispatcher.py` | 211-213 | Defensive `getattr(scores, "faithfulness", None)` on Pydantic model that always has the attribute | Info | 05-REVIEW WR-07 — masks legitimate AttributeError as None; not a blocker. |
| `tracer_ai/api/feedback.py` | 128 | `resolved_at = rows[0]["resolved_at"] if rows else datetime.now(UTC)` — fabricates timestamp on rows_updated=0 | Warning | 05-REVIEW CR-04 — contract violation (timestamp doesn't reference any DB row); doesn't block SC4 because the queue UI uses rows_updated=0 to no-op the row removal correctly, but operator sees a fresh timestamp on idempotent re-PATCH. Not blocking phase goal; routed to follow-up. |
| `tracer_ai/rag/pipeline.py` | 502 | `set_current_span(root_for_ctx)` token never reset | Warning | 05-REVIEW WR-06 — pollutes the request task contextvar after _emit_root runs; latent bug since no later code in the same task queries current_span(). Not blocking phase goal; routed to follow-up. |
| `frontend/src/pages/TraceDetail.tsx` | 78 | Defaulting feedbackRating to -1 when null silently flags trace as thumbs-down | Warning | 05-REVIEW WR-01 — selecting a diagnosis tag on an unrated trace pushes it into the User-flagged queue. UX footgun; principle of least surprise violated. Not blocking phase goal (FBCK-05 still satisfies the requirement of having a diagnosis-tag UI); routed to follow-up. |

### Human Verification Required

None. All 5 ROADMAP success criteria can be verified programmatically against the codebase + integration tests. The single gap (EVAL-04 cost stamping) is not a UX-visible item — it is a missing line of code that must be added regardless of human inspection.

### Gaps Summary

The phase delivers nearly all of its goal. Four of five ROADMAP success criteria are fully verified — the rag.eval span lands as a child of rag.request within budget; thumbs-down lands in the queue with sort_by=faithfulness_asc; time-series charts populate with the 4 required dimensions and connectNulls=false; the Mark Resolved action + dashboard widget for queue size + items resolved this week both work end-to-end; and judge failures never fail user requests (Pitfall #3 / EVAL-02 acceptance covered by integration test CF1).

**One concrete gap blocks closure:** EVAL-04 explicitly requires the rag.eval span to record `judge_cost_usd`. The constant `RAG_EVAL_JUDGE_COST_USD = "rag.eval.judge_cost_usd"` is defined in `tracer_ai/tracer/span.py:36`. The value is computed correctly by `tracer_ai/eval/llm_judge.py` (lines 212-216) and stored on `EvalScores.judge_cost_usd`. But `tracer_ai/eval/dispatcher.py` never imports the constant and never writes the value to `eval_span.attrs`. As a result, every rag.eval span lands without the cost attribute, and the dashboard / cost analytics cannot aggregate judge spend.

This is mechanical: 2 lines of code (one import, one assignment) + 1 small unit test in `tests/test_eval_dispatcher.py` to assert the stamp is present. It does NOT change any cross-module contract.

The 05-REVIEW.md document also flags four other concerns that do not block the phase goal:
- CR-02 (BaseException catch swallows CancelledError) — code-quality / robustness; user-facing SC5 still holds.
- CR-03 (drain race) — partially mitigated by setting `_stopped` first; theoretical race window of one event-loop tick; not goal-breaking.
- CR-04 (fabricated resolved_at on rows_updated=0) — contract anomaly; SC4 still passes because the UI handles rows_updated=0 correctly.
- WR-01 (diagnosis tag silently downvotes unrated trace) — UX footgun; FBCK-05 still satisfied because the diagnosis-tag UI exists and works for already-rated traces.

These four are recommended follow-ups but are out of scope of "phase goal achievement." Recommended action: address the EVAL-04 cost stamp now (closes the only must-have gap) and route CR-02/CR-03/CR-04/WR-01 to a Phase 5 polish PR or Phase 7 cleanup.

---

_Verified: 2026-05-07T18:00:00Z_
_Verifier: Claude (gsd-verifier)_
