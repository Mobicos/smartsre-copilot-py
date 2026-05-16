"""Add embedding vector column to agent_memory for pgvector similarity search."""

from __future__ import annotations

from sqlalchemy import text

from alembic import op

revision = "20260516_0015"
down_revision = "20260516_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    vector_exists = bind.execute(text("SELECT to_regtype('vector') IS NOT NULL")).scalar()
    if not vector_exists:
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute(
        "ALTER TABLE agent_memory "
        "ADD COLUMN IF NOT EXISTS embedding vector(1024)"
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_agent_memory_embedding_hnsw
        ON agent_memory USING hnsw (embedding vector_cosine_ops)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_agent_memory_embedding_hnsw")
    op.execute("ALTER TABLE agent_memory DROP COLUMN IF EXISTS embedding")
