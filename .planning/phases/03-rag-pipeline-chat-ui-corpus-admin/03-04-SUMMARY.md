---
phase: 03-rag-pipeline-chat-ui-corpus-admin
plan: 04
subsystem: rag/corpus
tags: [pgvector, hnsw, asyncpg, cosine-distance, upsert, on-conflict, idempotent-ingest, sql-injection-safe, structlog]

# Dependency graph
requires:
  - phase: 03-rag-pipeline-chat-ui-corpus-admin
    plan: 01
    provides: Retriever runtime_checkable Protocol in tracer_ai/rag/protocols.py + RetrievedChunk Pydantic-strict model with score in [0, 1] (tracer_ai/rag/types.py)
  - phase: 03-rag-pipeline-chat-ui-corpus-admin
    plan: 02
    provides: Chunk Pydantic-strict model (tracer_ai/corpus/types.py) with deterministic UUIDv5 id from (doc_id, chunk_index) -- the on-disk idempotency anchor for INSERT ... ON CONFLICT (id) DO UPDATE
  - phase: 03-rag-pipeline-chat-ui-corpus-admin
    plan: 03
    provides: Embedder Protocol concrete instances (VoyageEmbedder name="voyage-code-3" dim=1024 / version="voyage-code-3@2025-09") -- the producers of the embeddings list this plan UPSERTs alongside chunks; CORP-04 lifespan assertion that reads back the embedding_model column this plan writes
  - phase: 02-skeleton-infrastructure
    provides: alembic 0001 chunks DDL (id UUID PK, doc_id, chunk_index, doc_section, content, embedding VECTOR(1024), embedding_model TEXT, embedding_model_version TEXT, indexed_at TIMESTAMPTZ DEFAULT now(), metadata JSONB) + chunks_embedding_hnsw (HNSW vector_cosine_ops) + asyncpg pool DI pattern in api/health.py:44-47 + FakePool stub pattern in tests/test_healthz.py:17-44
provides:
  - tracer_ai.rag.retriever.PgvectorRetriever (cosine via <=>; ef_search=40 per query; 1.0s acquire timeout; score clamped to [0,1])
  - tracer_ai.corpus.store.upsert_chunks (idempotent UPSERT with full CORP-03 metadata triple on both INSERT and DO UPDATE branches)
  - tracer_ai.corpus.store.delete_stale (T-03-04-05 safety guard: empty current_doc_ids set is no-op, never wipes corpus)
  - tracer_ai.corpus.store.list_corpus (aggregate-row + per-doc fetch returning the {doc_count, chunk_count, embedding_model, embedding_model_version, last_indexed_at, docs[]} shape consumed by GET /admin/corpus)
affects: [03-05-prompt-pipeline, 03-06-chat-api-sse, 03-07-admin-feedback-ui]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "pgvector string-literal embedding rendering: f-format '[0.1,0.2,...]' with `{x:.6f}` so we don't depend on the optional pgvector-python asyncpg codec being registered AND no user-controlled string can interpolate into the SQL"
    - "Per-query HNSW tuning via SET LOCAL hnsw.ef_search = 40 inside the retrieve transaction (recall vs. speed knob; runtime-tunable without index rebuild)"
    - "Score clamp into [0, 1]: HNSW cosine distance can drift outside the mathematical interval by ~1e-7 on bit-equal vectors; clamp absorbs the drift before Pydantic validation"
    - "Idempotent UPSERT keyed on deterministic UUIDv5 -- re-running ingest produces no duplicate rows; ON CONFLICT (id) DO UPDATE writes the metadata triple on the conflict branch too so indexed_at always reflects the latest run"
    - "Empty-set safety guard for stale-row DELETE: refuses to issue WHERE doc_id <> ALL('{}') -- which is vacuously true and would wipe the table -- short-circuits to no-op + structured warning"
    - "Recording FakeConn pattern (extends test_healthz.py:17-44 FakePool with execute/fetchrow/fetch capture) for unit-testing pool consumers without a live Postgres"

key-files:
  created:
    - tracer_ai/rag/retriever.py
    - tracer_ai/corpus/store.py
    - tests/test_retriever.py
    - tests/test_corpus_store.py
  modified: []

