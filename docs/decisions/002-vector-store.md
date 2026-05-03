# ADR 002: Vector Store — pgvector on Same Postgres 16 Instance

## Status

Accepted — 2026-05-04

## Context

tracer-ai's RAG pipeline needs vector retrieval over ~50K chunks of Anthropic Claude API + Agent SDK documentation. The deployment target is a single-user, local Docker Compose stack — operational simplicity beats horizontal scalability for v1. We also need metadata filtering (by `doc_id`, `chunk_type`, `embedding_model`) and approximate-nearest-neighbor speed without brute-force scanning. Because [ADR 004](./004-trace-storage.md) already places traces in Postgres 16 with JSONB, consolidating the vector store into the same Postgres instance reduces the Compose stack to one persistent service.

This decision resolves [GSD-OPEN-2](../../tracer-ai-foundation-prd.md#10-open-questions-gsd-open-n) from the foundation PRD.

## Options Considered

- **pgvector on Postgres 16 (chosen):** Same Postgres instance as the trace store. `pgvector-python` integrates with SQLAlchemy 2.0 via `VECTOR(dim)` column type and `.cosine_distance()` query method. HNSW index supports approximate nearest neighbor; metadata filters are native SQL `WHERE` clauses.
- **Qdrant as a separate Docker service (rejected for v1):** Excellent vector store with rich filter API, but requires a second Docker service, a second client library (`qdrant-client[async]`), and a second persistence volume. Wins materialize only above ~500K chunks or when hybrid sparse+dense retrieval is required — neither applies in v1.
- **Chroma (rejected):** Embedded mode is unstable on volume-backed Compose deployments; minor-version API surface has churned. No advantage over pgvector for our scale.
- **Weaviate (rejected):** JVM-based, GraphQL API, multi-service operational footprint. Far too heavy for a single-user local stack.

## Decision

tracer-ai will use the **`pgvector` extension** on the same Postgres 16 instance that hosts the trace database. Chunks live in a `chunks` table with a `VECTOR(1024)` column sized to the Voyage `voyage-code-3` embedding dimension (per [ADR 003](./003-embedding-provider.md)). The vector index is created with `CREATE INDEX ... USING hnsw (embedding vector_cosine_ops)` for fast approximate nearest neighbor search. Metadata filters (e.g., `WHERE chunk_type = 'code'`) are native SQL — no special filter API. The `pgvector` extension is provisioned via the official `ankane/pgvector` Docker image referenced from `infra/docker-compose.yml`.

## Consequences

**Positive:**
- Single Postgres Docker service supports both vector retrieval and trace storage. One volume, one backup, one Alembic migration history.
- No second client library — the existing `asyncpg` + `sqlalchemy[asyncio]` setup covers vector queries.
- Metadata filters are plain SQL — no learning curve, no special filter DSL.
- HNSW index gives sub-100ms retrieval at 50K chunks on a laptop.

**Negative:**
- pgvector's HNSW implementation is good but not best-in-class at very large scale (>500K vectors). Documented switch trigger below.
- Vector and trace traffic share IO on one Postgres instance. Acceptable at v1 traffic levels; would be split if write contention emerges.

**Mandatory follow-ups:**
- [ ] Provision `pgvector` extension via `CREATE EXTENSION IF NOT EXISTS vector;` in initial Alembic migration (Phase 0 INFRA-03).
- [ ] Document switch trigger in `/docs/architecture.md`: migrate to Qdrant when corpus exceeds ~500K chunks **or** when hybrid sparse+dense search is needed.
- [ ] Keep the `Retriever` Protocol in `tracer_ai/rag/retriever.py` swap-friendly so a future `QdrantRetriever` adapter does not require pipeline rewrites.

## References

- [.planning/research/STACK.md §"GSD-OPEN-2"](../../.planning/research/STACK.md)
- [.planning/research/SUMMARY.md §"Recommended Stack"](../../.planning/research/SUMMARY.md)
- [ADR 003: Embedding Provider](./003-embedding-provider.md) — fixes the 1024-dim vector size used by this store.
- [ADR 004: Trace Storage](./004-trace-storage.md) — sibling Postgres tenant on the same instance.
