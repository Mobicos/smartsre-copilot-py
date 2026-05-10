"""Policy gate for planned Native Agent actions."""

from __future__ import annotations

from typing import Any

from app.agent_runtime.constants import SIDE_EFFECTS_REQUIRING_APPROVAL
from app.agent_runtime.ports import ToolPolicyStore
from app.agent_runtime.state import ToolAction


class ToolPolicyGate:
    """Attach the current governance policy snapshot to tool actions.

    Merges the registry-level ToolSchema metadata with any DB-stored
    policy overrides so that ``ToolAction`` carries the effective policy.
    """

    def __init__(self, *, policy_store: ToolPolicyStore) -> None:
        self._policy_store = policy_store

    def create_action(
        self,
        tool_name: str,
        *,
        goal: str,
        tool_schema: Any | None = None,
    ) -> ToolAction:
        policy = self._build_effective_policy(tool_name, tool_schema=tool_schema)
        # Extract input_schema dict for argument inference if available
        schema_dict = getattr(tool_schema, "input_schema", None) if tool_schema else None
        return ToolAction.from_tool_name(
            tool_name, goal=goal, policy=policy, tool_schema=schema_dict
        )

    def _build_effective_policy(
        self,
        tool_name: str,
        *,
        tool_schema: Any | None = None,
    ) -> dict[str, Any]:
        base: dict[str, Any] = {}
        if tool_schema is not None:
            side_effect = str(getattr(tool_schema, "side_effect", "none") or "none")
            approval_required = bool(getattr(tool_schema, "approval_required", False))
            if side_effect in SIDE_EFFECTS_REQUIRING_APPROVAL:
                approval_required = True
            base = {
                "tool_name": tool_name,
                "scope": str(getattr(tool_schema, "scope", "diagnosis") or "diagnosis"),
                "risk_level": str(getattr(tool_schema, "risk_level", "low") or "low"),
                "capability": getattr(tool_schema, "capability", None),
                "enabled": True,
                "approval_required": approval_required,
            }

        override = self._policy_store.get_policy(tool_name)
        if override:
            merged = {**base} if base else {"tool_name": tool_name}
            merged.update(
                {
                    "tool_name": str(override.get("tool_name") or tool_name),
                    "scope": str(override.get("scope") or merged.get("scope", "diagnosis")),
                    "risk_level": str(
                        override.get("risk_level") or merged.get("risk_level", "low")
                    ),
                    "capability": override.get("capability") or merged.get("capability"),
                    "enabled": bool(override.get("enabled", merged.get("enabled", True))),
                    "approval_required": bool(
                        override.get("approval_required", merged.get("approval_required", False))
                    ),
                }
            )
            return merged

        return base if base else {"tool_name": tool_name}
