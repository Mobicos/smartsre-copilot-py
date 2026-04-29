"""Domain entities for the Native Agent bounded context."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Workspace:
    """Resource and collaboration boundary for Native Agent assets."""

    id: str
    name: str
    description: str | None = None

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> Workspace:
        return cls(
            id=str(record["id"]),
            name=str(record["name"]),
            description=record.get("description"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
        }


@dataclass(frozen=True)
class KnowledgeBase:
    """Knowledge base metadata attached to scenes."""

    id: str
    workspace_id: str
    name: str
    description: str | None = None
    version: str = "0.0.1"

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> KnowledgeBase:
        return cls(
            id=str(record["id"]),
            workspace_id=str(record["workspace_id"]),
            name=str(record["name"]),
            description=record.get("description"),
            version=str(record.get("version") or "0.0.1"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
        }


@dataclass(frozen=True)
class Scene:
    """A diagnosis scenario composed from knowledge, tools, and agent config."""

    id: str
    workspace_id: str
    name: str
    description: str | None = None
    knowledge_bases: list[KnowledgeBase] = field(default_factory=list)
    tool_names: list[str] = field(default_factory=list)
    agent_config: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> Scene:
        return cls(
            id=str(record["id"]),
            workspace_id=str(record["workspace_id"]),
            name=str(record["name"]),
            description=record.get("description"),
            knowledge_bases=[
                KnowledgeBase.from_record(item) for item in record.get("knowledge_bases", [])
            ],
            tool_names=[str(item) for item in record.get("tools", [])],
            agent_config=dict(record.get("agent_config") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "name": self.name,
            "description": self.description,
            "knowledge_bases": [item.to_dict() for item in self.knowledge_bases],
            "tools": self.tool_names,
            "agent_config": self.agent_config,
        }


@dataclass(frozen=True)
class ToolPolicy:
    """Governance policy for one executable tool."""

    tool_name: str
    scope: str = "diagnosis"
    risk_level: str = "low"
    capability: str | None = None
    enabled: bool = True
    approval_required: bool = False

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> ToolPolicy:
        return cls(
            tool_name=str(record["tool_name"]),
            scope=str(record.get("scope") or "diagnosis"),
            risk_level=str(record.get("risk_level") or "low"),
            capability=record.get("capability"),
            enabled=bool(record.get("enabled", True)),
            approval_required=bool(record.get("approval_required", False)),
        )

    def requires_approval(self) -> bool:
        return self.approval_required

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "scope": self.scope,
            "risk_level": self.risk_level,
            "capability": self.capability,
            "enabled": self.enabled,
            "approval_required": self.approval_required,
        }


@dataclass(frozen=True)
class AgentRun:
    """One auditable Native Agent execution."""

    id: str
    workspace_id: str
    scene_id: str
    session_id: str
    goal: str
    status: str
    final_report: str | None = None

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> AgentRun:
        return cls(
            id=str(record.get("id") or record["run_id"]),
            workspace_id=str(record["workspace_id"]),
            scene_id=str(record["scene_id"]),
            session_id=str(record["session_id"]),
            goal=str(record["goal"]),
            status=str(record["status"]),
            final_report=record.get("final_report"),
        )

    def is_completed(self) -> bool:
        return self.status == "completed"


@dataclass(frozen=True)
class AgentEvent:
    """Trajectory event recorded during a Native Agent run."""

    id: str
    run_id: str
    type: str
    stage: str
    message: str
    payload: dict[str, Any]

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> AgentEvent:
        return cls(
            id=str(record["id"]),
            run_id=str(record["run_id"]),
            type=str(record["type"]),
            stage=str(record["stage"]),
            message=str(record["message"]),
            payload=dict(record.get("payload") or {}),
        )
