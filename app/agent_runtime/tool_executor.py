"""Tool execution boundary for the Native Agent runtime."""

from __future__ import annotations

import asyncio
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
    policy: dict[str, Any] | None = None
    decision: str = "executed"
    decision_reason: str | None = None

    def governance_payload(self) -> dict[str, Any]:
        """Return an audit-friendly policy decision payload."""
        return {
            "decision": self.decision,
            "reason": self.decision_reason,
            "policy": self.policy,
        }


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
        policy = self._normalized_policy(tool_name, tool=tool)

        if not bool(policy["enabled"]):
            return ToolExecutionResult(
                tool_name=tool_name,
                status="disabled",
                arguments=arguments,
                policy=policy,
                decision="denied",
                decision_reason="Tool is disabled by policy",
            )

        capability = policy.get("capability")
        if capability and not self._has_capability(getattr(principal, "role", ""), capability):
            return ToolExecutionResult(
                tool_name=tool_name,
                status="forbidden",
                arguments=arguments,
                error=f"Missing capability: {capability}",
                policy=policy,
                decision="denied",
                decision_reason=f"Principal is missing required capability: {capability}",
            )

        validation_error = self._validate_arguments(tool, arguments)
        if validation_error:
            return ToolExecutionResult(
                tool_name=tool_name,
                status="invalid_input",
                arguments=arguments,
                error=validation_error,
                policy=policy,
                decision="denied",
                decision_reason="Tool arguments failed schema validation",
            )

        if bool(policy["approval_required"]):
            return ToolExecutionResult(
                tool_name=tool_name,
                status="approval_required",
                arguments=arguments,
                policy=policy,
                decision="approval_required",
                decision_reason="Tool requires explicit approval before execution",
            )

        try:
            output = await self._invoke_tool_with_policy(tool, arguments, policy=policy)
            return ToolExecutionResult(
                tool_name=tool_name,
                status="success",
                arguments=arguments,
                output=output,
                policy=policy,
                decision="executed",
                decision_reason="Tool execution allowed by policy",
            )
        except Exception as exc:  # pragma: no cover - defensive boundary
            return ToolExecutionResult(
                tool_name=tool_name,
                status="error",
                arguments=arguments,
                error=str(exc),
                policy=policy,
                decision="executed",
                decision_reason="Tool execution allowed by policy but failed",
            )

    async def execute_approved(
        self,
        tool: Any,
        arguments: dict[str, Any],
        *,
        principal: Any,
        approval: dict[str, Any],
    ) -> ToolExecutionResult:
        """Execute an action that was previously blocked and explicitly approved."""
        tool_name = self._tool_name(tool)
        policy = self._normalized_policy(tool_name, tool=tool)
        approved_tool = str(approval.get("tool_name") or "")
        approved_decision = str(approval.get("decision") or "")

        if approved_tool != tool_name or approved_decision != "approved":
            return ToolExecutionResult(
                tool_name=tool_name,
                status="forbidden",
                arguments=arguments,
                error="Approved action does not match requested tool execution",
                policy=policy,
                decision="denied",
                decision_reason="Approval payload did not match the original tool action",
            )

        if not bool(policy["enabled"]):
            return ToolExecutionResult(
                tool_name=tool_name,
                status="disabled",
                arguments=arguments,
                policy=policy,
                decision="denied",
                decision_reason="Tool is disabled by policy",
            )

        capability = policy.get("capability")
        if capability and not self._has_capability(getattr(principal, "role", ""), capability):
            return ToolExecutionResult(
                tool_name=tool_name,
                status="forbidden",
                arguments=arguments,
                error=f"Missing capability: {capability}",
                policy=policy,
                decision="denied",
                decision_reason=f"Principal is missing required capability: {capability}",
            )

        validation_error = self._validate_arguments(tool, arguments)
        if validation_error:
            return ToolExecutionResult(
                tool_name=tool_name,
                status="invalid_input",
                arguments=arguments,
                error=validation_error,
                policy=policy,
                decision="denied",
                decision_reason="Tool arguments failed schema validation",
            )

        try:
            output = await self._invoke_tool_with_policy(tool, arguments, policy=policy)
            return ToolExecutionResult(
                tool_name=tool_name,
                status="success",
                arguments=arguments,
                output=output,
                policy=policy,
                decision="executed_after_approval",
                decision_reason="Tool execution matched an explicit approval decision",
            )
        except Exception as exc:  # pragma: no cover - defensive boundary
            return ToolExecutionResult(
                tool_name=tool_name,
                status="error",
                arguments=arguments,
                error=str(exc),
                policy=policy,
                decision="executed_after_approval",
                decision_reason="Approved tool execution failed",
            )

    def _normalized_policy(self, tool_name: str, *, tool: Any | None = None) -> dict[str, Any]:
        policy = self._default_policy(tool_name, tool=tool)
        override = self._policy_store.get_policy(tool_name)
        if override:
            policy.update(
                {
                    "tool_name": str(override.get("tool_name") or tool_name),
                    "scope": str(override.get("scope") or policy["scope"]),
                    "risk_level": str(override.get("risk_level") or policy["risk_level"]),
                    "capability": override.get("capability"),
                    "enabled": bool(override.get("enabled", policy["enabled"])),
                    "approval_required": bool(
                        override.get("approval_required", policy["approval_required"])
                    ),
                }
            )
        return policy

    @staticmethod
    def _default_policy(tool_name: str, *, tool: Any | None = None) -> dict[str, Any]:
        side_effect = str(getattr(tool, "side_effect", "none") or "none")
        approval_required = bool(getattr(tool, "approval_required", False))
        if side_effect == "destructive":
            approval_required = True
        return {
            "tool_name": tool_name,
            "scope": str(getattr(tool, "scope", "diagnosis") or "diagnosis"),
            "risk_level": str(getattr(tool, "risk_level", "low") or "low"),
            "capability": getattr(tool, "capability", None),
            "enabled": True,
            "approval_required": approval_required,
            "timeout_seconds": float(getattr(tool, "timeout_seconds", 30.0) or 30.0),
            "retry_count": max(int(getattr(tool, "retry_count", 0) or 0), 0),
            "owner": str(getattr(tool, "owner", "SmartSRE") or "SmartSRE"),
            "data_boundary": str(getattr(tool, "data_boundary", "workspace") or "workspace"),
            "side_effect": side_effect,
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

    async def _invoke_tool_with_policy(
        self,
        tool: Any,
        arguments: dict[str, Any],
        *,
        policy: dict[str, Any],
    ) -> Any:
        retry_count = max(int(policy.get("retry_count") or 0), 0)
        timeout_seconds = float(policy.get("timeout_seconds") or 30.0)
        last_error: Exception | None = None
        for attempt in range(retry_count + 1):
            try:
                return await asyncio.wait_for(
                    self._invoke_tool(tool, arguments),
                    timeout=timeout_seconds,
                )
            except TimeoutError as exc:
                last_error = exc
                if attempt >= retry_count:
                    raise TimeoutError(
                        f"Tool execution timed out after {timeout_seconds:g} seconds"
                    ) from exc
            except Exception as exc:
                last_error = exc
                if attempt >= retry_count:
                    raise
        if last_error is not None:
            raise last_error
        return None

    @staticmethod
    def _validate_arguments(tool: Any, arguments: dict[str, Any]) -> str | None:
        args_schema = getattr(tool, "args_schema", None)
        if args_schema is None:
            return None

        try:
            if hasattr(args_schema, "model_validate"):
                args_schema.model_validate(arguments)
                return None
            if hasattr(args_schema, "parse_obj"):
                args_schema.parse_obj(arguments)
                return None
            if isinstance(args_schema, dict):
                return _validate_json_schema_arguments(args_schema, arguments)
        except Exception as exc:
            return str(exc)

        return None

    @staticmethod
    def _tool_name(tool: Any) -> str:
        if hasattr(tool, "name"):
            return str(tool.name)
        return repr(tool)


def _validate_json_schema_arguments(schema: dict[str, Any], arguments: dict[str, Any]) -> str | None:
    required = schema.get("required") or []
    missing = [name for name in required if name not in arguments]
    if missing:
        return f"Missing required arguments: {', '.join(str(item) for item in missing)}"

    properties = schema.get("properties") or {}
    for name, value in arguments.items():
        expected = properties.get(name)
        if not isinstance(expected, dict):
            continue
        expected_type = expected.get("type")
        if expected_type and not _matches_json_schema_type(value, str(expected_type)):
            return f"Argument {name} must be {expected_type}"
    return None


def _matches_json_schema_type(value: Any, expected_type: str) -> bool:
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return (isinstance(value, int | float)) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "array":
        return isinstance(value, list)
    return True
