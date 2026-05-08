"""Request schemas for Native Agent workspace APIs."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class WorkspaceCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    description: str | None = None


class SceneCreateRequest(BaseModel):
    workspace_id: str
    name: str = Field(min_length=1)
    description: str | None = None
    knowledge_base_ids: list[str] = Field(default_factory=list)
    tool_names: list[str] = Field(default_factory=list)
    agent_config: dict[str, Any] = Field(default_factory=dict)


class ToolPolicyUpdateRequest(BaseModel):
    scope: str | None = None
    risk_level: str | None = None
    capability: str | None = None
    enabled: bool | None = None
    approval_required: bool | None = None


class AgentRunCreateRequest(BaseModel):
    scene_id: str
    session_id: str = "default"
    goal: str = Field(min_length=1)
    success_criteria: list[str] = Field(default_factory=list)
    stop_condition: dict[str, Any] | None = None
    priority: str = Field(default="P2", pattern="^(P0|P1|P2|P3)$")


class AgentFeedbackCreateRequest(BaseModel):
    rating: str = Field(pattern="^(up|down|helpful|not_helpful|wrong|unsafe|incomplete)$")
    comment: str | None = None
