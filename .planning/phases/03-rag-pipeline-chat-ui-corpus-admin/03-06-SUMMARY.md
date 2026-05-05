---
phase: 03-rag-pipeline-chat-ui-corpus-admin
plan: 06
subsystem: api/sse-chat-feedback
tags: [sse, fastapi, streaming-response, prompt-injection-defense, asyncpg, pydantic-strict, x-accel-buffering, cross-layer-integrity, audit-log, lifespan-di, async-generator-protocol]

# Dependency graph
requires:
  - phase: 03-rag-pipeline-chat-ui-corpus-admin
    plan: 01
    provides: api/schemas.py (ChatRequest, ChatFinal, FeedbackRequest, FeedbackResponse, Citation); rag/types.py existing classes (Message, LLMResult, RetrievedChunk, TextDelta, Final, StreamEvent, PipelineResult); tracer/writer.py (NoopTraceWriter, StdoutTraceWriter, TraceWriter Protocol); feedback table CHECK (rating IN (-1, 1))
  - phase: 03-rag-pipeline-chat-ui-corpus-admin
    plan: 03
    provides: VoyageEmbedder; api/lifespan.py with CORP-04 startup assertion
  - phase: 03-rag-pipeline-chat-ui-corpus-admin
    plan: 04
    provides: PgvectorRetriever (cosine via <=>; ef_search=40)
  - phase: 03-rag-pipeline-chat-ui-corpus-admin
    plan: 05
    provides: AnthropicLLM streaming adapter; Pipeline.run_stream emitting 4 spans; rag/prompt.py assemble; settings.pricing_*
  - phase: 02-skeleton-infrastructure
    provides: Pydantic v2 strict-mode pattern (extra='forbid'); structlog idiom; FLAT Settings; D-2.27 import DAG enforcement; D-2.38 SDK isolation gate; alembic 0001 feedback table CHECK
provides:
  - tracer_ai.rag.types.CitedChunk + ChatFinalEvent (chat SSE wire types; Plan 01 classes preserved)
  - tracer_ai.rag.pipeline.Pipeline._orchestrate (private 4-span emitter returning trace_id + chunks + text iterator + usage_holder)
  - tracer_ai.rag.pipeline.Pipeline.run_chat_stream (yields TextDelta + ChatFinalEvent for SSE clients)
  - tracer_ai.rag.pipeline.Pipeline.run_stream (now delegates to _orchestrate; Plan 05 wire-level interface preserved)
  - tracer_ai.api.chat with POST /chat StreamingResponse (text/event-stream; Cache-Control: no-cache; Connection: keep-alive; X-Accel-Buffering: no)
  - tracer_ai.api.feedback with POST /feedback (asyncpg INSERT INTO feedback ... RETURNING id, created_at)
  - tracer_ai.api.lifespan extended to construct Pipeline + adapters and stash on app.state.{pipeline, embedder, retriever, llm, trace_writer}
  - tracer_ai.api.main registers chat.router + feedback.router (alongside existing health.router)
affects: [03-07-admin-ingest, 03-08-chat-ui-frontend, 04-tracer-postgres-writer, 05-eval-judge]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "SSE wire format: event:NAME\\ndata:JSON\\n\\n; emitted via FastAPI StreamingResponse with media_type='text/event-stream' and X-Accel-Buffering: no header to defeat proxy buffering (Pitfall 7.4 / T-03-06-09)"
    - "Pipeline orchestration refactor: _orchestrate() returns a 4-tuple (trace_id, chunks, text_iter, usage_holder) so multiple public consumers (run_stream, run_chat_stream) can share span-emission logic without duplicating it"
    - "usage_holder closure pattern: text_iter populates a shared dict in its finally block AFTER the LLM stream drains; the caller reads usage AFTER fully iterating -- prevents the Final-event-not-yet-yielded race"
    - "Chat SSE final-event payload: ChatFinalEvent.cited_chunks built from RetrievedChunk.metadata.get('source_url', '') -- defensive default for chunks ingested without source_url metadata"
    - "Cross-layer Literal[-1, 1] + DB CHECK (rating IN (-1, 1)): both layers MUST agree; drift is a bug class (T-03-06-05)"
    - "Lifespan pipeline construction wrapped in try/except: VoyageEmbedder + PgvectorRetriever + AnthropicLLM + NoopTraceWriter + Pipeline; on exception sets app.state.pipeline = None + logs warning (so test envs without real keys don't break startup)"
    - "Cast at lifespan construction site for AnthropicLLM -> LLM Protocol: mirrors the cast pattern in pipeline.py at the call site -- the Protocol declares 'async def stream(...) -> AsyncIterator' (read by mypy as coroutine), runtime is async-generator (returns AsyncIterator directly)"
    - "Generic event:error frame on SSE generator exception: structlog captures the full exception (chat_stream_error event); the SSE frame carries str(exc) only (T-03-06-10 -- v1 local-dev acceptable; production would scrub)"

