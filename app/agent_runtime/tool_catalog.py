"""Tool discovery for the Native Agent runtime."""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any

from app.agent_runtime.constants import SIDE_EFFECTS_REQUIRING_APPROVAL
from app.infrastructure.tools import ToolScope, tool_registry


@dataclass(frozen=True)
class ToolSchema:
    """Standard tool contract consumed by policy and execution layers."""

    name: str
    description: str
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    scope: str = "diagnosis"
    risk_level: str = "low"
    capability: str | None = None
    timeout_seconds: float = 30.0
    retry_count: int = 0
    approval_required: bool = False
    owner: str = "SmartSRE"
    data_boundary: str = "workspace"
    side_effect: str = "none"
    fallback_strategy: str = "handoff"
    raw_tool: Any = field(default=None, repr=False, compare=False)

    @property
    def args_schema(self) -> dict[str, Any] | None:
        return self.input_schema

    async def ainvoke(self, arguments: dict[str, Any]) -> Any:
        tool = self.raw_tool
        if tool is None:
            return None
        if hasattr(tool, "ainvoke"):
            return await tool.ainvoke(arguments)
        if hasattr(tool, "invoke"):
            return tool.invoke(arguments)
        result = tool(**arguments) if callable(tool) else None
        if inspect.isawaitable(result):
            return await result
        return result


class ToolCatalog:
    """Discover local and MCP tools through the existing registry."""

    async def get_tools(
        self,
        scope: ToolScope,
        *,
        force_refresh: bool = False,
    ) -> list[ToolSchema]:
        tools = await tool_registry.get_tools(scope, force_refresh=force_refresh)  # type: ignore[attr-defined]
        return [_tool_to_schema(tool, scope=str(scope)) for tool in tools]


def _tool_to_schema(tool: Any, *, scope: str) -> ToolSchema:
    input_schema = _input_schema(tool)
    side_effect = str(getattr(tool, "side_effect", "none") or "none")
    approval_required = bool(getattr(tool, "approval_required", False))
    if side_effect in SIDE_EFFECTS_REQUIRING_APPROVAL:
        approval_required = True
    return ToolSchema(
        name=str(getattr(tool, "name", repr(tool))),
        description=str(getattr(tool, "description", "")),
        input_schema=input_schema,
        output_schema=_output_schema(tool),
        scope=str(getattr(tool, "scope", scope) or scope),
        risk_level=str(getattr(tool, "risk_level", "low") or "low"),
        capability=getattr(tool, "capability", None),
        timeout_seconds=float(getattr(tool, "timeout_seconds", 30.0) or 30.0),
        retry_count=max(int(getattr(tool, "retry_count", 0) or 0), 0),
        approval_required=approval_required,
        owner=str(getattr(tool, "owner", "SmartSRE") or "SmartSRE"),
        data_boundary=str(getattr(tool, "data_boundary", "workspace") or "workspace"),
        side_effect=side_effect,
        fallback_strategy=str(getattr(tool, "fallback_strategy", "handoff") or "handoff"),
        raw_tool=tool,
    )


def _input_schema(tool: Any) -> dict[str, Any] | None:
    args_schema = getattr(tool, "args_schema", None)
    return _schema_to_dict(args_schema)


def _output_schema(tool: Any) -> dict[str, Any] | None:
    output_schema = getattr(tool, "output_schema", None)
    return _schema_to_dict(output_schema)


def _schema_to_dict(schema_source: Any) -> dict[str, Any] | None:
    args_schema = schema_source
    if args_schema is None:
        return None
    if isinstance(args_schema, dict):
        return args_schema
    if hasattr(args_schema, "model_json_schema"):
        schema = args_schema.model_json_schema()
        return schema if isinstance(schema, dict) else None
    if hasattr(args_schema, "schema"):
        schema = args_schema.schema()
        return schema if isinstance(schema, dict) else None
    return None
