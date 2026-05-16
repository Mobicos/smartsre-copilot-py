"""Typed state primitives for the Native Agent loop."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from typing import Any

from app.agent_runtime.constants import MAX_TOOL_OUTPUT_CHARS

_MAX_TOOL_OUTPUT_CHARS = MAX_TOOL_OUTPUT_CHARS


@dataclass(frozen=True)
class Hypothesis:
    """A diagnostic hypothesis generated from a user goal."""

    summary: str

    @classmethod
    def from_goal(cls, goal: str) -> Hypothesis:
        return cls(
            summary=(f"调查目标「{goal}」，先检查场景知识、已批准工具和已采集证据，再给出结论。")
        )


@dataclass(frozen=True)
class KnowledgeContext:
    """Scene-scoped knowledge metadata loaded for an Agent run."""

    knowledge_bases: list[dict[str, Any]]

    @classmethod
    def empty(cls) -> KnowledgeContext:
        return cls(knowledge_bases=[])

    @property
    def summary(self) -> str:
        if not self.knowledge_bases:
            return "未配置场景知识库。"
        names = ", ".join(str(item["name"]) for item in self.knowledge_bases)
        count = len(self.knowledge_bases)
        return f"已加载场景知识库 {count} 个：{names}"

    def has_knowledge(self) -> bool:
        return bool(self.knowledge_bases)

    def to_event_payload(self) -> dict[str, Any]:
        return {
            "knowledge_bases": self.knowledge_bases,
            "summary": self.summary,
        }

    def to_report_lines(self) -> list[str]:
        return [
            f"- {item['name']} ({item['version']}): {item.get('description') or '暂无描述'}"
            for item in self.knowledge_bases
        ]


@dataclass(frozen=True)
class ToolPolicySnapshot:
    """Tool governance policy captured at planning time."""

    tool_name: str
    scope: str = "diagnosis"
    risk_level: str = "low"
    capability: str | None = None
    enabled: bool = True
    approval_required: bool = False

    @classmethod
    def from_policy(
        cls,
        policy: dict[str, Any] | None,
        *,
        tool_name: str,
    ) -> ToolPolicySnapshot:
        if policy is None:
            return cls(tool_name=tool_name)
        return cls(
            tool_name=str(policy.get("tool_name") or tool_name),
            scope=str(policy.get("scope") or "diagnosis"),
            risk_level=str(policy.get("risk_level") or "low"),
            capability=policy.get("capability"),
            enabled=bool(policy.get("enabled", True)),
            approval_required=bool(policy.get("approval_required", False)),
        )

    @property
    def approval_state(self) -> str:
        return "required" if self.approval_required else "not_required"

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "scope": self.scope,
            "risk_level": self.risk_level,
            "capability": self.capability,
            "enabled": self.enabled,
            "approval_required": self.approval_required,
        }


def _infer_arguments(
    tool_name: str,
    *,
    goal: str,
    tool_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build tool arguments from the goal, using schema properties when available."""
    # If we have a tool schema with properties, map goal to matching string properties
    if tool_schema and isinstance(tool_schema, dict):
        properties = tool_schema.get("properties", {})
        if properties and isinstance(properties, dict):
            arguments: dict[str, Any] = {}
            for prop_name, prop_def in properties.items():
                if isinstance(prop_def, dict) and prop_def.get("type") == "string":
                    arguments[prop_name] = goal
            if arguments:
                return arguments

    # Fallback: infer from tool name heuristics
    lowered = tool_name.lower()
    if "log" in lowered or "search" in lowered:
        return {"query": goal, "keyword": goal}
    if "metric" in lowered or "monitor" in lowered:
        return {"query": goal}
    return {"query": goal}


