# ADR 006: Chunking Strategy — Markdown-Header-Aware (900 / 100)

## Status

Accepted — 2026-05-04

## Context

The tracer-ai corpus is the Anthropic Claude API + Claude Agent SDK documentation: markdown-formatted, organized as nested `##` and `###` sections, and dense with fenced code blocks (```` ``` ````) containing JSON request/response examples and Python/TypeScript SDK snippets. Naive splitters tear this content in two damaging ways: (1) they cut inside fenced code blocks, leaving the retriever returning syntactically-broken half-snippets that confuse the LLM; (2) they ignore the section headings that are the natural semantic boundaries of API documentation.

Chunk size and overlap interact with the retrieval `top_k` parameter — too-large chunks waste context window; too-many chunks invite the "lost in the middle" failure mode where mid-context content is ignored by the LLM (Pitfall #5).

This decision resolves [GSD-OPEN-6](../../tracer-ai-foundation-prd.md#10-open-questions-gsd-open-n) from the foundation PRD.

## Options Considered

- **Markdown-header-aware splitter at `##` / `###` boundaries with fenced-code protection (chosen):** Splits on header boundaries; never splits inside ```` ``` ```` fences; configurable `chunk_size` and `overlap`; admin-tunable at runtime via `PATCH /admin/chunking-config`.
- **Fixed-size chunks (e.g., RecursiveCharacterTextSplitter) (rejected):** Splits mid-code-block; ignores headers; loses semantic structure that is the whole point of API docs.
- **Sentence-window (rejected):** Better than fixed-size for prose, but markdown headers and code blocks are not sentences — semantic boundaries are still lost.
- **Per-document (rejected):** Way too coarse for the long Claude API doc pages; hurts retrieval precision because half a doc is irrelevant to most queries.

## Decision

tracer-ai will chunk Claude API docs at **`##` / `###` markdown header boundaries**, with hard protection against splitting inside fenced code blocks (` ``` ` and `~~~`). Default **`chunk_size = 900` tokens, `overlap = 100` tokens**. Both defaults are admin-tunable at runtime via `PATCH /admin/chunking-config`; the change re-applies on the next re-index. The splitter lives in `tracer_ai/corpus/chunker.py` behind a `Chunker` Protocol so future strategies (e.g., semantic-density chunking) can be swapped in without re-wiring the ingest CLI.

The retrieval `top_k` default is `5`. Operators are warned in `/docs/api.md` against `top_k > 8` because of the lost-in-the-middle failure mode (Pitfall #5).

## Consequences

**Positive:**
- Code-block integrity is preserved — the retriever returns syntactically-complete code snippets.
- Section semantics are respected — chunks correspond to "what the doc author intended as a unit".
- Admin can recalibrate chunk size/overlap without code changes; no redeploy needed for empirical tuning.
- `Chunker` Protocol leaves the door open for future strategies (semantic-density, hierarchical) without breaking the pipeline.

**Negative:**
- Chunk sizes will be uneven — short `###` sections produce sub-budget chunks; long ones may cross the budget. Acceptable trade-off for semantic integrity.
- Defaults of `900 / 100 / top_k=5` are educated guesses, not measured optima. They will be revisited during Phase 5 calibration.
- Lost-in-the-middle warning is documentation only — we do not enforce a max `top_k` in code (operator discretion is preserved).

**Mandatory follow-ups:**
- [ ] Re-evaluate `chunk_size`, `overlap`, and `top_k` defaults during Phase 5 calibration (EVAL-06).
- [ ] Document `top_k > 8` warning in `/docs/api.md` for the retrieval admin endpoint.
- [ ] Implement fenced-code protection by tokenizing the markdown stream before splitting, not after (Phase 1 — see corpus phase).

## References

- [.planning/research/PITFALLS.md §"Pitfall #5"](../../.planning/research/PITFALLS.md) — lost-in-the-middle and chunking pitfalls.
- [ADR 003: Embedding Provider](./003-embedding-provider.md) — chunks emit one embedding per chunk via `voyage-code-3`.
- [ADR 002: Vector Store](./002-vector-store.md) — chunks plus their embeddings live in pgvector.
