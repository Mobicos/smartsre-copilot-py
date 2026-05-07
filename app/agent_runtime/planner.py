"""Planning primitives for the Native Agent runtime."""

from __future__ import annotations

from typing import Any

from app.agent_runtime.state import AgentRunState


class AgentPlanner:
    """Create deterministic development-runtime plans from scene context and user goals."""

    @staticmethod
    def create_initial_state(goal: str) -> AgentRunState:
        return AgentRunState.from_goal(goal)

    @staticmethod
    def select_tool_names(scene: dict[str, Any]) -> list[str]:
        return [str(tool_name) for tool_name in scene.get("tools", [])]
