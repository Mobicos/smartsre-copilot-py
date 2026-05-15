"""PostgreSQL schema facade.

Table classes live in domain modules under ``app.platform.persistence.tables``.
This facade keeps existing imports stable and exposes ``REQUIRED_TABLES`` from
SQLModel metadata so table discovery does not need manual maintenance.
"""

from __future__ import annotations

from sqlmodel import SQLModel

from app.platform.persistence.tables import (
    AgentCheckpoint,
    AgentCheckpointBlob,
    AgentCheckpointWrite,
    AgentEvent,
    AgentFeedback,
    AgentMemory,
    AgentRun,
    AIOpsRun,
    AIOpsRunEvent,
    AuditLog,
    ChatToolEvent,
    IndexingTask,
    KnowledgeBase,
    Message,
    Scene,
    SceneKnowledgeBase,
    SceneTool,
    Session,
    ToolPolicy,
    Workspace,
)

REQUIRED_TABLES = tuple(SQLModel.metadata.tables.keys())

__all__ = [
    "AIOpsRun",
    "AIOpsRunEvent",
    "AgentCheckpoint",
    "AgentCheckpointBlob",
    "AgentCheckpointWrite",
    "AgentEvent",
    "AgentFeedback",
    "AgentMemory",
    "AgentRun",
    "AuditLog",
    "ChatToolEvent",
    "IndexingTask",
    "KnowledgeBase",
    "Message",
    "REQUIRED_TABLES",
    "Scene",
    "SceneKnowledgeBase",
    "SceneTool",
    "Session",
    "ToolPolicy",
    "Workspace",
]