key-decisions:
  - "pgvector string-literal '[...]'::vector parameter rendering, not pgvector-python codec registration: keeps the retriever and store decoupled from the asyncpg pool's codec config; the same module works whether the pgvector-python codec is registered or not. The :.6f format is locale-independent and bounds payload size."
  - "Score clamp to [0, 1] on the asyncpg row, not via Pydantic field_validator: the clamp is a property of the pgvector cosine-distance computation, not of the RetrievedChunk model -- keeping it in the adapter prevents the model from quietly accepting -1e-7 elsewhere."
  - "delete_stale empty-set guard returns 0 + warning, not raises: the corpus pipeline's final-pass DELETE is normal flow when no docs are removed; raising would force every caller to wrap with try/except. The structured warning is observable for the audit trail."
  - "list_corpus uses two queries (aggregate row + per-doc grouping) inside one pool acquire: simpler than a single query with window functions; the pool is held for ~5ms which is fine; the admin route polls /admin/corpus on demand, not hot-path."
  - "Empty-corpus list_corpus returns the same shape with zeros and empty list (not raises): the admin UI must render on a fresh checkout where the chunks table is empty; coercing NULLs to 0/empty string lets the frontend skip null-handling."
  - "Length mismatch in upsert_chunks raises BEFORE pool acquire: a misconfiguration where chunks and embeddings are unaligned must not hold a Postgres connection during the error; the pool stays available for the next caller."

patterns-established:
  - "Adapters that talk to asyncpg use string-literal pgvector rendering (`'[0.1,0.2,...]'::vector`) rather than depending on a registered codec -- decouples module import from pool initialization order"
  - "Recording FakeConn (captures (query, args) tuples) for unit-testing query content + binding shape without a live Postgres -- extends the test_healthz.py FakePool pattern"
  - "Pool acquire timeout sized to operation: 1.0s for retriever (latency-sensitive), 5.0s for upsert (batch write), 2.0s for list_corpus (admin polling, not hot-path)"
  - "asyncpg.execute return-string parsing: 'DELETE N' / 'INSERT 0 N' format; defensive int() with try/except IndexError/ValueError on unexpected shapes"
  - "Single transaction for batch UPSERT (one acquire, one transaction, N execute) -- keeps row writes atomic so a partial-batch failure doesn't leave the metadata triple inconsistent"

requirements-completed:
  - CORP-03
  - RAG-01

# Metrics
duration: 6min
completed: 2026-05-05
---

# Phase 3 Plan 04: Retriever + Corpus Store Summary

**PgvectorRetriever issuing cosine `<=>` queries against the existing `chunks_embedding_hnsw` index with per-query `ef_search=40` tuning + idempotent UPSERT writer that always populates the CORP-03 metadata triple and a safety-guarded stale-row deletion that refuses to wipe the corpus on an empty current-doc set.**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-05-05T09:16:10Z
- **Completed:** 2026-05-05T09:22:18Z
- **Tasks:** 2 (both type="auto" tdd="true")
- **Files modified:** 4 created (2 source + 2 test) + 0 modified

## Accomplishments

- **`PgvectorRetriever`** in `tracer_ai/rag/retriever.py` -- structurally typed as the `Retriever` Protocol pinned in Plan 03-01. One transaction per `retrieve()` call: `SET LOCAL hnsw.ef_search = 40` is issued first, then `SELECT id, doc_id, doc_section, content, metadata, 1 - (embedding <=> $1::vector) AS score FROM chunks ORDER BY embedding <=> $1::vector LIMIT $2`. The cosine `<=>` operator matches the existing `chunks_embedding_hnsw USING hnsw (embedding vector_cosine_ops)` index from `alembic/versions/0001_initial.py:171-175`, so HNSW is used (not a brute-force scan). Score = `1 - cosine_distance` clamped to `[0.0, 1.0]` so HNSW floating-point drift on identical vectors never trips `RetrievedChunk.score: Field(ge=0.0, le=1.0)` validation.
- **`upsert_chunks`** in `tracer_ai/corpus/store.py` -- idempotent UPSERT keyed on the deterministic `Chunk.id` (UUIDv5 from `(doc_id, chunk_index)` per Plan 02). The CORP-03 metadata triple (`embedding_model`, `embedding_model_version`, `indexed_at`) is written on **both** the INSERT branch and the `ON CONFLICT (id) DO UPDATE SET` branch -- this is what keeps the CORP-04 lifespan `ORDER BY indexed_at DESC LIMIT 1` assertion meaningful across re-ingest cycles. Length-mismatch check fires **before** pool acquire so a misconfiguration cannot leak a connection.
- **`delete_stale`** -- parameterized `DELETE FROM chunks WHERE doc_id <> ALL($1::text[])`. The T-03-04-05 safety guard: an empty `current_doc_ids` set short-circuits to no-op + structured warning. Without this guard, `WHERE doc_id <> ALL('{}')` is vacuously true for every row and would wipe the entire chunks table. Behavior witnessed by `test_delete_stale_empty_set_does_not_delete`.
- **`list_corpus`** -- aggregate row (`COUNT(DISTINCT doc_id)`, `COUNT(*)`, `MAX(indexed_at)`, `MAX(embedding_model)`, `MAX(embedding_model_version)`) plus per-doc grouping (`doc_id`, `MIN(doc_section)`, `MIN(metadata->>'source_url')`, `COUNT(*)`, `MAX(indexed_at)`) inside one pool acquire. Returns the nested `{doc_count, chunk_count, embedding_model, embedding_model_version, last_indexed_at, docs[]}` shape consumed by `GET /admin/corpus` (Plan 07). Empty corpus path coerces NULLs to `0` / empty string so the admin UI renders without null checks.
- **17 tests + mypy --strict clean** -- 8 retriever tests (ordered-by-score, score clamp on negative drift + positive overshoot, cosine `<=>` + `LIMIT $2` projection, `ef_search` ordering before SELECT, Protocol structural typing, `top_k <= 0` ValueError, `top_k < 0` ValueError, JSONB-as-str-or-dict path) + 9 store tests (ON CONFLICT shape, metadata-triple on both branches, length-mismatch ValueError without pool touch, empty list returns 0 without pool touch, delete_stale empty-set guard, parameterized DELETE binding, `DELETE N` parse + unparseable fallback, list_corpus nested shape with NULL `source_url`, empty-corpus zero-coercion).

