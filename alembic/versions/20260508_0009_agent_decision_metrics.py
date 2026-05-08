"""Add decision runtime metrics to native agent runs."""

from __future__ import annotations

from alembic import op


revision = "20260508_0009"
down_revision = "20260507_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS decision_provider TEXT")
    op.execute("ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS cost_estimate JSONB")
    op.execute("ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS handoff_reason TEXT")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_runs_handoff_reason "
        "ON agent_runs(handoff_reason)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_agent_runs_handoff_reason")
    op.execute("ALTER TABLE agent_runs DROP COLUMN IF EXISTS handoff_reason")
    op.execute("ALTER TABLE agent_runs DROP COLUMN IF EXISTS cost_estimate")
    op.execute("ALTER TABLE agent_runs DROP COLUMN IF EXISTS decision_provider")
