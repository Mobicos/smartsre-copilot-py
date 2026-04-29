"""Typed state primitives for the Native Agent loop."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any


@dataclass(frozen=True)
class Hypothesis:
    """A diagnostic hypothesis generated from a user goal."""

    summary: str

    @classmethod
    def from_goal(cls, goal: str) -> Hypothesis:
        return cls(summary=f"围绕目标“{goal}”优先验证告警、日志、指标和近期变更证据。")


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
            return "未配置知识库上下文"
        names = ", ".join(str(item["name"]) for item in self.knowledge_bases)
        return f"已加载 {len(self.knowledge_bases)} 个知识库: {names}"

    def has_knowledge(self) -> bool:
        return bool(self.knowledge_bases)

    def to_event_payload(self) -> dict[str, Any]:
        return {
            "knowledge_bases": self.knowledge_bases,
            "summary": self.summary,
        }

    def to_report_lines(self) -> list[str]:
        return [
            f"- {item['name']} ({item['version']}): {item.get('description') or '无描述'}"
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
    ) -> ToolAction:
        lowered = tool_name.lower()
        if "log" in lowered or "search" in lowered:
            arguments = {"query": goal, "keyword": goal}
        elif "metric" in lowered or "monitor" in lowered:
            arguments = {"query": goal}
        else:
            arguments = {"query": goal}
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
        return {
            "tool_name": str(getattr(result, "tool_name", self.tool_name)),
            "status": executed.execution_status,
            "arguments": getattr(result, "arguments", self.arguments),
            "output": getattr(result, "output", None),
            "error": getattr(result, "error", None),
            "policy": executed.policy_snapshot.to_dict(),
            "approval_state": executed.approval_state,
            "execution_status": executed.execution_status,
        }


@dataclass(frozen=True)
class EvidenceItem:
    """Evidence collected from a tool execution."""

    tool_name: str
    status: str
    output: Any = None
    error: str | None = None

    @classmethod
    def from_tool_result(cls, result: Any) -> EvidenceItem:
        return cls(
            tool_name=str(getattr(result, "tool_name", "unknown")),
            status=str(getattr(result, "status", "unknown")),
            output=getattr(result, "output", None),
            error=getattr(result, "error", None),
        )

    def to_report_line(self) -> str:
        if self.status == "success":
            return f"{self.tool_name}: {self.output}"
        if self.status == "approval_required":
            return f"{self.tool_name}: 需要人工审批，V1 未执行该工具"
        if self.status == "disabled":
            return f"{self.tool_name}: 工具已禁用，未执行"
        return f"{self.tool_name}: 执行失败: {self.error}"


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