## Task Commits

Each task was committed atomically (TDD: tests + impl shipped together since each task introduces new modules and the failing test confirms module absence in <1s):

1. **Task 1: rag/retriever.py + tests/test_retriever.py** -- `2425a12` (feat)
2. **Task 2: corpus/store.py + tests/test_corpus_store.py** -- `c1dbc69` (feat)

## Files Created/Modified

**Created:**
- `tracer_ai/rag/retriever.py` -- `PgvectorRetriever` (cosine `<=>` against HNSW; ef_search per query; score clamp).
- `tracer_ai/corpus/store.py` -- `upsert_chunks` + `delete_stale` + `list_corpus`.
- `tests/test_retriever.py` -- 8 retriever tests via FakePool stubs.
- `tests/test_corpus_store.py` -- 9 store tests via recording FakeConn.

**Modified:** none.

## Decisions Made

- **pgvector string-literal embedding rendering, not codec registration:** rendering the query embedding as a `[0.1,0.2,...]` literal cast to `::vector` keeps `tracer_ai/rag/retriever.py` decoupled from the asyncpg pool's codec configuration. The same module works whether the optional `pgvector-python` codec is registered on the pool or not -- a smaller surface area for ingest- vs. query-time pool initialization mismatch. The `f"{x:.6f}"` format is locale-independent and prevents any user-controlled string from interpolating into the SQL (T-03-04-01 mitigation). Documented inline.
- **Score clamp lives in the adapter, not the model:** the clamp is a property of the pgvector cosine-distance computation (HNSW arithmetic drift), not of the `RetrievedChunk` shape. Pushing the clamp into a Pydantic `field_validator` would silently accept `-1e-7` from any source; keeping it in the retriever localizes the drift handling to the place that produces it.
- **`delete_stale` empty-set returns 0 + warning, not raises:** the ingest pipeline's final-pass DELETE is part of normal flow when no docs were removed from the source bundle; raising would force every caller to wrap with try/except. The structured `delete_stale_skipped` warning is the audit-trail signal an operator can grep for.
- **`list_corpus` two-query design (aggregate + per-doc) inside one acquire:** simpler than a single query with window functions, while still bounded to one round-trip-set. Pool is held for ~5ms total which is fine -- the admin route polls `/admin/corpus` on demand, not hot-path.
- **Empty-corpus `list_corpus` returns the same shape with zeros + empty list:** the admin UI renders on a fresh checkout where `chunks` is empty; coercing NULLs from `MAX(...)` aggregates to `""` and `COUNT(*)` to `0` lets the frontend skip null-handling. The defensive `if agg is None` branch covers callers who mock `fetchrow=None` even though Postgres always returns a row from `COUNT()`.
- **Length-mismatch raises BEFORE pool acquire in `upsert_chunks`:** a misconfiguration where chunks and embeddings are 1:N or N:M mis-aligned must not hold a Postgres connection during the error; the pool stays available for other callers. The recording-FakeConn test asserts the pool's `executed` list is empty in the mismatch case.
- **Pool acquire timeouts sized to operation:** 1.0s for retriever (latency-sensitive query path; tighter than the default), 5.0s for upsert (batch write may run longer than a single SELECT), 2.0s for `list_corpus` (admin polling, not hot-path, but still bounded so a stuck DB doesn't block the admin UI indefinitely).

## Deviations from Plan

### Auto-fixed Issues

**1. [Hook-driven] ruff SIM117 + SIM108 + ruff-format reformat on Task 1 commit**

- **Found during:** Task 1 commit (initial `git commit` invocation).
- **Issue:** Pre-commit ruff hook flagged SIM117 (nested `with self._pool.acquire(...) as conn: with conn.transaction(): ...` should be a single `with` with multiple comma-separated contexts) and SIM108 (the JSONB-decode `if isinstance(meta_raw, str): meta = json.loads(...) else: meta = meta_raw or {}` should be a ternary). `ruff-format` then reformatted line breaks on the file. The first commit aborted with the lint errors visible.
- **Fix:** Merged the two `async with` statements into one (`async with self._pool.acquire(timeout=1.0) as conn, conn.transaction():`). Replaced the if/else block with a ternary annotated with `dict[str, Any]`. Re-staged and re-ran `git commit`. All hooks (ruff, ruff-format, gitleaks, mypy --strict, pytest --testmon, import-cycle-guard, anti-pattern grep) reported PASS.
- **Files modified:** `tracer_ai/rag/retriever.py`.
- **Verification:** Re-ran `pytest tests/test_retriever.py` (8 passed) and `mypy --strict tracer_ai/rag/retriever.py` (no issues). The reformatted file preserves all test behaviors.
- **Committed in:** `2425a12` (Task 1 commit; fix folded in before any commit landed).

**2. [Hook-driven] ruff RUF043 on Task 2 commit (pytest.raises match without raw string)**

- **Found during:** Task 2 commit (initial `git commit` invocation).
- **Issue:** Pre-commit ruff hook flagged RUF043 on `with pytest.raises(ValueError, match="chunks .* embeddings"):` -- the pattern contains regex metacharacters but the string literal isn't raw. Ruff also flagged I001 (import block un-sorted) on `tests/test_corpus_store.py` and auto-fixed it.
- **Fix:** Changed the match pattern to a raw string: `match=r"chunks .* embeddings"`. The auto-fixed import sort was accepted as-is. Re-ran `git commit`; all gates passed.
- **Files modified:** `tests/test_corpus_store.py`.
- **Verification:** Re-ran `pytest tests/test_corpus_store.py` (9 passed). The match pattern still asserts the same regex.
- **Committed in:** `c1dbc69` (Task 2 commit; fix folded in before any commit landed).

---

**Total deviations:** 2 (both hook-driven lint refinements; no scope change, no behavior change).
**Impact on plan:** No scope creep. The two fixes harden style consistency (single `with` for two contexts, ternary for two-branch assignment, raw-string regex pattern) and the auto-import-sort matches the project convention. All test behaviors preserved.

## Issues Encountered

- **`asyncpg` not on the system Python (3.13.6).** Initial `python -m pytest` against the system interpreter failed at module import because `asyncpg` is only installed in the project's `.venv` (Python 3.12.4). Switched all verification commands to `.venv/Scripts/python.exe` -- this is the same env Phase 2 + Plans 03-01..03 ran tests against. No source change.

## Threat Mitigations Applied

| Threat ID | Status | Where |
|-----------|--------|-------|
| T-03-04-01 (Tampering -- retriever SQL injection) | Mitigated | All SQL values via asyncpg `$1`/`$2` placeholders; the query embedding is rendered as `f"[{','.join(f'{x:.6f}' for x in query_embedding)}]"` with a locale-independent float format -- no user-controlled string ever interpolates into the SQL. `tests/test_retriever.py::test_retrieve_uses_cosine_operator_and_limit` verifies the `LIMIT $2` placeholder shape. |
| T-03-04-02 (Tampering -- store UPSERT) | Mitigated | All values via asyncpg `$N` placeholders (1..9 across the UPSERT statement); `metadata` JSONB written via `json.dumps(c.metadata)` then cast `$9::jsonb`; vector via the same string-literal-cast-to-`::vector` pattern as the retriever. |
| T-03-04-03 (Information Disclosure -- retriever logs) | Mitigated | `structlog.info("retrieve_ok", top_k=..., returned=..., score_mean=...)` -- never logs the embedding vector itself or the full chunk content. The `score_mean` reduction is what pipeline span attributes consume. |
| T-03-04-04 (DoS -- retriever transaction) | Mitigated | `pool.acquire(timeout=1.0)` bounds connection-wait; HNSW with `SET LOCAL hnsw.ef_search = 40` keeps query <100ms p95 per RESEARCH.md latency budget for the 5K-50K chunk corpus. |
| T-03-04-05 (Tampering -- delete_stale empty-set bug) | Mitigated | Explicit early-return + structured `delete_stale_skipped` warning when `current_doc_ids` is empty. `tests/test_corpus_store.py::test_delete_stale_empty_set_does_not_delete` is the CI-enforced witness; asserts `pool.conn.executed == []` after the call. |
| T-03-04-06 (Repudiation -- upsert audit trail) | Mitigated | `chunks_upserted` log emits `count + embedding_model + embedding_model_version` on every batch; full audit trail in structlog JSON output. |

## Threat Flags

None -- no new threat surface introduced beyond the plan's `<threat_model>` register. The new attack surface (`<=>` cosine query + INSERT/DELETE on chunks) is bounded by the existing pool timeouts and the asyncpg parameterization; no new endpoints, auth paths, file access patterns, or schema changes.

## Self-Check: PASSED

- File `tracer_ai/rag/retriever.py` exists. Verified.
- File `tracer_ai/corpus/store.py` exists. Verified.
- File `tests/test_retriever.py` exists. Verified.
- File `tests/test_corpus_store.py` exists. Verified.
- Commit `2425a12` (Task 1) exists in `git log`. Verified.
- Commit `c1dbc69` (Task 2) exists in `git log`. Verified.
- `pytest tests/test_retriever.py tests/test_corpus_store.py -q` -> 17 passed.
- `mypy --strict tracer_ai/rag/retriever.py tracer_ai/corpus/store.py` -> Success: no issues found in 2 source files.
- `pytest tests/test_anti_patterns.py -q` -> 7 passed (no SDK-isolation regression).
- `python infra/scripts/import_cycle_guard.py` -> OK: tracer_ai module DAG check clean (4 layers).
- Acceptance grep counts:
  - `class PgvectorRetriever` (retriever.py) = 1.
  - `ef_search = 40` (retriever.py) = 3 (>= 1; module docstring + comment + actual SQL emit).
  - `embedding <=>` (retriever.py) = 3 (>= 2; SELECT projection + ORDER BY + module docstring reference).
  - `async def upsert_chunks|async def delete_stale|async def list_corpus` (store.py) = 3.
  - `ON CONFLICT (id) DO UPDATE` (store.py) = 1.
  - `embedding_model|embedding_model_version|indexed_at` (store.py) = 27 (>= 6; metadata triple referenced extensively).
  - real-import scan for `import voyageai|import anthropic` in `tracer_ai/rag/retriever.py` and `tracer_ai/corpus/store.py` = 0.

## User Setup Required

None -- no external service configuration required. All asyncpg pool calls are mocked in unit tests via the FakePool / recording-FakeConn pattern; the retriever and store run against the existing `chunks` table created by `alembic/versions/0001_initial.py` (Phase 2). The Docker compose smoke check (boot api + ingest seed corpus + run a retrieve) is a Phase-3-end manual gate, not a per-plan blocker.

## Next Phase Readiness

- **Phase 3 Plan 05 (prompt + LLM + pipeline):** unblocked. `pipeline.py` will instantiate `PgvectorRetriever(app.state.db_pool)` from lifespan; `pipeline.run_stream()` will call `retriever.retrieve(query_emb, top_k=5)` between the embed stage (Plan 03 `VoyageEmbedder`) and the prompt-assemble stage. The `RetrievedChunk` shape from Plan 01 is the contract -- pipeline code can assume score in `[0, 1]` (clamped here) and metadata as a real `dict[str, Any]` (decoded here).
- **Phase 3 Plan 06 (corpus ingest orchestrator + CLI):** unblocked. `tracer_ai/corpus/ingest.py` will compose `loader.discover()` -> `loader.load()` -> `chunker.split()` -> `embedder.embed_batch()` -> `upsert_chunks(...)` -> `delete_stale(current_doc_ids)`. The contracts here are exactly what that pipeline expects: same-length lists, full metadata triple, idempotent re-run.
- **Phase 3 Plan 07 (admin route + admin UI):** unblocked. `GET /admin/corpus` will call `list_corpus(request.app.state.db_pool)` and pass the nested dict directly to a Pydantic `CorpusState` response model (already pinned in Plan 03-01 `api/schemas.py`). Empty-corpus zero-coercion means the four KPI cards render on a fresh checkout.
- **Phase 4 (tracer Postgres writer):** orthogonal -- no retriever or store dependency.

---
*Phase: 03-rag-pipeline-chat-ui-corpus-admin*
*Completed: 2026-05-05*
