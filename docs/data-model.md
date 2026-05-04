# Data Model

A single Postgres 16 instance hosts both the trace database (5 tables) and the `pgvector` extension's chunk collection. JSONB columns store heterogeneous span attributes; GIN indexes enable fast querying by attribute key (`WHERE attrs->>'gen_ai.operation.name' = 'retrieval'`). Full prompt/response payloads live in a `span_payloads` JSONB side table referenced by `span_id` — NOT on the span row (per [ADR 004](./decisions/004-trace-storage.md) and [Trace Schema § Payload Storage Convention](./trace-schema.md)).

## Entity-Relationship Diagram

```mermaid
erDiagram
  traces ||--o{ spans : "has many"
  traces ||--o{ feedback : "may have many"
  spans ||--o| span_payloads : "may have one"
  regression_cases }o--|| traces : "promoted from"

  traces {
    uuid id PK
    timestamptz started_at
    timestamptz ended_at
    text query_text
    uuid root_span_id
  }
  spans {
    uuid id PK
    uuid trace_id FK
    uuid parent_span_id "nullable; null on root span"
    text name "rag.request | rag.retrieve | ..."
    timestamptz started_at
    timestamptz ended_at
    jsonb attrs
  }
  span_payloads {
    uuid span_id PK_FK
    jsonb payload "full prompt/response/chunks"
  }
  feedback {
    uuid id PK
    uuid trace_id FK
    smallint rating "1=up, -1=down"
    text comment "nullable"
    text diagnosis_tag "nullable; FBCK-05 future"
    timestamptz created_at
  }
  regression_cases {
    uuid id PK
    uuid source_trace_id FK
    text expected_doc_section
    jsonb expected_chunk_keywords
    timestamptz promoted_at
  }
```

## Postgres DDL

```sql
-- traces: one row per chat request
CREATE TABLE traces (
    id UUID PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    query_text TEXT NOT NULL,
    root_span_id UUID NOT NULL
);
CREATE INDEX traces_started_at_idx ON traces (started_at DESC);

-- spans: one row per span; PARTITIONED BY started_at month (D-51 / Pitfall #2)
CREATE TABLE spans (
    id UUID NOT NULL,
    trace_id UUID NOT NULL REFERENCES traces(id) ON DELETE CASCADE,
    parent_span_id UUID,
    name TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    attrs JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (id, started_at)
) PARTITION BY RANGE (started_at);

-- Initial monthly partitions (Alembic migration creates these and rolling future partitions)
CREATE TABLE spans_y2026m05 PARTITION OF spans
    FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');
CREATE INDEX spans_y2026m05_attrs_gin ON spans_y2026m05 USING gin (attrs);
CREATE INDEX spans_y2026m05_trace_id_idx ON spans_y2026m05 (trace_id);
-- Subsequent month partitions follow the same pattern; created via Alembic in Phase 2.

-- span_payloads: side table for full prompt/response text (D-47)
CREATE TABLE span_payloads (
    span_id UUID PRIMARY KEY,
    payload JSONB NOT NULL
    -- intentionally no FK to spans because spans is partitioned;
    -- FK enforcement is application-layer in tracer/exporters/postgres.py
);

-- feedback: thumbs-up/down + optional comment + future diagnosis_tag (FBCK-05)
CREATE TABLE feedback (
    id UUID PRIMARY KEY,
    trace_id UUID NOT NULL REFERENCES traces(id) ON DELETE CASCADE,
    rating SMALLINT NOT NULL CHECK (rating IN (-1, 1)),
    comment TEXT,
    diagnosis_tag TEXT,  -- Phase 5 FBCK-05 surfaces UI; column exists from day one
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX feedback_trace_id_idx ON feedback (trace_id);

-- regression_cases: traces promoted into the regression set (Phase 6 CLI-05)
CREATE TABLE regression_cases (
    id UUID PRIMARY KEY,
    source_trace_id UUID NOT NULL REFERENCES traces(id),
    expected_doc_section TEXT NOT NULL,
    expected_chunk_keywords JSONB NOT NULL,
    promoted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

All schema changes managed via Alembic in Phase 2 INFRA-01.

## pgvector Chunks Collection Schema

```sql
-- Enable pgvector extension once per database
CREATE EXTENSION IF NOT EXISTS vector;

-- Chunks table: 1024-dim Voyage voyage-code-3 embeddings
-- Embedding metadata mandate from ADR 003 / D-49 / Pitfall #3
CREATE TABLE chunks (
    id UUID PRIMARY KEY,
    doc_id TEXT NOT NULL,
    doc_section TEXT NOT NULL,  -- canonical taxonomy from /docs/eval/coverage_set.yaml
    content TEXT NOT NULL,
    embedding VECTOR(1024) NOT NULL,
    embedding_model TEXT NOT NULL,         -- e.g., 'voyage-code-3'
    embedding_model_version TEXT NOT NULL, -- pinned snapshot
    indexed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- HNSW index for fast approximate nearest-neighbor search
CREATE INDEX chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX chunks_doc_section_idx ON chunks (doc_section);
```

Startup assertion (Phase 3 CORP-04) verifies `config.embedding_model == chunks.embedding_model` before serving requests — prevents silent garbage-retrieval (Pitfall #3 / ADR 003).

## Migration Strategy

Schema is managed via Alembic in Phase 2 INFRA-01. The initial migration creates all 5 trace tables + the chunks table + 3 months of forward-rolling spans partitions. Per [ADR 004](./decisions/004-trace-storage.md), the spans table partition by `started_at` month is created in the initial migration to avoid expensive retrofitting later. A monthly cron / one-shot script creates the next month's partition before its data arrives — runtime detail is Phase 2 INFRA-02 scope, not Phase 1.

## Cross-References

- [Architecture](./architecture.md)
- [Trace Schema](./trace-schema.md)
- [ADR 002 — Vector Store](./decisions/002-vector-store.md)
- [ADR 003 — Embedding Provider](./decisions/003-embedding-provider.md)
- [ADR 004 — Trace Storage](./decisions/004-trace-storage.md)