key-files:
  created:
    - tracer_ai/api/chat.py
    - tracer_ai/api/feedback.py
    - tests/test_chat_route.py
    - tests/test_feedback_route.py
  modified:
    - tracer_ai/api/lifespan.py (added Plan 06 pipeline + adapter construction; cast for LLM Protocol)
    - tracer_ai/api/main.py (registered chat.router + feedback.router)
    - tracer_ai/rag/pipeline.py (extracted _orchestrate helper; added run_chat_stream; refactored run_stream to delegate)
    - tracer_ai/rag/types.py (appended CitedChunk + ChatFinalEvent; Plan 01 classes preserved)

key-decisions:
  - "Two-iterator decomposition with a usage_holder closure: _orchestrate returns a tuple (trace_id, chunks, text_iter, usage_holder). Both run_stream and run_chat_stream consume text_iter to yield text deltas; both read usage_holder AFTER the iterator drains to build their respective final-event payloads. The closure-mutation pattern keeps the Final/ChatFinalEvent construction in the public method (preserves the wire-level interface) while sharing the four-span emission logic in _orchestrate."
  - "ChatFinalEvent is a NEW Pydantic model in rag/types.py rather than a reuse of api/schemas.ChatFinal. The two share fields but ChatFinalEvent uses trace_id: str (instead of UUID) -- json.dumps wants strings and the SSE frame is JSON-serialized; pre-converting at the rag-layer keeps the chat handler free of UUID-stringify branches. ChatFinal in api/schemas.py remains the docs/api.md authoritative wire shape for any future non-streaming consumer."
  - "Chat handler does NOT check pipeline = None at request time -- the lifespan failure path leaves app.state.pipeline = None; calling .run_chat_stream on None would raise AttributeError caught by the SSE generator's except Exception handler and surface as event:error. This is acceptable for v1 local-dev; production hardening (returning 503 on pipeline-unavailable) is deferred."
  - "Feedback endpoint uses request.app.state.db_pool directly (no Depends() injection). Mirrors the health.py pattern (PATTERNS.md s'asyncpg pool DI from request.app.state'). 1.0s pool acquire timeout (T-03-06-* DoS bound; matches retriever.py pattern)."
  - "X-Accel-Buffering: no header set unconditionally even when no nginx proxy is in front. The header is harmless for direct uvicorn deployment and necessary for any future proxy. Defense-in-depth per Pitfall 7.4."
  - "AnthropicLLM construction in lifespan wrapped in try/except + cast(LLM, AnthropicLLM()): preserves the existing test fixture pattern where _configured_env injects fake env vars but doesn't actually exercise the SDK constructor. The cast is required at the construction site because mypy reads the Protocol's 'async def stream(...) -> AsyncIterator' as a Coroutine return; the concrete async-generator function returns AsyncIterator directly. Documented inline."
  - "RAG-06 automated gate is a mocked-stack latency test (< 1500ms) over a 50-canned-chunk fixture + 20 fake token deltas; the real-stack p95 < 5000ms remains a manual smoke (verification section). The mocked test gives a deterministic, reproducible CI gate without external dependencies."

