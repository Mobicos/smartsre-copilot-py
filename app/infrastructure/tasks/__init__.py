"""Task dispatch infrastructure."""

from __future__ import annotations

if True:
    from app.infrastructure.tasks.agent_resume import (
        AgentResumeDispatcher,
        agent_resume_dispatcher,
    )
    from app.infrastructure.tasks.dispatcher import LocalTaskDispatcher, task_dispatcher

# Type alias so mypy can follow the __getattr__ return types in consumers
TaskDispatcherType = LocalTaskDispatcher

__all__ = [
    "AgentResumeDispatcher",
    "LocalTaskDispatcher",
    "agent_resume_dispatcher",
    "task_dispatcher",
    "TaskDispatcherType",
]