"""Add release gate metric columns to agent_runs."""

from __future__ import annotations

from alembic import op

revision = "20260517_0016"
down_revision = "20260516_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS recovery_count INTEGER DEFAULT 0")
    op.execute(
        "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS empty_result_count INTEGER DEFAULT 0"
    )
    op.execute(
        "ALTER TABLE agent_runs "
        "ADD COLUMN IF NOT EXISTS duplicate_tool_call_count INTEGER DEFAULT 0"
    )
    op.execute("ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS step_latencies JSONB NULL")
    op.execute(
        "ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS regression_score DOUBLE PRECISION NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_runs_latency_ms ON agent_runs(latency_ms)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_agent_runs_latency_ms")
    op.execute("ALTER TABLE agent_runs DROP COLUMN IF EXISTS regression_score")
    op.execute("ALTER TABLE agent_runs DROP COLUMN IF EXISTS step_latencies")
    op.execute("ALTER TABLE agent_runs DROP COLUMN IF EXISTS duplicate_tool_call_count")
    op.execute("ALTER TABLE agent_runs DROP COLUMN IF EXISTS empty_result_count")
    op.execute("ALTER TABLE agent_runs DROP COLUMN IF EXISTS recovery_count")
