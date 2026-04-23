"""Add retry metadata to indexing tasks.

Revision ID: 20260423_0002
Revises: 20260423_0001
Create Date: 2026-04-23 06:00:00
"""

from __future__ import annotations

from alembic import op


revision = "20260423_0002"
down_revision = "20260423_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE indexing_tasks
        ADD COLUMN IF NOT EXISTS attempt_count INTEGER NOT NULL DEFAULT 0
        """
    )
    op.execute(
        """
        ALTER TABLE indexing_tasks
        ADD COLUMN IF NOT EXISTS max_retries INTEGER NOT NULL DEFAULT 3
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE indexing_tasks
        DROP COLUMN IF EXISTS max_retries
        """
    )
    op.execute(
        """
        ALTER TABLE indexing_tasks
        DROP COLUMN IF EXISTS attempt_count
        """
    )