patterns-established:
  - "SSE generator function pattern: an inner async def gen() -> AsyncIterator[bytes] yields encoded SSE frames; outer function returns StreamingResponse(gen(), media_type=..., headers=...). Reusable for any future SSE endpoint (e.g., admin ingest progress in Plan 07)."
  - "FakePipeline pattern: a test fixture class with a single async def run_chat_stream(query) -> AsyncIterator that yields configurable TextDelta + ChatFinalEvent. Bypasses lifespan and SDK construction entirely; the integration tests assert SSE wire format only. Reusable for Plan 08 frontend tests + Plan 07 admin tests."
  - "Cross-layer Literal mirrors DB CHECK + tested both ways: rating=0 -> 422 at FastAPI layer (Pydantic Literal[-1, 1]); FakePool.executed list shows zero recorded queries on validation failure (proves rejection happened pre-DB). Reusable for any future schema field with a DB CHECK."

requirements-completed:
  - RAG-05
  - RAG-06
  - CHAT-04

# Metrics
duration: 11min
completed: 2026-05-05
---

# Phase 3 Plan 06: Chat SSE + Feedback Persistence Summary

**Wired the SSE chat surface (POST /chat with text/event-stream + token + final frames) and the feedback write endpoint (POST /feedback) on top of the Plan 05 four-span pipeline.**

## Performance

- **Duration:** ~11 min
- **Started:** 2026-05-05T09:47:12Z
- **Completed:** 2026-05-05T09:58:33Z
- **Tasks:** 2 (both type="auto" tdd="true")
- **Files modified:** 4 created (2 source + 2 test) + 4 modified (pipeline.py, types.py, lifespan.py, main.py)

## Accomplishments

- **POST /chat SSE handler** (`tracer_ai/api/chat.py`): `StreamingResponse(media_type="text/event-stream")` with `Cache-Control: no-cache`, `Connection: keep-alive`, and `X-Accel-Buffering: no` headers (Pitfall 7.4 mitigation). Iterates `request.app.state.pipeline.run_chat_stream(body.question)`, serializing each `TextDelta` as `event: token\ndata: {"text": ...}\n\n` and the trailing `ChatFinalEvent` as `event: final\ndata: {full payload}\n\n`. Generic `event: error` frame on any exception (T-03-06-10 -- str(exc) only; full traceback lives in structlog).
- **POST /feedback handler** (`tracer_ai/api/feedback.py`): `INSERT INTO feedback (trace_id, rating, comment, diagnosis_tag) VALUES ($1, $2, $3, $4) RETURNING id, created_at` -- asyncpg pool acquire with 1.0s timeout. Returns `FeedbackResponse(id, created_at)`. Cross-layer integrity (T-03-06-05): `FeedbackRequest.rating: Literal[-1, 1]` + DB CHECK both block invalid values; the test asserts `pool.executed == []` after a 422, proving validation runs pre-DB.
- **Pipeline refactored with `_orchestrate` + `run_chat_stream`** (`tracer_ai/rag/pipeline.py`): extracted the per-stage span emission into a private `async def _orchestrate(query) -> (trace_id, chunks, text_iter, usage_holder)`. Public `run_stream` now consumes the text iterator and yields `TextDelta` + `Final` (Plan 05 contract preserved). New public `run_chat_stream` consumes the same iterator and yields `TextDelta` + exactly one `ChatFinalEvent` -- `cited_chunks` built from `RetrievedChunk.metadata.get("source_url", "")`, `latency_ms` measured from method entry to the moment `ChatFinalEvent` is yielded. The four-span emission contract is preserved: `rag.request` (root), `rag.retrieve`, `rag.prompt_assemble`, `rag.llm_call`.
- **`CitedChunk` + `ChatFinalEvent` appended to `tracer_ai/rag/types.py`**: append-only refactor preserving every Plan 01 class (RetrievedChunk, Message, LLMResult, TextDelta, Final, PipelineResult, StreamEvent). `ChatFinalEvent.trace_id: str` (rather than UUID) so `json.dumps` can serialize it without a custom encoder.
- **Lifespan extended to construct the Pipeline** (`tracer_ai/api/lifespan.py`): after the asyncpg pool opens AND CORP-04 succeeds, constructs `VoyageEmbedder()` + `PgvectorRetriever(pool)` + `AnthropicLLM()` (cast to LLM Protocol) + `NoopTraceWriter()` + `Pipeline(embedder, retriever, llm, writer, top_k=5)`, stashing each on `app.state.{pipeline, embedder, retriever, llm, trace_writer}`. Wrapped in `try/except`: on exception, all five `app.state.*` fields are set to `None` and a structured warning is logged so test environments without real Voyage/Anthropic keys don't break startup.
- **`api/main.py` registers chat + feedback routers**: alongside the existing health router. Three routers total now (Phase 3 Wave 4 ships POST /chat + POST /feedback; admin endpoints arrive in Plan 07).
- **12 new tests + mypy --strict clean**:
  - `tests/test_chat_route.py` (7 tests): SSE wire format (token + final frames), content-type starts with text/event-stream, validation 422 on empty / 4001-char question, headers (Cache-Control + X-Accel-Buffering), final-frame payload shape (all 6 keys with right types), RAG-06 mocked-stack < 1500ms latency gate over 50 canned chunks + 20 token deltas.
  - `tests/test_feedback_route.py` (5 tests): happy-path 201 + UUID id, rating=0 -> 422 (Literal cross-layer), comment recorded in INSERT args, extra_field -> 422 (extra='forbid'), SQL targets feedback table with all expected columns.
