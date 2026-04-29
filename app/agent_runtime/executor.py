"""Tool execution step for the Native Agent runtime."""

from __future__ import annotations

from typing import Any

from app.agent_runtime.state import ToolAction


class AgentToolExecutor:
    """Execute planned tool actions through the configured tool executor."""

    def __init__(self, *, tool_executor: Any) -> None:
        self._tool_executor = tool_executor

    async def execute(
        self,
        tool: Any,
        action: ToolAction,
        *,
        principal: Any,
    ) -> Any:
        return await self._tool_executor.execute(
            tool,
            action.arguments,
            principal=principal,
        )
