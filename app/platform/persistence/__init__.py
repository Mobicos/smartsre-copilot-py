"""Platform persistence package."""

# ruff: noqa: E402

from app.platform.compat import stabilize_windows_platform_detection

stabilize_windows_platform_detection()

from app.platform.persistence.repositories.aiops import aiops_run_repository  # noqa: E402
from app.platform.persistence.repositories.audit import audit_log_repository  # noqa: E402
from app.platform.persistence.repositories.conversation import (
    chat_tool_event_repository,
    conversation_repository,
)  # noqa: E402
from app.platform.persistence.repositories.indexing import indexing_task_repository  # noqa: E402
from app.platform.persistence.repositories.native_agent import (
    agent_feedback_repository,
    agent_run_repository,
    knowledge_base_repository,
    scene_repository,
    tool_policy_repository,
    workspace_repository,
)  # noqa: E402

__all__ = [
    "agent_feedback_repository",
    "agent_run_repository",
    "aiops_run_repository",
    "audit_log_repository",
    "chat_tool_event_repository",
    "conversation_repository",
    "indexing_task_repository",
    "knowledge_base_repository",
    "scene_repository",
    "tool_policy_repository",
    "workspace_repository",
]
