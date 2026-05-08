"""LangGraph checkpoint persistence tables."""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class AgentCheckpoint(SQLModel, table=True):
    __tablename__ = "agent_checkpoints"
    __table_args__ = (
        sa.Index(
            "idx_agent_checkpoints_thread_created",
            "thread_id",
            "checkpoint_ns",
            "checkpoint_id",
        ),
        {"extend_existing": True},
    )

    thread_id: str = Field(primary_key=True)
    checkpoint_ns: str = Field(default="", primary_key=True)
    checkpoint_id: str = Field(primary_key=True)
    checkpoint_type: str
    checkpoint_data: bytes = Field(sa_column=sa.Column(sa.LargeBinary, nullable=False))
    metadata_type: str
    metadata_data: bytes = Field(sa_column=sa.Column(sa.LargeBinary, nullable=False))
    parent_checkpoint_id: str | None = None
    created_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))


class AgentCheckpointBlob(SQLModel, table=True):
    __tablename__ = "agent_checkpoint_blobs"

    thread_id: str = Field(primary_key=True)
    checkpoint_ns: str = Field(default="", primary_key=True)
    channel: str = Field(primary_key=True)
    version: str = Field(primary_key=True)
    value_type: str
    value_data: bytes = Field(sa_column=sa.Column(sa.LargeBinary, nullable=False))


class AgentCheckpointWrite(SQLModel, table=True):
    __tablename__ = "agent_checkpoint_writes"

    thread_id: str = Field(primary_key=True)
    checkpoint_ns: str = Field(default="", primary_key=True)
    checkpoint_id: str = Field(primary_key=True)
    task_id: str = Field(primary_key=True)
    write_idx: int = Field(primary_key=True)
    channel: str
    value_type: str
    value_data: bytes = Field(sa_column=sa.Column(sa.LargeBinary, nullable=False))
    task_path: str = Field(default="")
