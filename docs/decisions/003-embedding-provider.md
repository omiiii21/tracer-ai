# ADR 003: Embedding Provider — Voyage AI voyage-code-3 (with sentence-transformers fallback)

## Status

Accepted — 2026-05-04

## Context

tracer-ai's corpus is the Anthropic Claude API + Claude Agent SDK documentation — a heavily code- and technical-prose hybrid. The embedder must capture both natural-language semantics ("how do I authenticate to the Messages API") and code-symbol semantics (`x-api-key`, `client.messages.create(...)`, JSON schema fragments) so retrieval surfaces the right doc section, not just text-similar prose. Pricing must allow embedding ~50K chunks within the portfolio budget; an offline fallback is required for development and as a pricing escape hatch.

A critical pitfall (Pitfall #2 in research) is **silent garbage retrieval when the query embedder and the corpus embedder differ**. Vector scores remain "normal-looking" but the semantic match is meaningless. The mitigation is metadata + a startup assertion — both mandated below.

This decision resolves [GSD-OPEN-3](../../tracer-ai-foundation-prd.md#10-open-questions-gsd-open-n) from the foundation PRD.

## Options Considered

- **Voyage AI `voyage-code-3` (chosen, primary):** 1024-dim. Anthropic-recommended embedding partner. Specifically tuned for code-and-technical-doc corpora; published evaluations show meaningful gains over generic text embedders on code-laden retrieval.
- **`sentence-transformers` `nomic-embed-text-v1.5` (chosen, offline/fallback):** 768-dim, fully local, no API key. Production-quality general-purpose embedder. Used for offline dev and as a budget escape hatch; offered behind the same `Embedder` Protocol.
- **OpenAI `text-embedding-3-large` (rejected):** 3072-dim. Generic English embedder, not code-tuned. Dimension is 3x our target — bloats `pgvector` index size and HNSW build time without retrieval-quality gain on this corpus.
- **Cohere `embed-english-v3.0` (rejected):** Strong general embedder, but no code-doc specialization edge over Voyage on this exact corpus type.

## Decision

tracer-ai will use **Voyage AI `voyage-code-3`** (1024-dim) as the primary embedder and **`sentence-transformers` `nomic-embed-text-v1.5`** (768-dim) as the offline fallback, both implemented behind a single `Embedder` Protocol in `tracer_ai/rag/embedder.py`. The `chunks` table records `embedding_model`, `embedding_model_version`, and `indexed_at` columns on every row. On application startup, FastAPI's lifespan handler runs an **assertion that `config.embedding_model == corpus.embedding_model`** (queried from the `chunks` table); a mismatch raises `EmbeddingModelMismatchError` and refuses to start. This converts a silent retrieval-garbage failure mode into a fast, loud startup failure.

## Consequences

**Positive:**
- Code-and-technical-prose retrieval quality is measurably better than generic embedders for our corpus.
- Offline-dev escape hatch: developers without a `VOYAGE_API_KEY` can run the full stack against `nomic-embed-text-v1.5`.
- Metadata + startup assertion converts the most insidious silent-failure mode (mismatched embedders) into a loud startup error — diagnoseable in seconds vs hours of "weird retrieval".
- Same `Embedder` Protocol abstracts both — pipeline code does not branch on provider.

**Negative:**
- `VOYAGE_API_KEY` is required for the primary path. CI/CD environments must inject it or fall back.
- Voyage pricing is **not yet verified.** Captured as a Phase 2 prereq, not a Phase 1 blocker.
- The two embedders have different dimensions (1024 vs 768), so switching providers requires a full re-index — but the metadata mandate ensures we will know when to do it.

**Mandatory follow-ups:**
- [x] Verified Voyage AI pricing 2026-05-04: `voyage-code-3` covered by 200M-token free tier per account (cumulative, not monthly-resetting); paid rate $0.18/1M tokens if exceeded. Phase 3 corpus ingestion (~25M tokens for ~50K chunks × ~500 tokens/chunk) is well under the free tier; no paid spend required to close INFRA-01. Source: https://docs.voyageai.com/docs/pricing checked via RESEARCH.md Topic 8 WebFetch on 2026-05-04. Per `--auto` chain (`/gsd-discuss-phase 2 --auto` → `/gsd-plan-phase 2 --auto` → `/gsd-execute-phase 2 --auto`), operator pre-authorized the free-tier path.
- [ ] Add startup assertion `config.embedding_model == corpus.embedding_model` in `tracer_ai/api/app.py` lifespan handler (Pitfall #3 mitigation).
- [ ] `chunks` table migration records `embedding_model TEXT NOT NULL`, `embedding_model_version TEXT NOT NULL`, `indexed_at TIMESTAMPTZ NOT NULL` (per D-49).
- [ ] Both adapters implement the same `Embedder` Protocol so pipeline code is provider-agnostic.

## References

- [.planning/research/STACK.md §"GSD-OPEN-3"](../../.planning/research/STACK.md)
- [.planning/research/PITFALLS.md §"Pitfall #3"](../../.planning/research/PITFALLS.md) — silent garbage retrieval on embedder mismatch.
- [.planning/research/SUMMARY.md §"Gaps to Address"](../../.planning/research/SUMMARY.md) — Voyage pricing verification flag.
- [ADR 002: Vector Store](./002-vector-store.md) — defines the `VECTOR(1024)` column matching Voyage's dimension.