@dataclass(frozen=True)
class ToolAction:
    """A planned tool action with normalized arguments."""

    tool_name: str
    arguments: dict[str, Any]
    policy_snapshot: ToolPolicySnapshot
    execution_status: str = "pending"

    @classmethod
    def from_tool_name(
        cls,
        tool_name: str,
        *,
        goal: str,
        policy: dict[str, Any] | None = None,
        tool_schema: dict[str, Any] | None = None,
    ) -> ToolAction:
        arguments = _infer_arguments(tool_name, goal=goal, tool_schema=tool_schema)
        return cls(
            tool_name=tool_name,
            arguments=arguments,
            policy_snapshot=ToolPolicySnapshot.from_policy(policy, tool_name=tool_name),
        )

    @property
    def approval_state(self) -> str:
        return self.policy_snapshot.approval_state

    def mark_executed(self, status: str) -> ToolAction:
        return replace(self, execution_status=status)

    def to_event_payload(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "policy": self.policy_snapshot.to_dict(),
            "approval_state": self.approval_state,
            "execution_status": self.execution_status,
        }

    def result_event_payload(self, result: Any) -> dict[str, Any]:
        executed = self.mark_executed(str(getattr(result, "status", "unknown")))
        policy = getattr(result, "policy", None) or executed.policy_snapshot.to_dict()
        governance = _result_governance_payload(result, policy=policy)
        payload = {
            "tool_name": str(getattr(result, "tool_name", self.tool_name)),
            "status": executed.execution_status,
            "arguments": getattr(result, "arguments", self.arguments),
            "output": getattr(result, "output", None),
            "error": getattr(result, "error", None),
            "policy": policy,
            "approval_state": executed.approval_state,
            "execution_status": executed.execution_status,
            "governance": governance,
        }
        latency_ms = getattr(result, "latency_ms", None)
        if latency_ms is not None:
            payload["latency_ms"] = latency_ms
        return payload


@dataclass(frozen=True)
class EvidenceItem:
    """Evidence collected from a tool execution."""

    tool_name: str
    status: str
    output: Any = None
    error: str | None = None

    @classmethod
    def from_tool_result(cls, result: Any) -> EvidenceItem:
        output = getattr(result, "output", None)
        output = _truncate_output(output)
        return cls(
            tool_name=str(getattr(result, "tool_name", "unknown")),
            status=str(getattr(result, "status", "unknown")),
            output=output,
            error=getattr(result, "error", None),
        )

    def to_report_line(self) -> str:
        if self.status == "success":
            return f"{self.tool_name}: {self.output}"
        if self.status == "approval_required":
            return f"{self.tool_name}：等待人工审批后采集证据"
        if self.status == "disabled":
            return f"{self.tool_name}：工具已被策略禁用"
        return f"{self.tool_name}：工具执行失败：{self.error}"


@dataclass
class AgentRunState:
    """Mutable state accumulated during one Agent run."""

    goal: str
    hypothesis: Hypothesis
    knowledge_context: KnowledgeContext = field(default_factory=KnowledgeContext.empty)
    actions: list[ToolAction] = field(default_factory=list)
    evidence: list[EvidenceItem] = field(default_factory=list)

    @classmethod
    def from_goal(cls, goal: str) -> AgentRunState:
        return cls(goal=goal, hypothesis=Hypothesis.from_goal(goal))

    def add_action(self, action: ToolAction) -> None:
        self.actions.append(action)

    def set_knowledge_context(self, knowledge_context: KnowledgeContext) -> None:
        self.knowledge_context = knowledge_context

    def add_evidence(self, evidence: EvidenceItem) -> None:
        self.evidence.append(evidence)

    def evidence_report_lines(self) -> list[str]:
        return [item.to_report_line() for item in self.evidence]


def _result_governance_payload(result: Any, *, policy: dict[str, Any]) -> dict[str, Any]:
    if hasattr(result, "governance_payload"):
        payload = result.governance_payload()
        if isinstance(payload, dict):
            return {
                "decision": payload.get("decision") or _governance_decision_from_status(result),
                "reason": payload.get("reason"),
                "policy": payload.get("policy") or policy,
            }
    return {
        "decision": _governance_decision_from_status(result),
        "reason": getattr(result, "error", None),
        "policy": policy,
    }


def _governance_decision_from_status(result: Any) -> str:
    status = str(getattr(result, "status", "unknown"))
    if status in {"disabled", "forbidden"}:
        return "denied"
    if status == "approval_required":
        return "approval_required"
    if status == "timeout":
        return "timeout"
    return "executed"


def _truncate_output(output: Any, max_chars: int = _MAX_TOOL_OUTPUT_CHARS) -> Any:
    if output is None:
        return None
    if isinstance(output, str):
        if len(output) <= max_chars:
            return output
        return output[:max_chars] + f"\n... [truncated, total {len(output)} chars]"
    try:
        serialized = json.dumps(output, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        text = str(output)
        if len(text) <= max_chars:
            return output
        return text[:max_chars] + f"\n... [truncated, total {len(text)} chars]"
    if len(serialized) <= max_chars:
        return output
    return serialized[:max_chars] + f"\n... [truncated, total {len(serialized)} chars]"
