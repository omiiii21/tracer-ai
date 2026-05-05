---
phase: 03-rag-pipeline-chat-ui-corpus-admin
plan: 02
subsystem: corpus
tags: [pydantic-v2, tiktoken, structlog, httpx, uuidv5, markdown-chunker, fence-safety]

# Dependency graph
requires:
  - phase: 03-rag-pipeline-chat-ui-corpus-admin
    plan: 01
    provides: tracer_ai/api/schemas.py Citation shape (idx, doc_id, doc_section, section_title, source_url, content, score) -- chunker.metadata fields chosen to map cleanly to this consumer shape; tracer_ai/rag/types.py RetrievedChunk Pydantic-strict pattern reused on Chunk
  - phase: 02-skeleton-infrastructure
    provides: Pydantic v2 ConfigDict(extra="forbid") strict-mode pattern (tracer_ai/api/health.py:27-33); structlog.get_logger() at module top idiom (health.py:23); 12-section canonical taxonomy (docs/eval/coverage_set.yaml); tiktoken installed via pyproject.toml; corpus/ -> rag.embedder narrow exception in import_cycle_guard.py
  - phase: 01-research-design-artifacts
    provides: ADR 006 chunking strategy (chunk_size=900, overlap=100, top_k=5 defaults); coverage_set.yaml 12 doc_section values; chunks DDL constraint in alembic 0001 (chunks.id UUID PK, doc_section TEXT NOT NULL, metadata JSONB)
provides:
  - tracer_ai.corpus.types.RawDoc + Chunk Pydantic v2 strict models
  - tracer_ai.corpus.types.DocSection Literal (12-section canonical taxonomy mirror)
  - tracer_ai.corpus.loader.discover() + load() async filesystem ingest path
  - tracer_ai.corpus.loader.discover_urls() + load_url() async URL-list ingest path with httpx (30s timeout, follow_redirects=True)
  - tracer_ai.corpus.loader._infer_section() with fallback warning to agent-sdk-overview
  - tracer_ai.corpus.chunker.Chunker Protocol (runtime_checkable)
  - tracer_ai.corpus.chunker.MarkdownHeaderChunker (header-aware, fence-safe, configurable size/overlap, deterministic UUIDv5 chunk IDs)
  - fixtures/claude-docs-sample/{auth,messages}.md minimal corpus fixture
affects: [03-03-embedder-retriever, 03-04-prompt-llm-pipeline, 03-06-admin-feedback-ui, 04-tracer-postgres-writer]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Literal-mirror-via-frozenset: DocSection Literal in types.py + _ALLOWED_SECTIONS frozenset in loader.py for O(1) runtime membership without losing single-source-of-truth typing"
    - "Fence-safe overlap carry: drop tail with odd ``` parity to preserve T-03-02-01 invariant (chunk.content.count('```') % 2 == 0 for every chunk)"
    - "Sub-split long single-line text at token boundaries OUTSIDE fences only (preserves code-block integrity while bounding chunk size)"
    - "Deterministic UUIDv5 from (doc_id, chunk_index) for idempotent re-ingest"
    - "httpx.MockTransport for unit-testing async URL ingest without network"
    - "structlog.testing.capture_logs() to assert structured warning events"

key-files:
  created:
    - tracer_ai/corpus/types.py
    - tracer_ai/corpus/loader.py
    - tracer_ai/corpus/chunker.py
    - tests/test_loader.py
    - tests/test_chunker.py
    - fixtures/claude-docs-sample/auth.md
    - fixtures/claude-docs-sample/messages.md
  modified: []

