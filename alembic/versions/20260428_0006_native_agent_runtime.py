"""Add native agent product and trajectory tables.

Revision ID: 20260428_0006
Revises: 20260423_0005
Create Date: 2026-04-28 00:00:00
"""

from __future__ import annotations

from alembic import op

revision = "20260428_0006"
down_revision = "20260423_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS workspaces (
            workspace_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledge_bases (
            knowledge_base_id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            description TEXT,
            version TEXT NOT NULL DEFAULT '0.0.1',
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS scenes (
            scene_id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            description TEXT,
            agent_config TEXT,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS scene_knowledge_bases (
            scene_id TEXT NOT NULL REFERENCES scenes(scene_id) ON DELETE CASCADE,
            knowledge_base_id TEXT NOT NULL REFERENCES knowledge_bases(knowledge_base_id) ON DELETE CASCADE,
            PRIMARY KEY(scene_id, knowledge_base_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS scene_tools (
            scene_id TEXT NOT NULL REFERENCES scenes(scene_id) ON DELETE CASCADE,
            tool_name TEXT NOT NULL,
            PRIMARY KEY(scene_id, tool_name)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tool_policies (
            tool_name TEXT PRIMARY KEY,
            scope TEXT NOT NULL DEFAULT 'diagnosis',
            risk_level TEXT NOT NULL DEFAULT 'low',
            capability TEXT,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            approval_required BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_runs (
            run_id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
            scene_id TEXT REFERENCES scenes(scene_id) ON DELETE SET NULL,
            session_id TEXT NOT NULL,
            status TEXT NOT NULL,
            goal TEXT NOT NULL,
            final_report TEXT,
            error_message TEXT,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_events (
            id BIGSERIAL PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES agent_runs(run_id) ON DELETE CASCADE,
            event_type TEXT NOT NULL,
            stage TEXT NOT NULL,
            message TEXT NOT NULL,
            payload TEXT,
            created_at TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_agent_events_run_created
        ON agent_events(run_id, created_at, id)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_feedback (
            feedback_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES agent_runs(run_id) ON DELETE CASCADE,
            rating TEXT NOT NULL,
            comment TEXT,
            created_at TIMESTAMPTZ NOT NULL
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_feedback")
    op.execute("DROP INDEX IF EXISTS idx_agent_events_run_created")
    op.execute("DROP TABLE IF EXISTS agent_events")
    op.execute("DROP TABLE IF EXISTS agent_runs")
    op.execute("DROP TABLE IF EXISTS tool_policies")
    op.execute("DROP TABLE IF EXISTS scene_tools")
    op.execute("DROP TABLE IF EXISTS scene_knowledge_bases")
    op.execute("DROP TABLE IF EXISTS scenes")
    op.execute("DROP TABLE IF EXISTS knowledge_bases")
    op.execute("DROP TABLE IF EXISTS workspaces")
