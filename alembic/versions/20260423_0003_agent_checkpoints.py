"""Add persistent agent checkpoint tables.

Revision ID: 20260423_0003
Revises: 20260423_0002
Create Date: 2026-04-23 08:40:00
"""

from __future__ import annotations

from alembic import op

revision = "20260423_0003"
down_revision = "20260423_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_checkpoints (
            thread_id TEXT NOT NULL,
            checkpoint_ns TEXT NOT NULL DEFAULT '',
            checkpoint_id TEXT NOT NULL,
            checkpoint_type TEXT NOT NULL,
            checkpoint_data BYTEA NOT NULL,
            metadata_type TEXT NOT NULL,
            metadata_data BYTEA NOT NULL,
            parent_checkpoint_id TEXT,
            created_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY(thread_id, checkpoint_ns, checkpoint_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_agent_checkpoints_thread_created
        ON agent_checkpoints(thread_id, checkpoint_ns, checkpoint_id DESC)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_checkpoint_blobs (
            thread_id TEXT NOT NULL,
            checkpoint_ns TEXT NOT NULL DEFAULT '',
            channel TEXT NOT NULL,
            version TEXT NOT NULL,
            value_type TEXT NOT NULL,
            value_data BYTEA NOT NULL,
            PRIMARY KEY(thread_id, checkpoint_ns, channel, version)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_checkpoint_writes (
            thread_id TEXT NOT NULL,
            checkpoint_ns TEXT NOT NULL DEFAULT '',
            checkpoint_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            write_idx INTEGER NOT NULL,
            channel TEXT NOT NULL,
            value_type TEXT NOT NULL,
            value_data BYTEA NOT NULL,
            task_path TEXT NOT NULL DEFAULT '',
            PRIMARY KEY(thread_id, checkpoint_ns, checkpoint_id, task_id, write_idx)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_checkpoint_writes")
    op.execute("DROP TABLE IF EXISTS agent_checkpoint_blobs")
    op.execute("DROP INDEX IF EXISTS idx_agent_checkpoints_thread_created")
    op.execute("DROP TABLE IF EXISTS agent_checkpoints")
