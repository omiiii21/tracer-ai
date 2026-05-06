---
phase: 03-rag-pipeline-chat-ui-corpus-admin
verified: 2026-05-06T06:09:09Z
status: gaps_found
score: 3/5 success criteria verified (2 blocked by wire-shape contract drift)
overrides_applied: 0
gaps:
  - truth: "Each retrieved chunk is cited inline and expandable (SC-2 / CHAT-02)"
    status: failed
    reason: |
      Wire-shape contract drift between backend SSE final event and frontend
      Citation accordion. Backend `Pipeline.run_chat_stream` emits
      `CitedChunk{idx, doc_url, section_title, text, score}`
      (tracer_ai/rag/types.py:115-131; tracer_ai/rag/pipeline.py:354-361).
      Frontend `Citation` interface and `CitationAccordion` consume
      `{idx, doc_id, doc_section, section_title, source_url, content, score}`
      (frontend/src/lib/api.ts:10-18; frontend/src/components/Citation.tsx:55-78).
      At runtime the accordion will render `c.doc_id`, `c.source_url`, and
      `c.content` as undefined. Inline label "[idx] doc_id · section_title · score"
      becomes "[idx] undefined · section_title · score"; <pre> chunk body
      renders empty; the source-URL click-through link does not appear.
      Plan 06 explicitly defined the new shape (`doc_url`, `text`); Plan 08
      explicitly specified the OLD shape (`doc_id`, `source_url`, `content`)
      — the two plans contradicted and the implementation followed Plan 06
      on the backend and Plan 08 on the frontend. The Playwright e2e tests
      stub the API with the OLD shape and pass, but the live backend now
      emits the NEW shape, so the tests do not catch the drift. Backend
      `tracer_ai/api/schemas.py` retains a now-unused `Citation` model with
      the OLD shape but the chat route does NOT use it as response_model
      (it serializes `ChatFinalEvent` directly).
    artifacts:
      - path: "tracer_ai/rag/types.py"
        issue: "CitedChunk fields {idx, doc_url, section_title, text, score} disagree with frontend Citation type"
      - path: "tracer_ai/rag/pipeline.py"
        issue: "Lines 353-361 build CitedChunk with doc_url/text instead of doc_id/source_url/content"
      - path: "frontend/src/lib/api.ts"
        issue: "Citation interface declares doc_id/doc_section/source_url/content — does not match wire payload"
      - path: "frontend/src/components/Citation.tsx"
        issue: "Renders c.doc_id, c.source_url, c.content which will be undefined at runtime"
      - path: "frontend/tests/chat.spec.ts"
        issue: "Stubs the SSE final frame with the OLD wire shape so e2e tests pass against an unrealistic mock"
    missing:
      - "Decide on a single canonical wire shape for cited chunks (recommend keeping CitedChunk source-of-truth and updating frontend Citation interface + Citation.tsx + tests/chat.spec.ts SAMPLE_CHUNK to use {idx, doc_url, section_title, text, score})"
      - "Update CitationAccordion render to use c.text for body and c.doc_url for click-through (or the inverse if the OLD shape is preferred — then update CitedChunk in rag/types.py and run_chat_stream)"
      - "Update Playwright SAMPLE_CHUNK fixture in frontend/tests/chat.spec.ts to match the live wire shape so the e2e tests would catch future drift"
      - "Reconcile or remove the unused tracer_ai/api/schemas.py Citation/ChatFinal models (currently dead code that does not match runtime)"

  - truth: "Asking 5 hand-picked questions returns accurate, cited answers with latency, token count, and estimated cost visible in the chat UI (SC-1)"
    status: partial
    reason: |
      The chat pipeline, SSE handler, citation accordion, metadata strip
      (latency_ms / tokens / cost), and message bubble are all implemented
      and exercised by unit + Playwright tests. SC-1 cannot be fully verified
      programmatically because it requires a live Voyage + Anthropic
      backend ingesting real Claude API docs and returning answers — out of
      scope for static verification. However the cited-chunk display path
      is broken by the wire-shape drift documented above, so even with
      live infrastructure the citations would render with empty bodies
      and missing source-URL links. Latency / tokens / cost surfacing IS
      working because those fields use matching names across both layers.
    artifacts:
      - path: "tracer_ai/rag/pipeline.py"
        issue: "Pipeline orchestrator implemented; depends on live Voyage + Anthropic adapters for real answers"
      - path: "frontend/src/components/Citation.tsx"
        issue: "Wire-shape drift breaks the citation body/source-URL display (see SC-2 gap above)"
    missing:
      - "Resolve the SC-2 wire-shape gap (above) so cited answers actually render their chunk text + source URLs"
      - "Manual smoke test against live Claude API + Voyage with a 5-question coverage subset (human verification — see human_verification section)"

