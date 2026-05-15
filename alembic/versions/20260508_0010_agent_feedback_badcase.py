"""Add badcase fields to agent feedback."""

from __future__ import annotations

from alembic import op

revision = "20260508_0010"
down_revision = "20260508_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE agent_feedback ADD COLUMN IF NOT EXISTS correction TEXT")
    op.execute(
        "ALTER TABLE agent_feedback "
        "ADD COLUMN IF NOT EXISTS badcase_flag BOOLEAN NOT NULL DEFAULT FALSE"
    )
    op.execute("ALTER TABLE agent_feedback ADD COLUMN IF NOT EXISTS original_report TEXT")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_feedback_badcase "
        "ON agent_feedback(badcase_flag, created_at)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_agent_feedback_badcase")
    op.execute("ALTER TABLE agent_feedback DROP COLUMN IF EXISTS original_report")
    op.execute("ALTER TABLE agent_feedback DROP COLUMN IF EXISTS badcase_flag")
    op.execute("ALTER TABLE agent_feedback DROP COLUMN IF EXISTS correction")
