"""Add chat tool event persistence.

Revision ID: 20260423_0005
Revises: 20260423_0004
Create Date: 2026-04-23 23:55:00
"""

from __future__ import annotations

from alembic import op

revision = "20260423_0005"
down_revision = "20260423_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_tool_events (
            id BIGSERIAL PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
            exchange_id TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload TEXT,
            created_at TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_chat_tool_events_session_created
        ON chat_tool_events(session_id, created_at, id)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_chat_tool_events_session_created")
    op.execute("DROP TABLE IF EXISTS chat_tool_events")