deferred:
  - truth: "Each message links to its trace in the Trace Explorer (SC-2 partial — link presence + non-404 route)"
    addressed_in: "Phase 4"
    evidence: "Phase 3 explicitly defers the actual viewer to Phase 4; the route /traces/{trace_id} renders TraceStub.tsx and does not 404, satisfying the Phase 3 contract — the real explorer ships in Phase 4 (TRCR-* / EXPL-*)."

human_verification:
  - test: "Boot the live stack with real Voyage + Anthropic keys; run `tracer-ai ingest --source <real-claude-docs-dir>`; ask 5 hand-picked coverage questions"
    expected: "Each answer is accurate, includes inline [n] markers tied to expandable chunk panels with non-empty content + source URL, and shows latency / tokens / cost in the metadata strip"
    why_human: "End-to-end correctness against live LLM + retrieval cannot be verified programmatically; SC-1 is the operator acceptance gate"
  - test: "Boot the live stack and measure end-to-end p95 chat latency for typical single-turn queries"
    expected: "p95 < 5000ms (RAG-06)"
    why_human: "Real-network latency cannot be measured with unit tests; mocked-stack latency gate (1500ms) is in tests/test_chat_route.py:189-207 but only verifies overhead, not the LLM call"
  - test: "Verify the admin Re-index button against the real claude-docs source directory"
    expected: "Clicking re-index from /admin starts a job that processes >0 docs and writes >0 chunks"
    why_human: "tracer_ai/api/admin.py:234 hard-codes `Path('claude-docs')` as the source — this resolves relative to the API's CWD and there is no `claude-docs/` directory at repo root (the fixture lives at fixtures/claude-docs-sample). The button will silently complete with docs_processed=0 unless the operator pre-creates the directory or runs from a directory where it exists. Confirm the deployment story."
---

# Phase 3: RAG Pipeline + Chat UI + Corpus Admin Verification Report

