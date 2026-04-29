"""Policy gate for planned Native Agent actions."""

from __future__ import annotations

from app.agent_runtime.ports import ToolPolicyStore
from app.agent_runtime.state import ToolAction


class ToolPolicyGate:
    """Attach the current governance policy snapshot to tool actions."""

    def __init__(self, *, policy_store: ToolPolicyStore) -> None:
        self._policy_store = policy_store

    def create_action(self, tool_name: str, *, goal: str) -> ToolAction:
        policy = self._policy_store.get_policy(tool_name)
        return ToolAction.from_tool_name(tool_name, goal=goal, policy=policy)
