"""Tool execution boundary for the Native Agent runtime."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any

from app.agent_runtime.ports import ToolPolicyStore
from app.security.auth import ROLE_CAPABILITIES


@dataclass(frozen=True)
class ToolExecutionResult:
    """Normalized tool execution result."""

    tool_name: str
    status: str
    arguments: dict[str, Any]
    output: Any = None
    error: str | None = None


class ToolPolicyRepositoryAdapter:
    """Adapter around the persistence repository."""

    def __init__(self, repository: ToolPolicyStore) -> None:
        self._repository = repository

    def get_policy(self, tool_name: str) -> dict[str, Any] | None:
        return self._repository.get_policy(tool_name)


class ToolExecutor:
    """Execute tools behind policy and normalization boundaries."""

    def __init__(self, *, policy_store: ToolPolicyStore) -> None:
        self._policy_store = policy_store

    async def execute(
        self,
        tool: Any,
        arguments: dict[str, Any],
        *,
        principal: Any,
    ) -> ToolExecutionResult:
        tool_name = self._tool_name(tool)
        policy = self._policy_store.get_policy(tool_name) or self._default_policy(tool_name)

        if not bool(policy["enabled"]):
            return ToolExecutionResult(
                tool_name=tool_name,
                status="disabled",
                arguments=arguments,
            )

        capability = policy.get("capability")
        if capability and not self._has_capability(getattr(principal, "role", ""), capability):
            return ToolExecutionResult(
                tool_name=tool_name,
                status="forbidden",
                arguments=arguments,
                error=f"Missing capability: {capability}",
            )

        if bool(policy["approval_required"]):
            return ToolExecutionResult(
                tool_name=tool_name,
                status="approval_required",
                arguments=arguments,
            )

        try:
            output = await self._invoke_tool(tool, arguments)
            return ToolExecutionResult(
                tool_name=tool_name,
                status="success",
                arguments=arguments,
                output=output,
            )
        except Exception as exc:  # pragma: no cover - defensive boundary
            return ToolExecutionResult(
                tool_name=tool_name,
                status="error",
                arguments=arguments,
                error=str(exc),
            )

    @staticmethod
    def _default_policy(tool_name: str) -> dict[str, Any]:
        return {
            "tool_name": tool_name,
            "scope": "diagnosis",
            "risk_level": "low",
            "capability": None,
            "enabled": True,
            "approval_required": False,
        }

    @staticmethod
    def _has_capability(role: str, capability: str) -> bool:
        capabilities = ROLE_CAPABILITIES.get(role, set())
        return "*" in capabilities or capability in capabilities

    @staticmethod
    async def _invoke_tool(tool: Any, arguments: dict[str, Any]) -> Any:
        if hasattr(tool, "ainvoke"):
            return await tool.ainvoke(arguments)
        if hasattr(tool, "invoke"):
            return tool.invoke(arguments)
        result = tool(**arguments) if callable(tool) else None
        if inspect.isawaitable(result):
            return await result
        return result

    @staticmethod
    def _tool_name(tool: Any) -> str:
        if hasattr(tool, "name"):
            return str(tool.name)
        return repr(tool)