- **Zero regressions**: `pytest tests/` reports 171 passed + 1 skipped (pre-existing skip, unrelated). Plan 05's six pipeline tests still pass after the `_orchestrate` refactor; Plan 03's healthz + lifespan tests still pass after the lifespan extension.

## Task Commits

Each task committed atomically (TDD: test file written first, RED confirmed via ImportError, then implementation):

1. **Task 1: chat SSE + Pipeline refactor + types append + lifespan extension** -- `9931e9f` (feat)
2. **Task 2: feedback persistence endpoint** -- `2233276` (feat)

## Files Created/Modified

**Created:**
- `tracer_ai/api/chat.py` -- POST /chat handler returning `StreamingResponse(media_type="text/event-stream")`; iterates `pipeline.run_chat_stream`; emits `event: token` / `event: final` / `event: error` frames; Pitfall 7.4 headers set.
- `tracer_ai/api/feedback.py` -- POST /feedback handler with `INSERT INTO feedback ... RETURNING id, created_at`; structlog `feedback_recorded` audit event.
- `tests/test_chat_route.py` -- 7 tests using `_FakePipeline` + FastAPI TestClient: streaming shape, content-type, validation bounds, headers, final payload shape, RAG-06 latency gate.
- `tests/test_feedback_route.py` -- 5 tests using `_FakePool` + FastAPI TestClient: 201 happy path, rating=0 -> 422 cross-layer, comment recorded, extra_field rejected, SQL shape verified.

**Modified:**
- `tracer_ai/api/lifespan.py` -- added VoyageEmbedder/PgvectorRetriever/AnthropicLLM/NoopTraceWriter/Pipeline construction after CORP-04; `cast(LLM, AnthropicLLM())` to bridge Protocol/runtime async-generator gap; try/except so test envs don't break startup.
- `tracer_ai/api/main.py` -- imported `chat` + `feedback` modules; registered both routers.
- `tracer_ai/rag/pipeline.py` -- extracted `_orchestrate` private helper; refactored `run_stream` to delegate; added new public `run_chat_stream`; added `_emit_root` helper for the early-failure root-span emission paths. All four spans still emitted on every code path (preserved test_retriever_failure_still_emits_spans invariant).
- `tracer_ai/rag/types.py` -- appended `CitedChunk` + `ChatFinalEvent` (every Plan 01 class preserved verbatim above the new section).

## Decisions Made

