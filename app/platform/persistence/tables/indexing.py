"""Indexing persistence tables."""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class IndexingTask(SQLModel, table=True):
    __tablename__ = "indexing_tasks"

    task_id: str = Field(primary_key=True)
    filename: str
    file_path: str
    status: str
    attempt_count: int = Field(default=0)
    max_retries: int = Field(default=3)
    error_message: str | None = None
    created_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))
    updated_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))