key-decisions:
  - "DocSection Literal in types.py is the single source of truth; loader's _ALLOWED_SECTIONS frozenset is a runtime mirror used only for membership tests"
  - "Carry-overlap drops the tail when its decoded text has odd ``` or ~~~ parity rather than attempting to repair fence state -- trades semantic continuity for the load-bearing fence-safety invariant"
  - "Long single-line markdown bodies sub-split at token boundaries outside fences; sub-splitting suppressed inside fences so code-block integrity wins over uniform chunk size"
  - "URL-ingest defaults doc_section to agent-sdk-overview (admin can re-tag in v2 per plan); never silently miscategorizes"
  - "_infer_section() tries parent dir name THEN file stem before falling back; structured warning emitted on miss so corpus drift is observable"
  - "discover_urls() is sync identity (not async) -- no FS walk needed; symmetry with discover() preserved at the call-site level"
  - "Fixtures live at fixtures/claude-docs-sample/ (NOT tests/fixtures) to make them reusable by future ingest CLI smoke tests in Phase 3 Plan 06+"

patterns-established:
  - "Corpus types module imports stdlib + pydantic only (corpus is layer-1 in import DAG; SDK adapters live elsewhere per D-2.38)"
  - "Acceptance grep that catches docstring false positives must be a real-import scan (^\\s*import|^\\s*from) not a substring match -- learned from Plan 03-01 deviation #1; preempted here by avoiding the substring 'voyageai/anthropic' in module docstrings"
  - "Chunker bounds enforced in __init__ (chunk_size in [100, 4000]; overlap in [0, min(500, chunk_size-1)]) so out-of-range config fails fast at construction, not at split-time"
  - "Chunker emits structured log on every split (doc_id + chunks + chunk_size + overlap) -- T-03-02-06 audit-trail mitigation"

requirements-completed:
  - CORP-01
  - CORP-02

# Metrics
duration: 5min
completed: 2026-05-05
---

# Phase 3 Plan 02: Corpus Loader + Markdown Chunker Summary

**Header-aware, fence-safe MarkdownHeaderChunker + filesystem/URL loader producing RawDoc/Chunk Pydantic-strict types with deterministic UUIDv5 chunk IDs and 12-section canonical taxonomy enforcement.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-05-05T08:49:03Z
- **Completed:** 2026-05-05T08:54:23Z
- **Tasks:** 2 (both type="auto" tdd="true")
- **Files modified:** 7 created (3 source + 2 test + 2 fixture) + 0 modified

## Accomplishments