- **Two-iterator decomposition with usage_holder closure**: `_orchestrate` returns `(trace_id, chunks, text_iter, usage_holder)`. The text_iter populates `usage_holder` in its `finally` block AFTER the LLM stream drains, so the public method (`run_stream` or `run_chat_stream`) can read the usage figures AFTER iterating to build the final event. Avoids duplicating the four-span emission logic between the two public methods.
- **`ChatFinalEvent` is a NEW Pydantic model in `rag/types.py`** -- not a reuse of `api/schemas.ChatFinal`. The two share fields but `ChatFinalEvent.trace_id: str` (instead of UUID) so `json.dumps` can serialize the SSE data line without a custom encoder. `ChatFinal` in `api/schemas.py` remains the docs/api.md authoritative wire shape for any future non-streaming consumer (e.g., a debug HTTP endpoint that returns a non-streamed full ChatFinal).
- **Chat handler does NOT pre-check `pipeline is None`**: the lifespan failure path sets `app.state.pipeline = None`; calling `.run_chat_stream` on None raises `AttributeError`, caught by the SSE generator's `except Exception` handler and surfaced as an `event: error` frame. Acceptable for v1 local-dev; production hardening (returning 503 on pipeline-unavailable) is deferred to v1.5+.
- **Feedback endpoint uses `request.app.state.db_pool` directly**: no FastAPI `Depends()` injection. Mirrors `health.py` pattern (PATTERNS.md "asyncpg pool DI from request.app.state"). 1.0s acquire timeout matches retriever.py.
- **`X-Accel-Buffering: no` header set unconditionally**: harmless when no nginx proxy is in front; necessary for any future proxy. Defense-in-depth per Pitfall 7.4.
- **Cast `AnthropicLLM` to `LLM` Protocol at construction site**: mypy reads the Protocol's `async def stream(...) -> AsyncIterator` as `Coroutine[..., AsyncIterator]` (would need await); the concrete async-generator function returns `AsyncIterator` directly. Documented inline; mirrors the cast pattern in `pipeline.py:194`.
- **RAG-06 primary gate is a mocked-stack latency test** (`test_chat_end_to_end_latency`): `_FakePipeline` with 20 instant TextDelta events + `ChatFinalEvent` with 50 canned `CitedChunk` fixtures; POST /chat measured end-to-end < 1500ms. Real-stack p95 < 5000ms remains a manual smoke (verification section), not the primary gate. The mocked test is reproducible, deterministic, and runs in CI without external dependencies.
- **`_emit_root` helper extracted**: the root `rag.request` span has three emission sites (retrieve-failure path, prompt-failure path, llm-iter finally). Extracting the emission logic into a single private method keeps the orchestration code DRY and the latency-computation invariant in one place.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 -- Blocking] mypy `arg-type` on `Pipeline(..., llm=AnthropicLLM(), ...)` in lifespan.py**

- **Found during:** Task 1 verify step (`mypy --strict tracer_ai/api/lifespan.py`).
- **Issue:** `Pipeline.__init__` is typed `llm: LLM` (the Protocol). `AnthropicLLM.stream` is an async-generator function returning `AsyncIterator[StreamEvent]` directly; the Protocol declares `async def stream(...) -> AsyncIterator[StreamEvent]` which mypy interprets as a coroutine returning an iterator. The structural shapes mismatch at type-check time. This is the same Protocol/runtime async-generator gap documented in Plan 05's deviation #6 (handled there with a cast at the call site in `pipeline.py:194`).
- **Fix:** Imported `cast` and `LLM` from `typing` and `tracer_ai.rag.protocols`; wrapped the `AnthropicLLM()` construction with `cast(LLM, AnthropicLLM())`. Documented inline with a 5-line comment explaining the Protocol/runtime mismatch.
- **Files modified:** `tracer_ai/api/lifespan.py`.
- **Verification:** `mypy --strict tracer_ai/api/lifespan.py` -> Success: no issues found. All chat tests still pass.
- **Committed in:** `9931e9f` (Task 1 commit; fix folded in before any commit landed).

**2. [Hook-driven] ruff-format reformatted pipeline.py during pre-commit**

- **Found during:** Task 1 first commit attempt.
- **Issue:** Pre-commit `ruff-format` hook reformatted the multi-line `await self._emit_root(...)` calls inside the nested finally blocks in `pipeline.py`. The first commit invocation aborted; the file was left modified after auto-format.
- **Fix:** Re-staged the formatted file; re-ran `git commit`. All hooks (trim-whitespace, fix-eof, ruff, ruff-format, gitleaks, mypy --strict, pytest --testmon, import-cycle-guard, anti-pattern-grep) reported PASS on the second invocation.
- **Files modified:** `tracer_ai/rag/pipeline.py` (cosmetic only).
- **Verification:** All 7 chat tests + 6 pipeline tests + 35 plan-relevant tests pass post-format. mypy --strict clean.
- **Committed in:** `9931e9f` (effects baked in).

---

