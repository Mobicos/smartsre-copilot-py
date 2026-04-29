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
    scope: str = "diagnosis"
    risk_level: str = "low"
    capability: str | None = None
    enabled: bool = True
    approval_required: bool = False


class AgentRunCreateRequest(BaseModel):
    scene_id: str
    session_id: str = "default"
    goal: str = Field(min_length=1)


class AgentFeedbackCreateRequest(BaseModel):
    rating: str = Field(pattern="^(up|down)$")
    comment: str | None = None
