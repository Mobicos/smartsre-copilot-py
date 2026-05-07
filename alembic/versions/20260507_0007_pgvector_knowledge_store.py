"""Add pgvector knowledge store tables.

Revision ID: 20260507_0007
Revises: 20260428_0006
Create Date: 2026-05-07 00:00:00
"""

from __future__ import annotations

from alembic import op

revision = "20260507_0007"
down_revision = "20260428_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledge_documents (
            document_id TEXT PRIMARY KEY,
            collection_name TEXT NOT NULL,
            source TEXT NOT NULL,
            content TEXT NOT NULL,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledge_chunks (
            chunk_id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL REFERENCES knowledge_documents(document_id) ON DELETE CASCADE,
            collection_name TEXT NOT NULL,
            source TEXT NOT NULL,
            content TEXT NOT NULL,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            embedding vector(1024) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_knowledge_documents_collection_source
        ON knowledge_documents(collection_name, source)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_collection_source
        ON knowledge_chunks(collection_name, source)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_embedding_hnsw
        ON knowledge_chunks USING hnsw (embedding vector_cosine_ops)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_knowledge_chunks_embedding_hnsw")
    op.execute("DROP INDEX IF EXISTS idx_knowledge_chunks_collection_source")
    op.execute("DROP INDEX IF EXISTS idx_knowledge_documents_collection_source")
    op.execute("DROP TABLE IF EXISTS knowledge_chunks")
    op.execute("DROP TABLE IF EXISTS knowledge_documents")
