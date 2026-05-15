"""Add badcase review fields."""

from __future__ import annotations

from alembic import op

revision = "20260508_0012"
down_revision = "20260508_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE agent_feedback
        ADD COLUMN IF NOT EXISTS review_status TEXT NOT NULL DEFAULT 'pending',
        ADD COLUMN IF NOT EXISTS review_note TEXT NULL,
        ADD COLUMN IF NOT EXISTS reviewed_by TEXT NULL,
        ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMP WITH TIME ZONE NULL
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_feedback_badcase_review "
        "ON agent_feedback (badcase_flag, review_status, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_agent_feedback_badcase_review")
    op.execute(
        """
        ALTER TABLE agent_feedback
        DROP COLUMN IF EXISTS reviewed_at,
        DROP COLUMN IF EXISTS reviewed_by,
        DROP COLUMN IF EXISTS review_note,
        DROP COLUMN IF EXISTS review_status
        """
    )
