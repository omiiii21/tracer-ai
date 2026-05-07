"""add feedback.resolved_at column for FBCK-04 mark-resolved action (Phase 5 D-5.15).

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-08

Never edit 0001_initial.py / 0002_traces_denorm.py (D-2.17). This revision is
additive-only and reversible.

Additive: ALTER TABLE feedback ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ NULL.
Existing feedback rows survive the upgrade with resolved_at IS NULL — interpreted
as "not resolved" by the bad-answer-queue exclusion filter (FBCK-03 / FBCK-04).

Reversible: downgrade -1 drops the partial index AND the column. Operator-set
resolved_at values are LOST on downgrade by definition (T-05-02-06 — accepted;
operators must back up resolved_at before invoking downgrade).

Partial index: ``feedback_unresolved_idx ON feedback (trace_id) WHERE resolved_at
IS NULL`` accelerates the bad-answer-queue exclusion filter (the hot-path
predicate is ``WHERE resolved_at IS NULL``). It also supports the FBCK-07 KPI
``COUNT(*) WHERE resolved_at >= now() - interval '7 days'`` because the inverse
predicate is rare and Postgres can scan the table directly for that count.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text("ALTER TABLE feedback ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ NULL;")
    )
    # Partial index for the bad-answer-queue exclusion filter (FBCK-03):
    # WHERE resolved_at IS NULL is the hot-path predicate.
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS feedback_unresolved_idx "
            "ON feedback (trace_id) WHERE resolved_at IS NULL;"
        )
    )
    # Phase 5 FBCK-07 widget needs `WHERE resolved_at >= now() - interval '7 days'`
    # — index supports the count query as well as the queue exclusion.


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS feedback_unresolved_idx;"))
    op.execute(sa.text("ALTER TABLE feedback DROP COLUMN IF EXISTS resolved_at;"))
