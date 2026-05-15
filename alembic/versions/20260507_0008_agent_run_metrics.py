"""Persist Native Agent run metrics.

Revision ID: 20260507_0008
Revises: 20260507_0007
Create Date: 2026-05-07 00:00:00
"""

from __future__ import annotations

from alembic import op

revision = "20260507_0008"
down_revision = "20260507_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS runtime_version TEXT")
    op.execute("ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS trace_id TEXT")
    op.execute("ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS model_name TEXT")
    op.execute("ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS step_count INTEGER")
    op.execute("ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS tool_call_count INTEGER")
    op.execute("ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS latency_ms INTEGER")
    op.execute("ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS error_type TEXT")
    op.execute("ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS approval_state TEXT")
    op.execute("ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS retrieval_count INTEGER")
    op.execute("ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS token_usage JSONB")
    op.execute("CREATE INDEX IF NOT EXISTS idx_agent_runs_trace_id ON agent_runs(trace_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_runs_approval_state ON agent_runs(approval_state)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_agent_runs_approval_state")
    op.execute("DROP INDEX IF EXISTS idx_agent_runs_trace_id")
    op.execute("ALTER TABLE agent_runs DROP COLUMN IF EXISTS token_usage")
    op.execute("ALTER TABLE agent_runs DROP COLUMN IF EXISTS retrieval_count")
    op.execute("ALTER TABLE agent_runs DROP COLUMN IF EXISTS approval_state")
    op.execute("ALTER TABLE agent_runs DROP COLUMN IF EXISTS error_type")
    op.execute("ALTER TABLE agent_runs DROP COLUMN IF EXISTS latency_ms")
    op.execute("ALTER TABLE agent_runs DROP COLUMN IF EXISTS tool_call_count")
    op.execute("ALTER TABLE agent_runs DROP COLUMN IF EXISTS step_count")
    op.execute("ALTER TABLE agent_runs DROP COLUMN IF EXISTS model_name")
    op.execute("ALTER TABLE agent_runs DROP COLUMN IF EXISTS trace_id")
    op.execute("ALTER TABLE agent_runs DROP COLUMN IF EXISTS runtime_version")