- **RawDoc + Chunk Pydantic v2 strict models** in `tracer_ai/corpus/types.py` with the `DocSection` Literal mirroring the 12-section canonical taxonomy from `docs/eval/coverage_set.yaml`. `extra='forbid'` on both models; `Chunk.chunk_index: int = Field(ge=0)`; `Chunk.metadata: dict[str, Any] = Field(default_factory=dict)` so unset metadata is `{}` not shared-mutable-default.
- **Async filesystem + URL ingest paths** in `tracer_ai/corpus/loader.py`. `discover()` returns sorted `**/*.md` for deterministic order; `load()` infers `doc_section` via parent-dir-then-file-stem with structured-warning fallback to `agent-sdk-overview` (T-03-02-04). `load_url()` accepts an injected `httpx.AsyncClient` (testable without network) and defaults to a 30s-timeout client (T-03-02-03 DoS mitigation).
- **Header-aware, fence-safe `MarkdownHeaderChunker`** in `tracer_ai/corpus/chunker.py`. Walks the doc line-by-line tracking `inside_fence`; h2/h3 split candidates are gated by `not inside_fence`; size-emit is gated by `not inside_fence`. Carry-overlap drops tails with odd ``` parity to preserve the T-03-02-01 invariant `chunk.content.count("```") % 2 == 0` for EVERY chunk. Long single-line text sub-splits at token boundaries OUTSIDE fences (RESEARCH.md §2's "tokenize into stream of (kind, text) events" implemented as line-walk + sub-line slicing).
- **Deterministic UUIDv5 chunk IDs** of `(doc_id, chunk_index)` -- re-running `MarkdownHeaderChunker().split(doc)` twice produces identical UUID lists; this is the on-disk idempotency guarantee for `INSERT ... ON CONFLICT (id) DO UPDATE` (RESEARCH.md §2 idempotency, exercised by `test_chunker_deterministic_uuids`).
- **22 tests + mypy --strict clean** across `types.py`, `loader.py`, `chunker.py`. Fence-safety test (`test_chunker_never_splits_inside_fence`) and the "header-inside-fence-as-text" test (`test_chunker_handles_header_inside_fence_as_text_not_split`) pin the load-bearing T-03-02-01 mitigation; plus deterministic-UUID test, multi-header split test, header_path breadcrumb test, configurable-size test, headerless-fallback test, bounds tests, and Protocol structural-acceptance test.

## Task Commits

Each task was committed atomically (TDD: tests + impl shipped together since each task introduces new modules and the failing test confirms module absence in <1s):

1. **Task 1: corpus/types.py + corpus/loader.py + tests + fixtures** -- `2466eea` (feat)
2. **Task 2: corpus/chunker.py + tests/test_chunker.py** -- `a695c95` (feat)

## Files Created/Modified

**Created:**
- `tracer_ai/corpus/types.py` -- RawDoc + Chunk Pydantic v2 strict models; DocSection Literal (12 values).
- `tracer_ai/corpus/loader.py` -- async `discover()`, `load()`, `discover_urls()`, `load_url()`; `_infer_section()` with structured warning on fallback.
- `tracer_ai/corpus/chunker.py` -- `Chunker` Protocol (runtime_checkable) + `MarkdownHeaderChunker` (header-aware, fence-safe, configurable size/overlap, deterministic UUIDv5).
- `tests/test_loader.py` -- 11 tests covering discover, load, _infer_section, RawDoc validation, discover_urls identity, load_url via httpx.MockTransport, load_url HTTP error propagation.
- `tests/test_chunker.py` -- 11 tests covering fence-safety (incl. headers-inside-fences), multi-header splits, deterministic UUIDs, metadata header_path, configurable chunk_size, headerless fallback, bounds enforcement, Protocol structural acceptance, h3-under-h2 breadcrumb.
- `fixtures/claude-docs-sample/auth.md` -- minimal auth fixture with one h2 + one fenced code block.
- `fixtures/claude-docs-sample/messages.md` -- minimal messages fixture with h2 + h3 + fenced code block.

**Modified:** none.

## Decisions Made

- **Sub-split long single-line text at token boundaries:** the plan-pseudocode chunker walks line-by-line; when a markdown body has its entire prose on one line (a real pattern, not just a test artifact), the line-based emit can't bound chunk size. Implemented per-line tiktoken-encode + slice + decode + emit when a non-fence non-header line exceeds `chunk_size`. Sub-splitting is suppressed inside fences (preserves code-block integrity) and on header lines (preserves split-at-header semantics).
- **Drop overlap tail on odd fence parity:** the plan's overlap carry-forward (last `overlap` tokens of emitted content fed to the next chunk) can put the next chunk in mid-fence state if the tail starts inside a code block. Tracking `inside_fence` across the carry-forward boundary would be brittle; instead, the tail is dropped if its decoded text has odd ``` or ~~~ parity. Trades some semantic continuity for the load-bearing T-03-02-01 invariant. Documented inline in chunker.py.
- **Avoid the substring 'voyageai/anthropic' in module docstrings:** Plan 03-01's deviation #1 was a false positive on a docstring-substring scan of "import voyageai". Preempted here by phrasing the corpus/types.py module docstring as "SDK adapters live in `tracer_ai.rag.embedder` / `rag.llm` per D-2.38" rather than "must not import voyageai / anthropic". Real-import scan (`^\\s*import|^\\s*from`) returns 0 hits.
- **httpx.AsyncClient injectable in load_url():** rather than instantiating internally and mocking via patch, the function takes `client: httpx.AsyncClient | None = None`. Tests pass an `httpx.MockTransport`-backed client; production passes None to get the 30s-timeout default. Avoids `unittest.mock` plumbing entirely.
- **Fixtures live at `fixtures/` (repo root) not `tests/fixtures/`:** future Phase 3 Plan 06+ ingest CLI smoke tests will reuse the same fixture, so it lives outside the tests/ tree. `tests/fixtures/` is reserved for test-only artifacts (e.g., the deliberate type-error fixture at `tests/fixtures/broken.py`).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 -- Bug] chunker_chunk_size_is_honored failed on single-line bodies**

