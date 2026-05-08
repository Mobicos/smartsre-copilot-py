"""Native Agent persistence tables."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


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
    decision_provider: str | None = None
    step_count: int | None = None
    tool_call_count: int | None = None
    latency_ms: int | None = None
    error_type: str | None = None
    approval_state: str | None = None
    retrieval_count: int | None = None
    cost_estimate: dict[str, Any] | None = Field(
        default=None,
        sa_column=sa.Column(sa.JSON, nullable=True),
    )
    handoff_reason: str | None = None
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