**Phase Goal:** A working RAG chatbot answers questions about the Claude API docs with citation-backed answers, and an operator can manage the corpus from a UI.
**Verified:** 2026-05-06T06:09:09Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (Roadmap Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Asking 5 hand-picked questions about the Claude API returns accurate, cited answers with latency, token count, and estimated cost visible in the chat UI | ⚠️ PARTIAL | Pipeline + SSE + MetadataStrip implemented; latency/tokens/cost path works (frontend/src/components/MetadataStrip.tsx); cited-chunk display BROKEN by wire-shape drift; live correctness needs human gate |
| 2 | Each retrieved chunk is cited inline and expandable; each message links to its trace, route must not 404 | ✗ FAILED | Trace link present + route renders (TraceStub.tsx), but inline citation accordion will display undefined for c.doc_id, c.source_url, c.content — backend emits {idx, doc_url, section_title, text, score}; frontend reads {idx, doc_id, doc_section, section_title, source_url, content, score} |
| 3 | Admin UI at /admin shows current corpus (doc list, chunk count, embedding model, last-indexed timestamp) and a re-index button that triggers ingestion | ✓ VERIFIED | tracer_ai/api/admin.py + frontend/src/pages/Admin.tsx + CorpusCards.tsx + DocList.tsx + ReindexButton.tsx all present and wired; /admin/corpus returns the four required aggregates plus per-doc table; ingest button triggers POST /admin/ingest |
| 4 | Corpus ingested with one embedding model triggers a startup assertion failure if config changes to a different model (CORP-04) | ✓ VERIFIED | tracer_ai/api/lifespan.py:67-89 reads chunks.embedding_model and raises CorpusEmbeddingMismatchError before port binds; tests/test_lifespan_corpus_assertion.py:93+ proves the mismatch path raises and pool closes; 4/4 lifespan tests pass |
| 5 | End-to-end chat latency under 5 seconds for a typical single-user query | ⚠️ PARTIAL | Mocked-stack RAG-06 gate (< 1500ms) is automated and passes (tests/test_chat_route.py:189-207); real-network p95 < 5000ms cannot be verified without a live LLM — human gate |

**Score:** 3/5 truths verified · 2 partial/failed

### Deferred Items

| # | Item | Addressed In | Evidence |
|---|------|--------------|----------|
| 1 | Trace explorer viewer behind /traces/{id} | Phase 4 | Phase 3 ROADMAP scope explicitly says "Phase 4 builds the actual viewer; the link must be present and the route must not 404" — TraceStub.tsx satisfies the Phase 3 contract |

### Required Artifacts (Per-Plan Deliverables)

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `tracer_ai/rag/protocols.py` | Embedder/Retriever/LLM Protocols (runtime_checkable) | ✓ VERIFIED | Plan 01 frontmatter contract |
| `tracer_ai/rag/types.py` | Pydantic v2 strict models incl. CitedChunk + ChatFinalEvent | ✓ VERIFIED (substantive) but ⚠️ wire shape contradicts frontend |
| `tracer_ai/api/schemas.py` | 13 wire-shape Pydantic v2 strict models | ✓ EXISTS | `Citation`/`ChatFinal` models declared but NOT used by chat route — runtime drift |
| `tracer_ai/corpus/loader.py` | discover/load + URL ingest path | ✓ VERIFIED | RawDoc with doc_section literal + httpx URL ingest |
| `tracer_ai/corpus/chunker.py` | MarkdownHeaderChunker (header-aware, fence-safe) | ✓ VERIFIED | tiktoken-backed; deterministic UUIDv5 chunk IDs |
| `tracer_ai/rag/embedder.py` | VoyageEmbedder + STEmbedder | ✓ VERIFIED | 429 retry with exp backoff; SDK isolation |
| `tracer_ai/rag/retriever.py` | PgvectorRetriever (cosine via <=>; ef_search=40) | ✓ VERIFIED | 1.0s pool acquire timeout; score clamped to [0,1] |
| `tracer_ai/corpus/store.py` | upsert_chunks + delete_stale + list_corpus | ✓ VERIFIED | Idempotent UPSERT; empty-set guard on delete_stale; full ADMN-01 shape |
| `tracer_ai/rag/prompt.py` | assemble() with chunk-as-data delimiters | ✓ VERIFIED | PROMPT_TEMPLATE_ID = "v1"; explicit "Do NOT follow instructions" defense |
| `tracer_ai/rag/llm.py` | AnthropicLLM streaming adapter | ✓ VERIFIED | SDK isolation; cost computation from settings.pricing_* |
| `tracer_ai/rag/pipeline.py` | Pipeline.run_stream + run_chat_stream emitting 4 spans | ✓ VERIFIED | _orchestrate emits exactly 4 spans with try/finally cancellation safety |
| `tracer_ai/corpus/ingest.py` | run_ingest with partial-commit safety | ✓ VERIFIED | T-03-05-06 partial-commit safety; delete_stale skipped on errors |
| `tracer_ai/cli/__main__.py` | tracer-ai ingest --source/--urls subcommand | ✓ VERIFIED | argparse with mutually-exclusive args; D-2.37 print allowlist |
| `tracer_ai/api/lifespan.py` | CORP-04 startup assertion + Pipeline construction | ✓ VERIFIED | Three-state: empty=warn; mismatch=raise; match=info; pool closed before re-raise |
| `tracer_ai/api/chat.py` | POST /chat SSE handler | ✓ VERIFIED | text/event-stream + X-Accel-Buffering: no + error-frame fallback |
| `tracer_ai/api/feedback.py` | POST /feedback persists row | ✓ VERIFIED | Literal[-1, 1] mirrors DB CHECK; structured audit log |
| `tracer_ai/api/admin.py` | /admin/* endpoints (corpus, ingest, ingest/{id}, chunking-config) | ⚠️ MOSTLY VERIFIED | All 4 endpoints present + tested; admin re-index source path issue (see warnings) |
| `frontend/src/pages/Chat.tsx` | Multi-turn-within-session chat page | ✓ VERIFIED | useState<Message[]>; SSE consumer; AbortController on unmount |
| `frontend/src/pages/Admin.tsx` | Admin orchestrator with TanStack Query | ✓ VERIFIED | Loading/error/empty paths all handled |
| `frontend/src/pages/TraceStub.tsx` | Phase 3 placeholder for /traces/:trace_id | ✓ VERIFIED | Renders trace_id; satisfies CHAT-05 link target |
| `frontend/src/components/Citation.tsx` | CitationAccordion expander | ✗ STUB-LIKE | EXISTS + IMPORTED + RENDERED but data-flow is HOLLOW — fields it reads (doc_id, source_url, content) are not in the wire payload |
| `frontend/src/components/MetadataStrip.tsx` | Latency/tokens/cost + thumbs + trace link | ✓ VERIFIED | Strict regex contract on display strings |
| `frontend/src/components/ThumbsFeedback.tsx` | Thumbs-up instant; thumbs-down with comment dialog | ✓ VERIFIED | Posts /feedback with rating + comment |
| `frontend/src/components/CorpusCards.tsx` | 4 KPI Tremor Cards | ✓ VERIFIED | DOCUMENTS / CHUNKS / EMBEDDING MODEL / LAST INDEXED labels |
| `frontend/src/components/DocList.tsx` | Per-doc table | ✓ VERIFIED | Tremor Table sorted by doc.id |
| `frontend/src/components/ReindexButton.tsx` | Idle/confirming/running/done/error state machine | ✓ VERIFIED | TanStack Query polling at 2s; useMutation; useQuery enabled gating |
| `frontend/src/components/IngestProgress.tsx` | ProgressBar + elapsed counter | ✓ VERIFIED | 1Hz local tick; auto-stops on terminal status |
| `frontend/src/components/UrlIngestForm.tsx` | URL textarea + per-line ^https?:// validation | ✓ VERIFIED | "Line N: not a URL" inline error; client-side regex matches server schema |
| `frontend/src/components/ChunkingConfigForm.tsx` | Number inputs with bounds | ✓ VERIFIED | chunk_size [100,4000] / overlap [0,500] |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `tracer_ai/api/chat.py` | `tracer_ai/rag/pipeline.py` | `request.app.state.pipeline.run_chat_stream` | ✓ WIRED | lifespan.py:115 stashes Pipeline on app.state |
| `tracer_ai/api/admin.py` | `tracer_ai/corpus/store.py` | `list_corpus(pool)` | ✓ WIRED | get_corpus passes app.state.db_pool to list_corpus |
| `tracer_ai/api/admin.py` | `tracer_ai/corpus/ingest.py` | `run_ingest(...)` via BackgroundTasks | ✓ WIRED | _run_ingest_job constructs VoyageEmbedder + MarkdownHeaderChunker and dispatches |
| `tracer_ai/api/lifespan.py` | `chunks.embedding_model` row | `SELECT ... FROM chunks ORDER BY indexed_at DESC LIMIT 1` | ✓ WIRED | CorpusEmbeddingMismatchError raised before port binds; pool closed |
| `frontend/src/pages/Chat.tsx` | `POST /chat` | `postChat()` async generator → fetch | ✓ WIRED | Streams SSEEvent frames; mutates assistant message on each token |
| `frontend/src/pages/Admin.tsx` | `GET /admin/corpus` | `getCorpus()` via TanStack Query | ✓ WIRED | useQuery with staleTime; isLoading/isError/data branches all rendered |
| `frontend/src/components/MessageBubble.tsx` | `frontend/src/components/Citation.tsx` | `CitationAccordion chunks={cited_chunks}` | ⚠️ WIRED but HOLLOW | Component receives the array but renders fields not in the payload |
| `frontend/src/components/MetadataStrip.tsx` | `/traces/:trace_id` | React-Router `Link` | ✓ WIRED | href="/traces/{trace_id}" matches router.tsx route; TraceStub renders |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|-------------------|--------|
| `Chat.tsx` | `messages` (ChatMessage[]) | postChat() SSE stream | YES (real tokens flow) | ✓ FLOWING |
| `Citation.tsx` (CitationAccordion) | `chunks: Citation[]` from `cited_chunks` prop | `final.cited_chunks` from SSE | NO — fields {doc_id, source_url, content} are NOT in CitedChunk wire payload | ✗ HOLLOW_PROP |
| `MetadataStrip.tsx` | `latency_ms`, `input_tokens`, `output_tokens`, `estimated_cost_usd` | ChatFinalEvent | YES (matching field names) | ✓ FLOWING |
| `Admin.tsx` (CorpusCards/DocList) | `corpus: CorpusState` | `getCorpus()` → list_corpus(pool) → COUNT/MAX over chunks | YES (real DB aggregates) | ✓ FLOWING |
| `ReindexButton.tsx` | `statusQuery.data` | `getIngestStatus()` polling /admin/ingest/{id} | YES — driven by JobState dict in admin.py | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Backend test suite | `.venv/Scripts/python.exe -m pytest` | 180 passed, 1 skipped | ✓ PASS (matches baseline 181 collected) |
| Backend mypy --strict | `mypy --strict tracer_ai` | Success: no issues found in 36 source files | ✓ PASS |
| Backend ruff | `ruff check tracer_ai` | All checks passed | ✓ PASS |
| Frontend tsc | `npx tsc --noEmit` (frontend/) | No errors | ✓ PASS |
| Anti-pattern grep | `pytest tests/test_anti_patterns.py` | 7/7 passed | ✓ PASS |
| CitedChunk JSON shape | `python -c "from tracer_ai.rag.types import CitedChunk; ..."` | `{idx, doc_url, section_title, text, score}` | ✓ Confirms wire-shape drift |
| Admin route tests | `pytest tests/test_admin_routes.py` | 9/9 passed | ✓ PASS |
| Pipeline tests | `pytest tests/test_pipeline.py` | 6/6 passed | ✓ PASS |
| Chat route tests (incl. RAG-06 mocked-stack gate) | `pytest tests/test_chat_route.py` | 7/7 passed | ✓ PASS |
| CORP-04 lifespan tests | `pytest tests/test_lifespan_corpus_assertion.py` | 4/4 passed | ✓ PASS |

(Frontend Playwright e2e tests deliberately not run per runtime_notes — they pass against stubbed APIs but those stubs use the OLD wire shape and would not catch the live drift.)

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| CORP-01 | 02, 05 | CLI ingest pulls/parses Claude docs | ✓ SATISFIED | tracer_ai/cli/__main__.py + corpus/loader.py + ingest.py |
| CORP-02 | 02, 05 | Markdown-header-aware chunker, fence-safe | ✓ SATISFIED | tracer_ai/corpus/chunker.py:53+ MarkdownHeaderChunker |
| CORP-03 | 03, 04 | Each chunk row stores embedding_model + version + indexed_at | ✓ SATISFIED | tracer_ai/corpus/store.py UPSERT writes triple on INSERT and DO UPDATE |
| CORP-04 | 03 | Startup assertion fails on embedding-model mismatch | ✓ SATISFIED | tracer_ai/api/lifespan.py:67-89 + tests/test_lifespan_corpus_assertion.py |
| CORP-05 | 01, 03 | Embedder Protocol + Voyage primary + ST fallback | ✓ SATISFIED | tracer_ai/rag/embedder.py:32 VoyageEmbedder + :139 STEmbedder |
| RAG-01 | 01, 04 | Retriever Protocol with pgvector adapter, top_k=5 | ✓ SATISFIED | tracer_ai/rag/retriever.py:33 PgvectorRetriever |
| RAG-02 | 01, 05 | Prompt assembler with chunk-as-data delimiters | ✓ SATISFIED | tracer_ai/rag/prompt.py:65 assemble + chunks-as-data system prompt |
| RAG-03 | 01, 05 | LLM Protocol + Anthropic adapter + cost estimate | ✓ SATISFIED | tracer_ai/rag/llm.py AnthropicLLM + _cost_per_mtok |
| RAG-04 | 01, 05 | pipeline.run returns answer + chunks + tokens + cost | ✓ SATISFIED | tracer_ai/rag/pipeline.py Pipeline class |
| RAG-05 | 01, 06 | POST /chat returns answer + chunks + latency + tokens + cost + trace_id | ⚠️ PARTIAL | Endpoint returns SSE stream with all fields, but cited_chunks shape disagrees with frontend Citation type |
| RAG-06 | 06 | < 5s typical single-user latency | ⚠️ NEEDS HUMAN | Mocked-stack < 1500ms gate passes; real-LLM gate is human verification |
| CHAT-01 | 08 | Single/multi-turn chat at /chat | ✓ SATISFIED | frontend/src/pages/Chat.tsx multi-turn within session |
| CHAT-02 | 08 | Each message renders answer + cited source chunks (clickable to expand) | ✗ BLOCKED | CitationAccordion exists but renders undefined for chunk body and source URL — wire-shape drift |
| CHAT-03 | 08 | Latency, token count, cost per message | ✓ SATISFIED | MetadataStrip.tsx with regex-strict format strings |
| CHAT-04 | 06, 08 | Thumbs-up/down + comment | ✓ SATISFIED | ThumbsFeedback.tsx + POST /feedback (Literal[-1,1] + DB CHECK) |
| CHAT-05 | 08 | Link to full trace | ✓ SATISFIED | MetadataStrip Link to /traces/{trace_id} + TraceStub.tsx route |
| ADMN-01 | 07, 09 | /admin shows doc list, chunk count, embedding model, last-indexed | ✓ SATISFIED | Admin.tsx + CorpusCards.tsx + DocList.tsx; GET /admin/corpus returns all four aggregates |
| ADMN-02 | 07, 09 | Re-index button triggers ingestion | ⚠️ PARTIAL | ReindexButton + POST /admin/ingest are wired; admin.py:234 hard-codes Path("claude-docs") which is non-existent at repo root — the button silently completes with 0 docs unless the operator pre-creates the directory (see human verification) |
| ADMN-03 | 07, 09 | Chunking config form persists | ✓ SATISFIED | ChunkingConfigForm.tsx + PATCH /admin/chunking-config (in-memory; next-ingest-applies semantics documented) |
| ADMN-04 | 07, 09 | URL-list textarea for URL ingestion | ✓ SATISFIED | UrlIngestForm.tsx + IngestUrlsRequest schema with per-line "Line N" validator |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `frontend/src/components/Citation.tsx` | 62-77 | Reads `c.doc_id`, `c.source_url`, `c.content` which are NOT in the live SSE payload | 🛑 BLOCKER | Chat citations render with undefined chunk body and missing source URL |
| `frontend/tests/chat.spec.ts` | 43-52, 12-20 | SAMPLE_CHUNK and sseBody helper stub the OLD wire shape | ⚠️ WARNING | Tests pass but cannot catch the wire-shape drift |
| `tracer_ai/api/admin.py` | 234 | `Path(source) if source == "claude-docs" else None` — hard-codes a relative directory `Path("claude-docs")` that is not present at repo root | ⚠️ WARNING | Re-index button silently produces 0 docs/chunks unless operator pre-creates the directory |
| `tracer_ai/api/schemas.py` | 45-69 | `Citation` and `ChatFinal` models present but NOT used as response_model on the chat route | ℹ️ INFO | Dead schema; chat.py serializes `ChatFinalEvent` directly via model_dump |

### Human Verification Required

#### 1. Live RAG correctness (5 hand-picked questions)

**Test:** Boot the live stack with real Voyage + Anthropic keys; ingest a real claude-docs corpus; ask 5 hand-picked questions covering different doc sections (auth, messages, tools, prompt-caching, agent-sdk).
**Expected:** Each answer is accurate, contains inline `[n]` markers, and clicking the Sources accordion reveals expandable chunks with non-empty content + a clickable source URL.
**Why human:** End-to-end correctness against a live LLM cannot be verified programmatically. SC-1 is the operator acceptance gate. Note: this test will currently FAIL the citation-body and source-URL display until the SC-2 wire-shape drift is fixed.

#### 2. Real-network p95 latency (RAG-06)

**Test:** Boot the live stack; issue 20 typical-length single-turn chat queries; measure end-to-end p95 latency from request send to final-frame receive.
**Expected:** p95 < 5000ms.
**Why human:** Real LLM and embedder network latency cannot be measured with unit tests. The mocked-stack < 1500ms gate (`tests/test_chat_route.py::test_chat_end_to_end_latency`) only verifies framework overhead.

#### 3. Admin re-index button against real corpus

**Test:** From a fresh Docker compose stack, click "Re-index corpus" in the Admin UI.
**Expected:** Job transitions queued → running → succeeded with `docs_processed > 0` and `chunks_written > 0`.
**Why human:** `tracer_ai/api/admin.py:234` resolves `source` as `Path("claude-docs")` — relative to the API process CWD. There is no `claude-docs/` directory at repo root (the fixture lives at `fixtures/claude-docs-sample`). Confirm whether the deployment story is to (a) symlink/copy claude-docs into the API CWD, (b) update admin.py to use `fixtures/claude-docs-sample` or a configurable path, or (c) accept that admins must use the URL ingest flow instead. The current code may be intentional pending a real ingestion script in Phase 7.

### Gaps Summary

The phase delivers extensive correct infrastructure: the RAG pipeline, SSE streaming, admin endpoints, CORP-04 startup assertion, all 9 frontend components, MetadataStrip, ThumbsFeedback, ReindexButton state machine, and the URL ingest path are all implemented and tested. Backend tests are at 180/181 passing (matching baseline; 1 skipped is intentional). Mypy strict, ruff, and tsc are all clean.

The phase is blocked on **one major issue**: a wire-shape contract drift between the backend `CitedChunk` (Plan 06: `idx, doc_url, section_title, text, score`) and the frontend `Citation` interface (Plan 08: `idx, doc_id, doc_section, section_title, source_url, content, score`). Plan 06 and Plan 08 contradicted on the citation shape, the implementation followed each plan's spec on its own side, and the Playwright tests stub with the OLD shape so they don't catch the live drift. The visible runtime impact: in the chat UI, the Sources accordion will display `[1]  ·  · 0.xx` (undefined doc_id and missing source URL link) and an empty chunk-body `<pre>` block — **directly breaking SC-2 (cited inline + expandable)**. This is also why **SC-1 (5 hand-picked questions with cited answers)** cannot pass even after manual smoke testing until the drift is reconciled.

A secondary concern is the admin re-index source path (`Path("claude-docs")`) which resolves to a non-existent directory at repo root and would silently produce a no-op job. This degrades ADMN-02 in practice but does not block the goal because the URL-list ingest path works correctly.

CORP-04 (SC-4) is fully verified by automated tests. RAG-06 (SC-5) is partially verified via a mocked-stack 1500ms gate; real-network < 5000ms is a human verification gate. Trace-explorer linkage (SC-2 second clause) is satisfied by `TraceStub.tsx` per the Phase 3 → Phase 4 boundary documented in the roadmap.

Recommended fix path for the wire-shape gap: keep `CitedChunk` (Plan 06 shape) as source of truth, update `frontend/src/lib/api.ts` Citation interface to `{idx, doc_url, section_title, text, score}`, update `Citation.tsx` accordion render to use `c.text` for body and `c.doc_url` for click-through, and update `frontend/tests/chat.spec.ts` SAMPLE_CHUNK and sseBody helper to match. Optionally remove or align the unused `Citation`/`ChatFinal` models in `tracer_ai/api/schemas.py` (Plan 01 dead code).

---

*Verified: 2026-05-06T06:09:09Z*
*Verifier: Claude (gsd-verifier)*
