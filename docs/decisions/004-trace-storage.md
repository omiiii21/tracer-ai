# ADR 004: Trace Storage — Postgres 16 + JSONB

## Status

Accepted — 2026-05-04

## Context

Every stage of tracer-ai's RAG pipeline emits a span. Span attributes are heterogeneous: an LLM span carries `gen_ai.usage.input_tokens` / `gen_ai.usage.output_tokens`; a retrieval span carries `rag.retrieval.score.mean` and `rag.retrieval.k`; an eval span carries `rag.eval.faithfulness`. A rigid relational schema would force either nullable columns for every possible attribute or a complex inheritance scheme — both painful to evolve as the OTel GenAI spec (still at Development stability — see [ADR 005](./005-observability-strategy.md)) changes.

We also need fast time-series aggregations (`AVG(faithfulness)` rolled up by hour, `p95(latency)` over 24h) for the dashboard. Full prompt and response payloads can exceed the OTel span-attribute size limit (4–16 KB) — these must live separately from the span row to keep span queries cheap.

This decision resolves [GSD-OPEN-4](../../tracer-ai-foundation-prd.md#10-open-questions-gsd-open-n) from the foundation PRD.

## Options Considered

- **Postgres 16 + JSONB GIN-indexed (chosen):** Same instance as `pgvector` (per [ADR 002](./002-vector-store.md)). JSONB GIN indexes support `WHERE attrs->>'gen_ai.operation.name' = 'retrieval'`. Time-series aggregations are native SQL with `DATE_TRUNC`. asyncpg gives high-throughput async writes.
- **SQLite (rejected):** Fine for single-writer scenarios, but write-lock contention under async concurrent writes from the tracer queue is a known failure mode. JSON support exists but no GIN-equivalent index for attribute-key filters.
- **ClickHouse (rejected for v1):** Best-in-class for trace-style time-series — but adds a third Docker service and a second persistence story. Future migration target if traces grow to 100M+ rows.
- **DuckDB (rejected):** Excellent for analytical reads but write concurrency is unsuitable for a real-time trace ingestion path.

## Decision

tracer-ai will store traces and spans in **Postgres 16**, on the same instance as `pgvector`. Schema:

- `traces` — one row per request. Columns: `trace_id` (PK), `started_at`, `ended_at`, `request_id`, `user_session`.
- `spans` — one row per span. Columns: `span_id` (PK), `trace_id` (FK → traces), `parent_span_id`, `name`, `started_at`, `ended_at`, `attrs JSONB` GIN-indexed.
- `span_payloads` — JSONB side table for full prompt/response/retrieved-chunk content, referenced by `span_id` (FK). Payloads are NOT inlined onto the span row, because OTel limits span attributes to 4–16 KB and we routinely exceed that.

The **`spans` table is partitioned by `RANGE (started_at)` on month boundaries** in the initial Alembic migration. Partitioning at write time costs little; retrofitting partitioning to a populated table is expensive — so we do it from day one.

## Consequences

**Positive:**
- Single Postgres instance (with `pgvector`) supports both vector retrieval and trace storage.
- JSONB GIN indexes keep attribute-filter queries fast as the schema evolves.
- Native SQL time-series aggregations (`DATE_TRUNC`, `AVG`, `percentile_cont`) drive the dashboard directly.
- Monthly partitioning lets us drop old partitions cheaply during demo runs and bounds index sizes.

**Negative:**
- Initial Alembic migration is non-trivial (partitioned table + GIN index + side table). Encapsulated in one migration script — pain pays for itself the first time we need to drop a month of traces.
- Splitting `spans` from `span_payloads` adds a join when the trace-detail UI fetches full payloads — acceptable, payload reads are infrequent vs. span list reads.
- Future migration to ClickHouse would require translating JSONB queries — manageable; documented as a future option.

**Mandatory follow-ups:**
- [ ] Initial Alembic migration creates the `spans` table with `PARTITION BY RANGE (started_at)` and pre-creates the current + next two monthly partitions (per D-51).
- [ ] `span_payloads` JSONB side table holds full prompt / response / retrieved-chunk content (Pitfall #2 / Pitfall #6 mitigation, per D-47).
- [ ] GIN index on `spans.attrs` to support `attrs->>'gen_ai.operation.name'` filters.
- [ ] Add a partition-rotation cron-equivalent (Phase 2 — out of scope for v1 but documented in `/docs/data-model.md`).

## References

- [.planning/research/STACK.md §"GSD-OPEN-4"](../../.planning/research/STACK.md)
- [.planning/research/PITFALLS.md §"Pitfall #2"](../../.planning/research/PITFALLS.md) — span attribute size limits.
- [.planning/research/PITFALLS.md §"Pitfall #6"](../../.planning/research/PITFALLS.md) — payload-table separation rationale.
- [ADR 002: Vector Store](./002-vector-store.md) — co-tenant of this Postgres instance.
- [ADR 005: Observability Strategy](./005-observability-strategy.md) — defines the span attribute names that populate `attrs JSONB`.
