"""Add AIOps run event persistence.

Revision ID: 20260423_0004
Revises: 20260423_0003
Create Date: 2026-04-23 23:40:00
"""

from __future__ import annotations

from alembic import op

revision = "20260423_0004"
down_revision = "20260423_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS aiops_run_events (
            id BIGSERIAL PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES aiops_runs(run_id) ON DELETE CASCADE,
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
        CREATE INDEX IF NOT EXISTS idx_aiops_run_events_run_created
        ON aiops_run_events(run_id, created_at, id)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_aiops_run_events_run_created")
    op.execute("DROP TABLE IF EXISTS aiops_run_events")
