"""Initial application schema.

Revision ID: 20260423_0001
Revises:
Create Date: 2026-04-23 01:50:00
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260423_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            session_type TEXT NOT NULL DEFAULT 'chat',
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id BIGSERIAL PRIMARY KEY,
            session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_messages_session_created_at
        ON messages(session_id, created_at, id)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS aiops_runs (
            run_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            status TEXT NOT NULL,
            task_input TEXT NOT NULL,
            report TEXT,
            error_message TEXT,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS indexing_tasks (
            task_id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            file_path TEXT NOT NULL,
            status TEXT NOT NULL,
            error_message TEXT,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_logs (
            id BIGSERIAL PRIMARY KEY,
            request_id TEXT NOT NULL,
            method TEXT NOT NULL,
            path TEXT NOT NULL,
            status_code INTEGER NOT NULL,
            subject TEXT,
            role TEXT,
            client_ip TEXT,
            user_agent TEXT,
            error_message TEXT,
            created_at TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_audit_logs_request_id
        ON audit_logs(request_id)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_audit_logs_request_id")
    op.execute("DROP TABLE IF EXISTS audit_logs")
    op.execute("DROP TABLE IF EXISTS indexing_tasks")
    op.execute("DROP TABLE IF EXISTS aiops_runs")
    op.execute("DROP INDEX IF EXISTS idx_messages_session_created_at")
    op.execute("DROP TABLE IF EXISTS messages")
    op.execute("DROP TABLE IF EXISTS sessions")