- **Found during:** Task 2 (initial pytest run after writing chunker.py)
- **Issue:** Test 5 (`test_chunker_chunk_size_is_honored`) compared chunk counts at `chunk_size=900` vs `chunk_size=300` against a doc whose body was a single long line. The line-based chunker added the entire body in one append; the size-emit fired once afterwards. Result: 2 chunks at both sizes -- `len(small) > len(big)` failed (`assert 2 > 2`).
- **Fix:** Added a sub-split branch in `MarkdownHeaderChunker.split()`: if a non-fence, non-header line's token count exceeds `self.chunk_size`, encode the line via tiktoken, slice into chunk_size-bounded segments, decode each segment, append to buffer, and emit on size threshold. Sub-splitting is suppressed inside fences (preserves code-block integrity) and on header lines (preserves split-at-header semantics).
- **Files modified:** `tracer_ai/corpus/chunker.py`
- **Verification:** All 11 chunker tests pass; fence-safety test confirms code-block-integrity preserved post-fix; configurable-size test now reports `len(small)=12, len(big)=4` for the same input.
- **Committed in:** `a695c95` (Task 2 commit, fix folded into the same atomic commit -- the failing test was discovered before any commit landed)

**2. [Hook-driven] ruff-format reformatted test_loader.py and chunker.py on commit**

- **Found during:** Task 1 commit and Task 2 commit
- **Issue:** Pre-commit `ruff-format` hook reformatted line breaks (e.g., merged a multi-line list comprehension; collapsed argument list) and aborted the first commit invocation.
- **Fix:** Re-staged the formatted file and re-ran `git commit`. All hooks (ruff, ruff-format, gitleaks, mypy --strict, pytest --testmon, import-cycle-guard, anti-pattern grep) reported PASS on the second invocation.
- **Files modified:** `tests/test_loader.py` (Task 1), `tracer_ai/corpus/chunker.py` (Task 2)
- **Verification:** Re-running `pytest` and `mypy --strict` confirmed equivalence; reformatted files preserve all test behaviors.
- **Committed in:** both task commits (effects baked in)

---

**Total deviations:** 2 (1 Rule 1 test-discovered correctness gap auto-fixed; 1 hook-driven reformat).
**Impact on plan:** No scope change. The Rule 1 fix is a hardening of the chunker's size-bounding guarantee against a real pattern (single-line markdown bodies); without it, the plan's "average chunk token count is closer to 600 than 900 (ADMN-03 contract)" intent would silently regress on real docs. The hook reformat is a normal pre-commit interaction.

## Issues Encountered

- **None during planned work.** The single chunker bug above was discovered by the plan's own test list, not by an unrelated path.

## Threat Mitigations Applied

