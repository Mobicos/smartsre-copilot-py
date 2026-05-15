"""Domain table modules registered into SQLModel metadata."""

from app.platform.persistence.tables.agent import (
    AgentEvent,
    AgentFeedback,
    AgentMemory,
    AgentRun,
    KnowledgeBase,
    Scene,
    SceneKnowledgeBase,
    SceneTool,
    ToolPolicy,
    Workspace,
)
from app.platform.persistence.tables.aiops import AIOpsRun, AIOpsRunEvent
from app.platform.persistence.tables.audit import AuditLog
from app.platform.persistence.tables.checkpoint import (
    AgentCheckpoint,
    AgentCheckpointBlob,
    AgentCheckpointWrite,
)
from app.platform.persistence.tables.conversation import (
    ChatToolEvent,
    Message,
    Session,
)
from app.platform.persistence.tables.indexing import IndexingTask

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
    "Scene",
    "SceneKnowledgeBase",
    "SceneTool",
    "Session",
    "ToolPolicy",
    "Workspace",
]
