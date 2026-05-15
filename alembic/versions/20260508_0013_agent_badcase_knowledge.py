"""Add badcase knowledge promotion fields."""

from __future__ import annotations

from alembic import op

revision = "20260508_0013"
down_revision = "20260508_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE agent_feedback
        ADD COLUMN IF NOT EXISTS knowledge_status TEXT NOT NULL DEFAULT 'not_promoted',
        ADD COLUMN IF NOT EXISTS knowledge_task_id TEXT NULL,
        ADD COLUMN IF NOT EXISTS knowledge_filename TEXT NULL,
        ADD COLUMN IF NOT EXISTS promoted_at TIMESTAMP WITH TIME ZONE NULL
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_feedback_knowledge_status "
        "ON agent_feedback (knowledge_status, promoted_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_agent_feedback_knowledge_status")
    op.execute(
        """
        ALTER TABLE agent_feedback
        DROP COLUMN IF EXISTS promoted_at,
        DROP COLUMN IF EXISTS knowledge_filename,
        DROP COLUMN IF EXISTS knowledge_task_id,
        DROP COLUMN IF EXISTS knowledge_status
        """
    )