| Threat ID | Status | Where |
|-----------|--------|-------|
| T-03-02-01 (Tampering -- chunker fence handling) | Mitigated | `MarkdownHeaderChunker` walks fence state; size-emit and h2/h3-split both gated by `not inside_fence`; carry-overlap drops tail on odd fence parity; `test_chunker_never_splits_inside_fence` and `test_chunker_handles_header_inside_fence_as_text_not_split` are the CI-enforced witnesses. |
| T-03-02-02 (Info disclosure -- file:// URL leak) | Accepted | `source_url=file://{absolute path}` is intentional for citations; v1 is single-user local-dev per CLAUDE.md. |
| T-03-02-03 (DoS -- URL ingest) | Mitigated | `load_url()` defaults to `httpx.AsyncClient(timeout=30.0, follow_redirects=True)`; URL-list batch bound (`min_length=1, max_length=100`) is enforced upstream in `api/schemas.py` from Plan 03-01. |
| T-03-02-04 (Tampering -- section inference) | Mitigated | `_infer_section()` falls back to `agent-sdk-overview` and emits `corpus_section_unknown` warning; `RawDoc.doc_section: DocSection` Literal rejects out-of-enum values at construction time. |
| T-03-02-05 (Spoofing -- UUIDv5 chunk IDs) | Accepted | UUIDv5 is deterministic but non-secret; idempotent re-ingest is the design (RESEARCH.md §2 D-2). |
| T-03-02-06 (Repudiation -- chunker logging) | Mitigated | `chunker_split` log emits `doc_id + chunks + chunk_size + overlap` on every split; `corpus_discover` emits `source_dir + count`; `corpus_discover_urls` emits `count`. |

## Self-Check: PASSED

- File `tracer_ai/corpus/types.py` exists. Verified.
- File `tracer_ai/corpus/loader.py` exists. Verified.
- File `tracer_ai/corpus/chunker.py` exists. Verified.
- File `tests/test_loader.py` exists. Verified.
- File `tests/test_chunker.py` exists. Verified.
- File `fixtures/claude-docs-sample/auth.md` exists. Verified.
- File `fixtures/claude-docs-sample/messages.md` exists. Verified.
- Commit `2466eea` (Task 1) exists in `git log`. Verified.
- Commit `a695c95` (Task 2) exists in `git log`. Verified.
- `pytest tests/test_loader.py tests/test_chunker.py -q` -> 22 passed.
- `mypy --strict tracer_ai/corpus/types.py tracer_ai/corpus/loader.py tracer_ai/corpus/chunker.py` -> Success: no issues found in 3 source files.
- `pytest tests/test_anti_patterns.py -q` -> 7 passed (no SDK-isolation regression).
- `python infra/scripts/import_cycle_guard.py` -> OK: tracer_ai module DAG check clean (4 layers).
- Acceptance grep counts: `class RawDoc|class Chunk` (types.py) = 2; `async def discover|async def load|async def load_url` (loader.py) = 3; `class Chunker(Protocol)|class MarkdownHeaderChunker` (chunker.py) = 2; `inside_fence` (chunker.py) = 7 (>= 2); `uuid5` (chunker.py) = 3 (>= 1); real-import scan for `import anthropic|import voyageai` in `tracer_ai/corpus/` = 0.

## User Setup Required

None -- no external service configuration required. Filesystem ingest reads from `fixtures/claude-docs-sample/` which is checked in; URL ingest is unit-tested with `httpx.MockTransport` and requires no live network in CI.

## Next Phase Readiness

- **Phase 3 Plan 03 (embedder + retriever):** unblocked. Will consume `Chunk.content` (str) -> embedding via `Embedder.embed_batch()` (Protocol pinned in Plan 03-01); `Chunk.id` (UUIDv5) and `Chunk.metadata` (dict) become the row keys for the `INSERT ... ON CONFLICT (id) DO UPDATE` UPSERT in `tracer_ai/corpus/store.py` (Plan 03-04 or 03-05).
- **Phase 3 Plan 04 (prompt + LLM + pipeline):** unblocked. The `RetrievedChunk.metadata` plumbing follows the same JSONB shape this plan writes (`section_title`, `header_path`, `source_url`); `prompt.py` reads them back to populate citation badges per RESEARCH.md §3.
- **Phase 3 Plan 06 (admin UI / re-index):** unblocked. The `MarkdownHeaderChunker(chunk_size, overlap)` constructor accepts the admin-tunable params from `Settings.chunking` (Phase 3 modifies `config.py` to add the nested `chunking` block, per PATTERNS.md §"Settings field access" Phase 3 addition); bounds are validated in `__init__` so the PATCH `/admin/chunking-config` endpoint can pass user input directly.
- **Phase 4 (tracer Postgres writer):** orthogonal -- no chunker dependency.

## Threat Flags

None -- no new threat surface introduced beyond the plan's `<threat_model>` register. All file access is read-only from a checked-in fixture path; URL ingest sits behind the existing 30s `httpx` timeout boundary.

---
*Phase: 03-rag-pipeline-chat-ui-corpus-admin*
*Completed: 2026-05-05*
