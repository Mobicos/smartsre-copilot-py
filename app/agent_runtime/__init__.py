"""Native Agent runtime platform package with lazy public exports."""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS = {
    "AgentRuntime": "app.agent_runtime.runtime",
    "AgentDecision": "app.agent_runtime.decision",
    "AgentDecisionRuntime": "app.agent_runtime.decision",
    "AgentDecisionState": "app.agent_runtime.decision",
    "AgentGoalContract": "app.agent_runtime.decision",
    "AgentHypothesis": "app.agent_runtime.decision",
    "AgentObservation": "app.agent_runtime.decision",
    "DeterministicDecisionProvider": "app.agent_runtime.decision",
    "EvidenceAssessment": "app.agent_runtime.decision",
    "FinalReportContract": "app.agent_runtime.decision",
    "LangChainQwenDecisionInvoker": "app.agent_runtime.decision",
    "Priority": "app.agent_runtime.decision",
    "QwenDecisionProvider": "app.agent_runtime.decision",
    "RecoveryDecision": "app.agent_runtime.decision",
    "RuntimeBudget": "app.agent_runtime.decision",
    "StopCondition": "app.agent_runtime.decision",
    "SuccessCriteria": "app.agent_runtime.decision",
    "build_initial_decision_state": "app.agent_runtime.decision",
    "AgentRuntimeEvent": "app.agent_runtime.events",
    "AgentRunStore": "app.agent_runtime.ports",
    "SceneStore": "app.agent_runtime.ports",
    "AgentRunState": "app.agent_runtime.state",
    "EvidenceItem": "app.agent_runtime.state",
    "Hypothesis": "app.agent_runtime.state",
    "KnowledgeContext": "app.agent_runtime.state",
    "ToolAction": "app.agent_runtime.state",
    "ToolPolicySnapshot": "app.agent_runtime.state",
    "AgentPlanner": "app.agent_runtime.planner",
    "AgentToolExecutor": "app.agent_runtime.executor",
    "KnowledgeContextProvider": "app.agent_runtime.context",
    "ReportSynthesizer": "app.agent_runtime.synthesizer",
    "ToolPolicyGate": "app.agent_runtime.policy",
    "ToolCatalog": "app.agent_runtime.tool_catalog",
    "ToolSchema": "app.agent_runtime.tool_catalog",
    "ToolExecutionResult": "app.agent_runtime.tool_executor",
    "ToolExecutor": "app.agent_runtime.tool_executor",
    "ToolPolicyRepositoryAdapter": "app.agent_runtime.tool_executor",
    "ToolPolicyStore": "app.agent_runtime.ports",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    try:
        module_name = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value