**Total deviations:** 2 (1 Rule 3 mypy-Protocol-runtime gap, 1 hook-driven cosmetic reformat).
**Impact on plan:** No scope change. The mypy fix is documented inline and mirrors Plan 05's established cast-at-Protocol-boundary pattern. The reformat is cosmetic.

## Issues Encountered

- **None during planned work.** Both deviations above were discovered by the plan's own test list / static-analysis gates -- not by unrelated paths.

## Threat Mitigations Applied

| Threat ID | Status | Where |
|-----------|--------|-------|
| T-03-06-01 (Tampering -- prompt-injection-via-question) | Mitigated upstream | `ChatRequest.question: Annotated[str, Field(min_length=1, max_length=4000)]` caps user input at the FastAPI layer (422 on out-of-bounds); the load-bearing prompt-injection defense lives in `tracer_ai/rag/prompt.py` (Plan 05) which wraps chunks (NOT the user query) in delimiter tags. |
| T-03-06-02 (Information Disclosure -- SSE response) | Accepted | Local-dev only (no auth boundary per ADR 009); production hardening deferred to v1.5+. |
| T-03-06-03 (Denial of Service -- POST /chat long question) | Mitigated | `max_length=4000` caps single-request size at FastAPI; `Pipeline.run_chat_stream` -> `AnthropicLLM.stream` -> `max_tokens=1024` default caps response cost (T-03-05-05 inherited). No rate-limiter in v1 (single-user local). |
| T-03-06-04 (Tampering -- JSON encoding) | Mitigated | `json.dumps` escapes control chars and quotes; SSE frame delimiters `\n\n` would be encoded by `json.dumps` if present in token text. |
| T-03-06-05 (Tampering -- feedback rating) | Mitigated | DOUBLE-LAYER: `FeedbackRequest.rating: Literal[-1, 1]` (Plan 01 schemas) AND DB CHECK (rating IN (-1, 1)) (alembic 0001). Witness: `tests/test_feedback_route.py::test_post_feedback_rejects_rating_zero` asserts `pool.executed == []` after a 422 (proves validation rejected pre-DB). |
| T-03-06-06 (Information Disclosure -- comment field) | Accepted | Local-dev unauthenticated; comments are user-controlled but stored only for the same user. |
| T-03-06-07 (Spoofing -- trace_id forgery) | Accepted | Local-dev; forging a UUID points to a non-existent trace (orphan rows simply won't show up in the Phase 4 trace explorer). |
| T-03-06-08 (Repudiation -- audit trail) | Mitigated | structlog `feedback_recorded` event logs every successful insert with `trace_id` + `rating`; `chat_stream_error` event logs the full exception via `log.exception` on any SSE generator failure. |
| T-03-06-09 (Denial of Service -- proxy buffering) | Mitigated | `X-Accel-Buffering: no` header set unconditionally; `Cache-Control: no-cache` + `Connection: keep-alive` companion headers. CHAT-02 e2e test in Plan 08 will assert >= 2 distinct DOM mutations (proves no client-side buffering). |
| T-03-06-10 (Information Disclosure -- error event leakage) | Mitigated | Generic `except Exception` -> `event: error` frame with `str(exc)` ONLY; full traceback stays in structlog (`log.exception("chat_stream_error", error=...)`). Production deployment would gate on env to scrub the message. |

## Self-Check: PASSED

- File `tracer_ai/api/chat.py` exists. Verified.
- File `tracer_ai/api/feedback.py` exists. Verified.
- File `tests/test_chat_route.py` exists. Verified.
- File `tests/test_feedback_route.py` exists. Verified.
- File `tracer_ai/api/lifespan.py` modified (added pipeline construction). Verified.
- File `tracer_ai/api/main.py` modified (registers chat + feedback routers). Verified.
- File `tracer_ai/rag/pipeline.py` modified (added _orchestrate + run_chat_stream). Verified.
- File `tracer_ai/rag/types.py` modified (appended CitedChunk + ChatFinalEvent). Verified.
- Commit `9931e9f` (Task 1) exists in `git log`. Verified.
- Commit `2233276` (Task 2) exists in `git log`. Verified.
- `pytest tests/test_chat_route.py tests/test_feedback_route.py -q` -> 12 passed.
- `pytest tests/ -q` -> 171 passed + 1 skipped (zero regressions).
- `mypy --strict tracer_ai/api/chat.py tracer_ai/api/feedback.py tracer_ai/api/lifespan.py tracer_ai/api/main.py tracer_ai/rag/pipeline.py tracer_ai/rag/types.py` -> Success: no issues found in 6 source files.
- `python infra/scripts/import_cycle_guard.py` -> OK: tracer_ai module DAG check clean (4 layers).
- Acceptance grep counts (Task 1):
  - `media_type="text/event-stream"` (chat.py) = 1.
  - `X-Accel-Buffering` (chat.py) = 2 (>= 1).
  - `event: token | event: final` (chat.py) = 6 (>= 2).
  - `app.state.pipeline` (lifespan.py) = 5 (>= 1).
  - `chat.router` (main.py) = 1 (>= 1).
  - `ChatFinalEvent | class CitedChunk` (types.py) = 4 (>= 1).
  - Existing classes preserved (types.py) = 6 (>= 6: RetrievedChunk, Message, LLMResult, TextDelta, Final, PipelineResult).
  - `async def run_chat_stream` (pipeline.py) = 1.
  - `pipeline.run_chat_stream` (chat.py) = 2 (1 in code + 1 in docstring; the call-site exists).
- Acceptance grep counts (Task 2):
  - `INSERT INTO feedback` (feedback.py) = 1.
  - `@router.post("/feedback"` (feedback.py) = 1.
  - `feedback.router | include_router(feedback` (main.py) = 1 (>= 1).

## User Setup Required

None -- no external service configuration required for the test gates. The lifespan-construction try/except path means a `docker compose up` startup without real Voyage/Anthropic keys will boot (with `app.state.pipeline = None` and a structured warning); calling /chat in that state would surface as `event: error`. Real-stack manual smoke (`curl -N -X POST http://localhost:8000/chat ...`) requires `ANTHROPIC_API_KEY` + `VOYAGE_API_KEY` set in the env.

## Next Phase Readiness

- **Phase 3 Plan 07 (admin UI / re-index):** unblocked. The admin's `POST /admin/ingest` endpoint will dispatch via FastAPI BackgroundTasks against the `run_ingest` orchestrator pinned in Plan 05. The admin handler can also use the SSE generator pattern from `chat.py` for streaming ingest progress (Plan 07 may choose JSON polling instead per UI-SPEC).
- **Phase 3 Plan 08 (chat UI frontend):** unblocked. The frontend's `lib/sse.ts` SSE parser will consume the wire format pinned here (`event: token\ndata: {text}\n\n` + `event: final\ndata: {full payload}\n\n`); the `ChatFinalEvent` JSON schema is now stable (trace_id: str, cited_chunks: list, latency_ms + tokens + cost).
- **Phase 4 (tracer Postgres writer):** unblocked. The lifespan currently uses `NoopTraceWriter()`; Phase 4 swaps to `PostgresTraceWriter()` with one line in `lifespan.py`. The four-span emission contract is preserved through the `_orchestrate` refactor -- no pipeline.py changes needed.
- **Phase 5 (eval + judge):** unblocked. The chat endpoint emits `trace_id` in the `ChatFinalEvent` payload; the Phase 5 eval pipeline will join feedback rows to trace rows via this trace_id (CHAT-04 + RAG-04 already wire the persistence half here; the eval reader is Phase 5).

## Threat Flags

None -- no new threat surface introduced beyond the plan's `<threat_model>` register. The new attack surface (POST /chat SSE stream + POST /feedback row insert) is bounded by:
- `ChatRequest.question` length cap 1..4000 (FastAPI 422 on out-of-bounds);
- `FeedbackRequest.rating: Literal[-1, 1]` + DB CHECK both layers;
- `extra="forbid"` on every Pydantic model in `api/schemas.py` (rejects unknown JSON fields);
- 1.0s asyncpg pool acquire timeout on /feedback (DoS bound);
- max_tokens=1024 default cap in `AnthropicLLM.stream` (T-03-05-05 inherited);
- structlog audit trail (`feedback_recorded` + `chat_stream_error`) for repudiation defense.

---
*Phase: 03-rag-pipeline-chat-ui-corpus-admin*
*Completed: 2026-05-05*
