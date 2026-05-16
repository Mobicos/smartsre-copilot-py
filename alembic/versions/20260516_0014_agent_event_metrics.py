"""Add Agent event metric columns."""

from __future__ import annotations

from alembic import op

revision = "20260516_0014"
down_revision = "20260508_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE agent_events
        ADD COLUMN IF NOT EXISTS step_index INTEGER NULL,
        ADD COLUMN IF NOT EXISTS evidence_quality TEXT NULL,
        ADD COLUMN IF NOT EXISTS recovery_action TEXT NULL,
        ADD COLUMN IF NOT EXISTS token_usage JSONB NULL,
        ADD COLUMN IF NOT EXISTS cost_estimate JSONB NULL
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_events_run_step "
        "ON agent_events (run_id, step_index, id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_agent_events_run_step")
    op.execute(
        """
        ALTER TABLE agent_events
        DROP COLUMN IF EXISTS cost_estimate,
        DROP COLUMN IF EXISTS token_usage,
        DROP COLUMN IF EXISTS recovery_action,
        DROP COLUMN IF EXISTS evidence_quality,
        DROP COLUMN IF EXISTS step_index
        """
    )
