"""add latency_ms, faithfulness, feedback_rating, estimated_cost_usd to traces.

Also adds 2026-08 spans partition (Phase 4 D-4.02 + RESEARCH §Open Questions #1 + Pitfall 4).

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-06

Never edit 0001_initial.py (D-2.17). This revision is additive-only and reversible.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # D-4.02: three denormalized scalar columns on traces
    op.execute(sa.text("ALTER TABLE traces ADD COLUMN IF NOT EXISTS latency_ms INT NULL;"))
    op.execute(sa.text("ALTER TABLE traces ADD COLUMN IF NOT EXISTS faithfulness REAL NULL;"))
    op.execute(
        sa.text("ALTER TABLE traces ADD COLUMN IF NOT EXISTS feedback_rating SMALLINT NULL;")
    )
    # RESEARCH §Open Questions #1: docs/api.md TraceListItem requires estimated_cost_usd
    op.execute(sa.text("ALTER TABLE traces ADD COLUMN IF NOT EXISTS estimated_cost_usd REAL NULL;"))
    # Add CHECK constraint on feedback_rating mirroring docs/api.md FeedbackRequest.rating
    op.execute(
        sa.text(
            "ALTER TABLE traces ADD CONSTRAINT traces_feedback_rating_chk "
            "CHECK (feedback_rating IS NULL OR feedback_rating IN (-1, 1));"
        )
    )
    # Indexes on EXPL-01 filter columns (D-4.20)
    op.execute(
        sa.text("CREATE INDEX IF NOT EXISTS traces_faithfulness_idx ON traces (faithfulness);")
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS traces_feedback_rating_idx ON traces (feedback_rating);"
        )
    )
    # Pitfall 4: extend spans partitions to 2026-08 (0001_initial.py covered 2026-05/06/07)
    op.execute(
        sa.text(
            "CREATE TABLE IF NOT EXISTS spans_y2026m08 PARTITION OF spans "
            "FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');"
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS spans_y2026m08_attrs_gin "
            "ON spans_y2026m08 USING gin (attrs);"
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS spans_y2026m08_trace_id_idx "
            "ON spans_y2026m08 (trace_id);"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS spans_y2026m08_trace_id_idx;"))
    op.execute(sa.text("DROP INDEX IF EXISTS spans_y2026m08_attrs_gin;"))
    op.execute(sa.text("DROP TABLE IF EXISTS spans_y2026m08;"))
    op.execute(sa.text("DROP INDEX IF EXISTS traces_feedback_rating_idx;"))
    op.execute(sa.text("DROP INDEX IF EXISTS traces_faithfulness_idx;"))
    op.execute(sa.text("ALTER TABLE traces DROP CONSTRAINT IF EXISTS traces_feedback_rating_chk;"))
    op.execute(sa.text("ALTER TABLE traces DROP COLUMN IF EXISTS estimated_cost_usd;"))
    op.execute(sa.text("ALTER TABLE traces DROP COLUMN IF EXISTS feedback_rating;"))
    op.execute(sa.text("ALTER TABLE traces DROP COLUMN IF EXISTS faithfulness;"))
    op.execute(sa.text("ALTER TABLE traces DROP COLUMN IF EXISTS latency_ms;"))
