"""PostgreSQL schema — SQLModel table definitions."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

# ---------------------------------------------------------------------------
# Conversation
# ---------------------------------------------------------------------------


class Session(SQLModel, table=True):
    __tablename__ = "sessions"

    session_id: str = Field(primary_key=True)
    title: str
    session_type: str = Field(default="chat")
    created_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))
    updated_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))


class Message(SQLModel, table=True):
    __tablename__ = "messages"
    __table_args__ = (
        sa.Index("idx_messages_session_created_at", "session_id", "created_at", "id"),
    )

    id: int | None = Field(
        sa_column=sa.Column(sa.BigInteger, primary_key=True, autoincrement=True), default=None
    )
    session_id: str = Field(foreign_key="sessions.session_id", ondelete="CASCADE")
    role: str
    content: str
    created_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))


class ChatToolEvent(SQLModel, table=True):
    __tablename__ = "chat_tool_events"
    __table_args__ = (
        sa.Index("idx_chat_tool_events_session_created", "session_id", "created_at", "id"),
    )

    id: int | None = Field(
        sa_column=sa.Column(sa.BigInteger, primary_key=True, autoincrement=True), default=None
    )
    session_id: str = Field(foreign_key="sessions.session_id", ondelete="CASCADE")
    exchange_id: str
    tool_name: str
    event_type: str
    payload: str | None = None
    created_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))


# ---------------------------------------------------------------------------
# AIOps
# ---------------------------------------------------------------------------


class AIOpsRun(SQLModel, table=True):
    __tablename__ = "aiops_runs"

    run_id: str = Field(primary_key=True)
    session_id: str
    status: str
    task_input: str
    report: str | None = None
    error_message: str | None = None
    created_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))
    updated_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))


class AIOpsRunEvent(SQLModel, table=True):
    __tablename__ = "aiops_run_events"
    __table_args__ = (sa.Index("idx_aiops_run_events_run_created", "run_id", "created_at", "id"),)

    id: int | None = Field(
        sa_column=sa.Column(sa.BigInteger, primary_key=True, autoincrement=True), default=None
    )
    run_id: str = Field(foreign_key="aiops_runs.run_id", ondelete="CASCADE")
    event_type: str
    stage: str
    message: str
    payload: str | None = None
    created_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))


# ---------------------------------------------------------------------------
# Indexing
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_logs"
    __table_args__ = (sa.Index("idx_audit_logs_request_id", "request_id"),)

    id: int | None = Field(
        sa_column=sa.Column(sa.BigInteger, primary_key=True, autoincrement=True), default=None
    )
    request_id: str
    method: str
    path: str
    status_code: int
    subject: str | None = None
    role: str | None = None
    client_ip: str | None = None
    user_agent: str | None = None
    error_message: str | None = None
    created_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))


# ---------------------------------------------------------------------------
# LangGraph Checkpoint
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Native Agent
# ---------------------------------------------------------------------------


class Workspace(SQLModel, table=True):
    __tablename__ = "workspaces"

    workspace_id: str = Field(primary_key=True)
    name: str
    description: str | None = None
    created_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))
    updated_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))


class KnowledgeBase(SQLModel, table=True):
    __tablename__ = "knowledge_bases"

    knowledge_base_id: str = Field(primary_key=True)
    workspace_id: str = Field(foreign_key="workspaces.workspace_id", ondelete="CASCADE")
    name: str
    description: str | None = None
    version: str = Field(default="0.0.1")
    created_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))
    updated_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))


class Scene(SQLModel, table=True):
    __tablename__ = "scenes"

    scene_id: str = Field(primary_key=True)
    workspace_id: str = Field(foreign_key="workspaces.workspace_id", ondelete="CASCADE")
    name: str
    description: str | None = None
    agent_config: str | None = None
    created_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))
    updated_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))


class SceneKnowledgeBase(SQLModel, table=True):
    __tablename__ = "scene_knowledge_bases"

    scene_id: str = Field(foreign_key="scenes.scene_id", ondelete="CASCADE", primary_key=True)
    knowledge_base_id: str = Field(
        foreign_key="knowledge_bases.knowledge_base_id", ondelete="CASCADE", primary_key=True
    )


class SceneTool(SQLModel, table=True):
    __tablename__ = "scene_tools"

    scene_id: str = Field(foreign_key="scenes.scene_id", ondelete="CASCADE", primary_key=True)
    tool_name: str = Field(primary_key=True)


class ToolPolicy(SQLModel, table=True):
    __tablename__ = "tool_policies"

    tool_name: str = Field(primary_key=True)
    scope: str = Field(default="diagnosis")
    risk_level: str = Field(default="low")
    capability: str | None = None
    enabled: bool = Field(default=True)
    approval_required: bool = Field(default=False)
    created_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))
    updated_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))


class AgentRun(SQLModel, table=True):
    __tablename__ = "agent_runs"

    run_id: str = Field(primary_key=True)
    workspace_id: str = Field(foreign_key="workspaces.workspace_id", ondelete="CASCADE")
    scene_id: str | None = Field(
        sa_column=sa.Column(
            sa.Text, sa.ForeignKey("scenes.scene_id", ondelete="SET NULL"), nullable=True
        )
    )
    session_id: str
    status: str
    goal: str
    final_report: str | None = None
    error_message: str | None = None
    runtime_version: str | None = None
    trace_id: str | None = None
    model_name: str | None = None
    step_count: int | None = None
    tool_call_count: int | None = None
    latency_ms: int | None = None
    error_type: str | None = None
    approval_state: str | None = None
    retrieval_count: int | None = None
    token_usage: dict[str, Any] | None = Field(
        default=None,
        sa_column=sa.Column(sa.JSON, nullable=True),
    )
    created_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))
    updated_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))


class AgentEvent(SQLModel, table=True):
    __tablename__ = "agent_events"
    __table_args__ = (sa.Index("idx_agent_events_run_created", "run_id", "created_at", "id"),)

    id: int | None = Field(
        sa_column=sa.Column(sa.BigInteger, primary_key=True, autoincrement=True), default=None
    )
    run_id: str = Field(foreign_key="agent_runs.run_id", ondelete="CASCADE")
    event_type: str
    stage: str
    message: str
    payload: str | None = None
    created_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))


class AgentFeedback(SQLModel, table=True):
    __tablename__ = "agent_feedback"

    feedback_id: str = Field(primary_key=True)
    run_id: str = Field(foreign_key="agent_runs.run_id", ondelete="CASCADE")
    rating: str
    comment: str | None = None
    created_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REQUIRED_TABLES = (
    "sessions",
    "messages",
    "chat_tool_events",
    "aiops_runs",
    "aiops_run_events",
    "indexing_tasks",
    "audit_logs",
    "agent_checkpoints",
    "agent_checkpoint_blobs",
    "agent_checkpoint_writes",
    "workspaces",
    "knowledge_bases",
    "scenes",
    "scene_knowledge_bases",
    "scene_tools",
    "tool_policies",
    "agent_runs",
    "agent_events",
    "agent_feedback",
)
