"""Add cross-session agent memory."""

from __future__ import annotations

from alembic import op

revision = "20260508_0011"
down_revision = "20260508_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_memory (
            memory_id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
            run_id TEXT NULL REFERENCES agent_runs(run_id) ON DELETE SET NULL,
            conclusion_text TEXT NOT NULL,
            conclusion_type TEXT NOT NULL DEFAULT 'final_report',
            confidence DOUBLE PRECISION NOT NULL DEFAULT 0.5,
            validation_count INTEGER NOT NULL DEFAULT 0,
            metadata JSONB NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_agent_memory_workspace_updated "
        "ON agent_memory (workspace_id, updated_at DESC)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_agent_memory_run_id ON agent_memory (run_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_agent_memory_run_id")
    op.execute("DROP INDEX IF EXISTS ix_agent_memory_workspace_updated")
    op.execute("DROP TABLE IF EXISTS agent_memory")
