"""initial schema: traces + spans (partitioned) + span_payloads + feedback + regression_cases + chunks (pgvector) + 3 monthly partitions

Revision ID: 0001
Revises:
Create Date: 2026-05-04

Per D-2.17 + docs/data-model.md (locked Phase 1): hand-curated initial migration.
Future revisions add to this; never edit 0001_initial.py.

Per Pitfall 2 / D-2.09: this migration assumes the ``vector`` extension already
exists (created by infra/db/init.sql as the postgres superuser). The application
user ``tracer`` lacks SUPERUSER and CANNOT install Postgres extensions.

Per RESEARCH.md Topic 2: PARTITION BY RANGE DDL uses op.execute(sa.text(...))
because the Alembic op.* API does not directly support partitioning.

Per fix W-5: the chunks table is also created via raw SQL so the on-disk column
is ``metadata`` from the start -- no rename two-step, no spurious autogenerate
diffs. Phase 3+ ORM models will use ``mapped_column(name="metadata", key="metadata_")``
to bridge the SQLAlchemy DeclarativeBase reserved-attribute clash.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the full Phase 2 schema verbatim from docs/data-model.md."""

    # 1. traces -- one row per chat request (data-model.md lines 54-62)
    op.execute(
        sa.text("""
        CREATE TABLE traces (
            id UUID PRIMARY KEY,
            started_at TIMESTAMPTZ NOT NULL,
            ended_at TIMESTAMPTZ,
            query_text TEXT NOT NULL,
            root_span_id UUID NOT NULL
        );
    """)
    )
    op.execute(sa.text("CREATE INDEX traces_started_at_idx ON traces (started_at DESC);"))

    # 2. spans -- PARTITIONED BY RANGE(started_at) monthly (data-model.md lines 64-74)
    #    Composite PK (id, started_at) is a Postgres correctness requirement --
    #    the partition key must be in the PK (STATE.md Phase 1 decision).
    op.execute(
        sa.text("""
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
    """)
    )

    # 3. Three forward-rolling monthly partitions per D-2.17
    #    Naming: spans_y{YYYY}m{MM} per STATE.md locked convention
    #    Loop is unrolled so each partition name appears as a literal in source
    #    (greppable for the acceptance gates and code review).
    op.execute(
        sa.text("""
        CREATE TABLE spans_y2026m05 PARTITION OF spans
            FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');
    """)
    )
    op.execute(
        sa.text("CREATE INDEX spans_y2026m05_attrs_gin ON spans_y2026m05 USING gin (attrs);")
    )
    op.execute(sa.text("CREATE INDEX spans_y2026m05_trace_id_idx ON spans_y2026m05 (trace_id);"))

    op.execute(
        sa.text("""
        CREATE TABLE spans_y2026m06 PARTITION OF spans
            FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');
    """)
    )
    op.execute(
        sa.text("CREATE INDEX spans_y2026m06_attrs_gin ON spans_y2026m06 USING gin (attrs);")
    )
    op.execute(sa.text("CREATE INDEX spans_y2026m06_trace_id_idx ON spans_y2026m06 (trace_id);"))

    op.execute(
        sa.text("""
        CREATE TABLE spans_y2026m07 PARTITION OF spans
            FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');
    """)
    )
    op.execute(
        sa.text("CREATE INDEX spans_y2026m07_attrs_gin ON spans_y2026m07 USING gin (attrs);")
    )
    op.execute(sa.text("CREATE INDEX spans_y2026m07_trace_id_idx ON spans_y2026m07 (trace_id);"))

    # 4. span_payloads -- side table; intentionally NO FK to spans because
    #    partitioned-parent FK enforcement is expensive in Postgres (STATE.md decision).
    op.execute(
        sa.text("""
        CREATE TABLE span_payloads (
            span_id UUID PRIMARY KEY,
            payload JSONB NOT NULL
        );
    """)
    )

    # 5. feedback -- rating CHECK (-1, 1) is the DB-layer integrity constraint
    #    matched by Pydantic Literal[-1, 1] in api.md (cross-layer pattern).
    op.execute(
        sa.text("""
        CREATE TABLE feedback (
            id UUID PRIMARY KEY,
            trace_id UUID NOT NULL REFERENCES traces(id) ON DELETE CASCADE,
            rating SMALLINT NOT NULL CHECK (rating IN (-1, 1)),
            comment TEXT,
            diagnosis_tag TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    )
    op.execute(sa.text("CREATE INDEX feedback_trace_id_idx ON feedback (trace_id);"))

    # 6. regression_cases -- promoted from traces; source_trace_id has NO ON DELETE
    #    so regression cases outlive the source trace (Phase 6 CLI-05 contract).
    op.execute(
        sa.text("""
        CREATE TABLE regression_cases (
            id UUID PRIMARY KEY,
            source_trace_id UUID NOT NULL REFERENCES traces(id),
            expected_doc_section TEXT NOT NULL,
            expected_chunk_keywords JSONB NOT NULL,
            promoted_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    )

    # 7. chunks -- pgvector; vector extension created by init.sql NOT here (Pitfall 2).
    #    Embedding-metadata triple-column pattern (model + version + indexed_at) is the
    #    silent-garbage-retrieval mitigation (Pitfall #3 / D-49 / ADR 003 / STATE.md).
    #    The embedding column is the SQL equivalent of pgvector.sqlalchemy Vector(1024)
    #    -- 1024 dimensions matches Voyage voyage-code-3 output (ADR 003).
    op.execute(
        sa.text("""
        CREATE TABLE chunks (
            id UUID PRIMARY KEY,
            doc_id TEXT NOT NULL,
            doc_section TEXT NOT NULL,
            content TEXT NOT NULL,
            embedding VECTOR(1024) NOT NULL,
            embedding_model TEXT NOT NULL,
            embedding_model_version TEXT NOT NULL,
            indexed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb
        )
    """)
    )

    # HNSW index for fast approximate cosine NN search
    op.execute(
        sa.text(
            "CREATE INDEX chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops);"
        )
    )
    op.execute(sa.text("CREATE INDEX chunks_doc_section_idx ON chunks (doc_section);"))


def downgrade() -> None:
    """Drop everything in reverse dependency order."""
    # chunks first (no dependents)
    op.execute(sa.text("DROP TABLE IF EXISTS chunks CASCADE;"))
    op.execute(sa.text("DROP TABLE IF EXISTS regression_cases CASCADE;"))
    op.execute(sa.text("DROP TABLE IF EXISTS feedback CASCADE;"))
    op.execute(sa.text("DROP TABLE IF EXISTS span_payloads CASCADE;"))
    # spans partitions before parent
    op.execute(sa.text("DROP TABLE IF EXISTS spans_y2026m05 CASCADE;"))
    op.execute(sa.text("DROP TABLE IF EXISTS spans_y2026m06 CASCADE;"))
    op.execute(sa.text("DROP TABLE IF EXISTS spans_y2026m07 CASCADE;"))
    op.execute(sa.text("DROP TABLE IF EXISTS spans CASCADE;"))
    op.execute(sa.text("DROP TABLE IF EXISTS traces CASCADE;"))
