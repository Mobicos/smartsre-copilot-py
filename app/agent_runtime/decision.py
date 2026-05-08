"""Decision Runtime contracts and deterministic providers.

The V2 decision layer stores structured decisions and short reasoning summaries.
It intentionally does not persist private chain-of-thought.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Sequence
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

ActionType = Literal[
    "observe",
    "call_tool",
    "ask_approval",
    "recover",
    "final_report",
    "handoff",
]
EvidenceQuality = Literal["strong", "partial", "weak", "empty", "conflicting", "error"]
DecisionRunStatus = Literal[
    "running",
    "waiting_approval",
    "completed",
    "failed",
    "handoff_required",
    "cancelled",
]
Priority = Literal["P0", "P1", "P2", "P3"]


class SuccessCriteria(BaseModel):
    """A measurable condition that lets the runtime stop safely."""

    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=1)
    required: bool = True


class StopCondition(BaseModel):
    """Boundaries that prevent unbounded autonomous execution."""

    model_config = ConfigDict(extra="forbid")

    max_steps: int = Field(default=5, ge=1)
    max_minutes: float = Field(default=2.0, gt=0)
    confidence_threshold: float = Field(default=0.75, ge=0.0, le=1.0)


class AgentObservation(BaseModel):
    """A compact observation visible to decision providers."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    citations: list[dict[str, Any]] = Field(default_factory=list)


class AgentHypothesis(BaseModel):
    """A ranked diagnostic hypothesis carried through the decision loop."""

    model_config = ConfigDict(extra="forbid")

    hypothesis_id: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    priority: int = Field(default=1, ge=1)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class RuntimeBudget(BaseModel):
    """Bounded runtime budget visible to decision providers."""

    model_config = ConfigDict(extra="forbid")

    max_steps: int = Field(default=5, ge=1)
    remaining_steps: int = Field(default=5, ge=0)
    max_tool_calls: int = Field(default=5, ge=1)
    remaining_tool_calls: int = Field(default=5, ge=0)
    run_timeout_seconds: float = Field(default=120.0, gt=0)
    remaining_seconds: float | None = Field(default=None, ge=0)

    @property
    def exhausted(self) -> bool:
        return self.remaining_steps <= 0 or self.remaining_tool_calls <= 0


class AgentGoalContract(BaseModel):
    """Explicit goal, success criteria, and boundaries for one run."""

    model_config = ConfigDict(extra="forbid")

    goal: str = Field(min_length=1)
    success_criteria: list[SuccessCriteria] = Field(default_factory=list)
    stop_condition: StopCondition = Field(default_factory=StopCondition)
    priority: Priority = "P2"
    workspace_id: str | None = None
    scene_id: str | None = None
    allowed_tools: list[str] = Field(default_factory=list)
    trace_id: str | None = None
    prohibited_outputs: list[str] = Field(
        default_factory=lambda: ["private_chain_of_thought", "secrets"],
    )


class EvidenceAssessment(BaseModel):
    """A compact evidence quality record."""

    model_config = ConfigDict(extra="forbid")

    quality: EvidenceQuality
    summary: str = ""
    citations: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class RecoveryDecision(BaseModel):
    """Structured recovery or handoff guidance."""

    model_config = ConfigDict(extra="forbid")

    required: bool = False
    reason: str | None = None
    next_action: Literal["retry", "ask_approval", "handoff", "final_report"] | None = None


class AgentDecision(BaseModel):
    """Serializable decision payload emitted by the V2 runtime."""

    model_config = ConfigDict(extra="forbid")

    action_type: ActionType
    reasoning_summary: str = Field(min_length=1)
    selected_tool: str | None = None
    selected_action: str | None = None
    tool_arguments: dict[str, Any] = Field(default_factory=dict)
    expected_evidence: list[str] = Field(default_factory=list)
    evidence: EvidenceAssessment = Field(
        default_factory=lambda: EvidenceAssessment(quality="empty")
    )
    actual_evidence: EvidenceAssessment | None = None
    recovery: RecoveryDecision = Field(default_factory=RecoveryDecision)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    decision_status: DecisionRunStatus | ActionType | str | None = None
    handoff_reason: str | None = None

    @field_validator("reasoning_summary")
    @classmethod
    def _reject_private_reasoning(cls, value: str) -> str:
        lowered = value.lower()
        blocked_terms = ("chain-of-thought", "private reasoning", "hidden reasoning")
        if any(term in lowered for term in blocked_terms):
            raise ValueError("reasoning_summary must not include private reasoning")
        return value

    @model_validator(mode="after")
    def _normalize_decision_payload(self) -> AgentDecision:
        if self.actual_evidence is None:
            self.actual_evidence = self.evidence
        if self.selected_action is None:
            self.selected_action = self.action_type
        if self.decision_status is None:
            self.decision_status = self.action_type
        if self.handoff_reason is None and self.recovery.required:
            self.handoff_reason = self.recovery.reason
        return self

    def to_event_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class AgentDecisionState(BaseModel):
    """Decision state carried between graph nodes."""

    model_config = ConfigDict(extra="forbid")

    run_id: str | None = None
    status: DecisionRunStatus = "running"
    goal: AgentGoalContract
    budget: RuntimeBudget = Field(default_factory=RuntimeBudget)
    available_tools: list[str] = Field(default_factory=list)
    executed_tools: list[str] = Field(default_factory=list)
    observations: list[AgentObservation] = Field(default_factory=list)
    hypothesis_queue: list[AgentHypothesis] = Field(default_factory=list)
    evidence: list[EvidenceAssessment] = Field(default_factory=list)
    consecutive_empty_evidence: int = 0
    decisions: list[AgentDecision] = Field(default_factory=list)

    def with_decision(self, decision: AgentDecision) -> AgentDecisionState:
        status: DecisionRunStatus = self.status
        if decision.action_type == "ask_approval":
            status = "waiting_approval"
        elif decision.action_type == "final_report":
            status = "completed"
        elif decision.action_type == "handoff":
            status = "handoff_required"
        return self.model_copy(
            update={
                "status": status,
                "decisions": [*self.decisions, decision],
            }
        )


class DecisionProvider(Protocol):
    """Provider interface for deterministic or model-backed decisions."""

    def decide(self, state: AgentDecisionState) -> AgentDecision:
        """Return the next structured decision."""


class DeterministicDecisionProvider:
    """Rule-based provider used before model-backed decisioning is enabled."""

    def decide(self, state: AgentDecisionState) -> AgentDecision:
        if state.budget.exhausted:
            return AgentDecision(
                action_type="handoff",
                reasoning_summary="Runtime budget is exhausted, so the run should hand off.",
                evidence=_best_evidence(state.evidence),
                recovery=RecoveryDecision(
                    required=True,
                    reason="budget_exhausted",
                    next_action="handoff",
                ),
                confidence=0.5,
            )

        strong_evidence = next((item for item in state.evidence if item.quality == "strong"), None)
        if strong_evidence is not None:
            return AgentDecision(
                action_type="final_report",
                reasoning_summary="Strong evidence is available and can support a final report.",
                evidence=strong_evidence,
                confidence=max(strong_evidence.confidence, 0.8),
            )

        if state.consecutive_empty_evidence >= 2:
            return AgentDecision(
                action_type="recover",
                reasoning_summary="Evidence remained empty after repeated attempts.",
                evidence=EvidenceAssessment(quality="empty", summary="No usable evidence yet."),
                recovery=RecoveryDecision(
                    required=True,
                    reason="empty_evidence",
                    next_action="retry",
                ),
                confidence=0.4,
            )

        remaining_tools = [
            tool for tool in state.available_tools if tool not in state.executed_tools
        ]
        if remaining_tools:
            tool_name = remaining_tools[0]
            return AgentDecision(
                action_type="call_tool",
                selected_tool=tool_name,
                tool_arguments={"query": state.goal.goal},
                expected_evidence=[f"Evidence from {tool_name}"],
                reasoning_summary=f"Call {tool_name} to gather evidence for the goal.",
                evidence=_best_evidence(state.evidence),
                confidence=0.7,
            )

        return AgentDecision(
            action_type="handoff",
            reasoning_summary="No executable tools are available for this goal.",
            evidence=_best_evidence(state.evidence),
            recovery=RecoveryDecision(
                required=True,
                reason="no_available_tools",
                next_action="handoff",
            ),
            confidence=0.3,
        )


class QwenDecisionProvider:
    """Structured JSON provider wrapper for Qwen-compatible chat callables."""

    def __init__(self, invoke_json: Callable[[AgentDecisionState], str]) -> None:
        self._invoke_json = invoke_json

    def decide(self, state: AgentDecisionState) -> AgentDecision:
        raw = self._invoke_json(state)
        try:
            payload = _parse_strict_json(raw)
            decision = AgentDecision.model_validate(payload)
        except (ValueError, ValidationError, TypeError) as exc:
            return AgentDecision(
                action_type="recover",
                reasoning_summary="Model output was not valid structured decision JSON.",
                evidence=EvidenceAssessment(
                    quality="error",
                    summary=f"{type(exc).__name__}: {exc}",
                ),
                recovery=RecoveryDecision(
                    required=True,
                    reason="invalid_model_output",
                    next_action="retry",
                ),
                confidence=0.0,
            )

        if decision.selected_tool and decision.selected_tool not in state.available_tools:
            return AgentDecision(
                action_type="recover",
                reasoning_summary="Model selected a tool outside the available tool set.",
                evidence=EvidenceAssessment(
                    quality="error",
                    summary=f"Unknown tool: {decision.selected_tool}",
                ),
                recovery=RecoveryDecision(
                    required=True,
                    reason="unknown_tool",
                    next_action="retry",
                ),
                confidence=0.0,
            )

        if decision.confidence < 0.2:
            return decision.model_copy(
                update={
                    "action_type": "recover",
                    "recovery": RecoveryDecision(
                        required=True,
                        reason="low_confidence",
                        next_action="retry",
                    ),
                }
            )

        return decision


class LangChainQwenDecisionInvoker:
    """Call a LangChain-compatible Qwen chat model for structured decisions."""

    def __init__(self, chat_model: Any) -> None:
        self._chat_model = chat_model

    def __call__(self, state: AgentDecisionState) -> str:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are SmartSRE Decision Runtime. Return one plain JSON object only. "
                    "Do not use Markdown fences. Do not include private chain-of-thought. "
                    "Use reasoning_summary for a short audit summary."
                ),
            },
            {
                "role": "user",
                "content": _qwen_decision_prompt(state),
            },
        ]
        response = self._chat_model.invoke(messages)
        content = getattr(response, "content", response)
        if isinstance(content, list):
            parts = [
                str(item.get("text", item)) if isinstance(item, dict) else str(item)
                for item in content
            ]
            return "".join(parts)
        return str(content)


class AgentDecisionRuntime:
    """Small graph-compatible runtime skeleton for V2 decisions."""

    checkpoint_ns = "agent-v2"

    def __init__(
        self,
        *,
        provider: DecisionProvider | None = None,
        checkpoint_saver: Any | None = None,
    ) -> None:
        self._provider = provider or DeterministicDecisionProvider()
        self._checkpoint_saver = checkpoint_saver
        self._compiled_graph: Any | None = None

    def decide_once(self, state: AgentDecisionState) -> AgentDecisionState:
        decision = self._provider.decide(state)
        return state.with_decision(decision)

    def run_graph_once(self, state: AgentDecisionState) -> AgentDecisionState:
        graph = self.build_graph()
        thread_id = state.run_id or str(uuid.uuid4())
        result = graph.invoke(
            state.model_dump(mode="json"),
            config={
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": self.checkpoint_ns,
                }
            },
        )
        return AgentDecisionState.model_validate(result)

    def build_graph(self) -> Any:
        if self._compiled_graph is not None:
            return self._compiled_graph

        try:
            from langgraph.graph import END, StateGraph
        except Exception as exc:  # pragma: no cover - depends on optional import wiring
            raise RuntimeError("LangGraph is not available") from exc

        graph = StateGraph(dict)  # type: ignore[type-var]
        graph.add_node("initialize", self._graph_initialize)  # type: ignore[call-overload]
        graph.add_node("observe", self._graph_observe)  # type: ignore[call-overload]
        graph.add_node("decide", self._graph_decide)  # type: ignore[call-overload]
        graph.add_node("validate_decision", self._graph_validate_decision)  # type: ignore[call-overload]
        graph.add_node("act", self._graph_act)  # type: ignore[call-overload]
        graph.add_node("evaluate_evidence", self._graph_evaluate_evidence)  # type: ignore[call-overload]
        graph.add_node("recover", self._graph_recover)  # type: ignore[call-overload]
        graph.add_node("final_report", self._graph_final_report)  # type: ignore[call-overload]
        graph.set_entry_point("initialize")
        graph.add_edge("initialize", "observe")
        graph.add_edge("observe", "decide")
        graph.add_edge("decide", "validate_decision")
        graph.add_conditional_edges(
            "validate_decision",
            _route_decision,
            {
                "act": "act",
                "recover": "recover",
                "final_report": "final_report",
                "end": END,
            },
        )
        graph.add_edge("act", "evaluate_evidence")
        graph.add_edge("evaluate_evidence", END)
        graph.add_edge("recover", END)
        graph.add_edge("final_report", END)
        if self._checkpoint_saver is not None:
            self._compiled_graph = graph.compile(checkpointer=self._checkpoint_saver)
        else:
            self._compiled_graph = graph.compile()
        return self._compiled_graph

    def _graph_initialize(self, payload: dict[str, Any]) -> dict[str, Any]:
        state = AgentDecisionState.model_validate(payload)
        return state.model_dump(mode="json")

    def _graph_observe(self, payload: dict[str, Any]) -> dict[str, Any]:
        state = AgentDecisionState.model_validate(payload)
        observations = list(state.observations)
        if not observations:
            observations.append(
                AgentObservation(
                    source="user_goal",
                    summary=state.goal.goal,
                    confidence=1.0,
                )
            )
        if state.available_tools:
            observations.append(
                AgentObservation(
                    source="tool_catalog",
                    summary=f"{len(state.available_tools)} scene-approved tools are available.",
                    confidence=1.0,
                    citations=[{"tools": state.available_tools}],
                )
            )
        return state.model_copy(update={"observations": observations}).model_dump(mode="json")

    def _graph_decide(self, payload: dict[str, Any]) -> dict[str, Any]:
        state = AgentDecisionState.model_validate(payload)
        return self.decide_once(state).model_dump(mode="json")

    def _graph_validate_decision(self, payload: dict[str, Any]) -> dict[str, Any]:
        state = AgentDecisionState.model_validate(payload)
        if not state.decisions:
            return state.model_dump(mode="json")

        latest = state.decisions[-1]
        if latest.selected_tool and latest.selected_tool not in state.available_tools:
            decision = AgentDecision(
                action_type="recover",
                reasoning_summary="Decision selected a tool outside the scene-approved tool set.",
                evidence=EvidenceAssessment(
                    quality="error",
                    summary=f"Unknown tool: {latest.selected_tool}",
                ),
                recovery=RecoveryDecision(
                    required=True,
                    reason="unknown_tool",
                    next_action="retry",
                ),
                confidence=0.0,
            )
            return state.model_copy(
                update={"decisions": [*state.decisions[:-1], decision]}
            ).model_dump(mode="json")

        if latest.action_type == "call_tool" and not latest.selected_tool:
            decision = AgentDecision(
                action_type="recover",
                reasoning_summary="Decision requested a tool call without selecting a tool.",
                evidence=EvidenceAssessment(
                    quality="error",
                    summary="Missing selected_tool for call_tool decision.",
                ),
                recovery=RecoveryDecision(
                    required=True,
                    reason="invalid_tool_decision",
                    next_action="retry",
                ),
                confidence=0.0,
            )
            return state.model_copy(
                update={"decisions": [*state.decisions[:-1], decision]}
            ).model_dump(mode="json")
        return state.model_dump(mode="json")

    def _graph_act(self, payload: dict[str, Any]) -> dict[str, Any]:
        state = AgentDecisionState.model_validate(payload)
        if not state.decisions:
            return state.model_dump(mode="json")
        latest = state.decisions[-1]
        if latest.action_type != "call_tool" or not latest.selected_tool:
            return state.model_dump(mode="json")

        executed_tools = [*state.executed_tools, latest.selected_tool]
        budget = state.budget.model_copy(
            update={
                "remaining_steps": max(state.budget.remaining_steps - 1, 0),
                "remaining_tool_calls": max(state.budget.remaining_tool_calls - 1, 0),
            }
        )
        return state.model_copy(
            update={"executed_tools": executed_tools, "budget": budget}
        ).model_dump(mode="json")

    def _graph_evaluate_evidence(self, payload: dict[str, Any]) -> dict[str, Any]:
        state = AgentDecisionState.model_validate(payload)
        if not state.decisions:
            return state.model_dump(mode="json")
        latest = state.decisions[-1]
        if latest.action_type != "call_tool":
            return state.model_dump(mode="json")
        expected = latest.expected_evidence or ["Tool evidence is pending execution."]
        evidence = EvidenceAssessment(
            quality="weak",
            summary="; ".join(expected),
            confidence=min(latest.confidence, 0.5),
            citations=[
                {
                    "source": "decision_runtime",
                    "tool_name": latest.selected_tool,
                    "stage": "expected_evidence",
                }
            ],
        )
        return state.model_copy(update={"evidence": [*state.evidence, evidence]}).model_dump(
            mode="json"
        )

    def _graph_recover(self, payload: dict[str, Any]) -> dict[str, Any]:
        state = AgentDecisionState.model_validate(payload)
        if not state.decisions:
            return state.model_dump(mode="json")
        latest = state.decisions[-1]
        status: DecisionRunStatus = (
            "handoff_required" if latest.recovery.next_action == "handoff" else "running"
        )
        return state.model_copy(update={"status": status}).model_dump(mode="json")

    def _graph_final_report(self, payload: dict[str, Any]) -> dict[str, Any]:
        state = AgentDecisionState.model_validate(payload)
        return state.model_copy(update={"status": "completed"}).model_dump(mode="json")


def build_initial_decision_state(
    *,
    run_id: str | None,
    goal: str,
    workspace_id: str | None,
    scene_id: str | None,
    available_tools: Sequence[str],
    executed_tools: Sequence[str] | None = None,
    budget: RuntimeBudget | None = None,
    success_criteria: Sequence[str | SuccessCriteria] | None = None,
    stop_condition: StopCondition | None = None,
    priority: Priority = "P2",
) -> AgentDecisionState:
    criteria = [
        item if isinstance(item, SuccessCriteria) else SuccessCriteria(description=str(item))
        for item in success_criteria or []
    ]
    return AgentDecisionState(
        run_id=run_id,
        goal=AgentGoalContract(
            goal=goal,
            success_criteria=criteria,
            stop_condition=stop_condition or StopCondition(),
            priority=priority,
            workspace_id=workspace_id,
            scene_id=scene_id,
            allowed_tools=list(available_tools),
            trace_id=run_id,
        ),
        budget=budget or RuntimeBudget(max_tool_calls=max(len(available_tools), 1)),
        available_tools=list(available_tools),
        executed_tools=list(executed_tools or []),
        observations=[
            AgentObservation(source="user_goal", summary=goal, confidence=1.0),
        ],
        hypothesis_queue=[
            AgentHypothesis(
                hypothesis_id="hypothesis-1",
                summary="Validate logs, metrics, alerts, and recent changes for the goal.",
                priority=1,
                confidence=0.5,
            )
        ],
    )


class FinalReportContract(BaseModel):
    """Evidence-safe final report payload for UI, replay, and handoff."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1)
    verified_facts: list[str] = Field(default_factory=list)
    inferences: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    handoff_required: bool = False
    handoff_reason: str | None = None

    def to_event_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def _best_evidence(evidence: Sequence[EvidenceAssessment]) -> EvidenceAssessment:
    if not evidence:
        return EvidenceAssessment(quality="empty", summary="No evidence has been collected yet.")
    order = {"strong": 0, "partial": 1, "weak": 2, "conflicting": 3, "error": 4, "empty": 5}
    return sorted(evidence, key=lambda item: order[item.quality])[0]


def _parse_strict_json(raw: str) -> dict[str, Any]:
    stripped = raw.strip()
    if stripped.startswith("```") or stripped.endswith("```"):
        raise ValueError("Decision provider must return plain JSON without Markdown fences")
    parsed = json.loads(stripped)
    if not isinstance(parsed, dict):
        raise ValueError("Decision provider returned non-object JSON")
    return parsed


def _qwen_decision_prompt(state: AgentDecisionState) -> str:
    schema_hint = {
        "action_type": "observe|call_tool|ask_approval|recover|final_report|handoff",
        "reasoning_summary": "short audit summary, no private reasoning",
        "selected_tool": "one available tool or null",
        "tool_arguments": {"query": state.goal.goal},
        "expected_evidence": ["what the selected tool should prove"],
        "evidence": {
            "quality": "strong|partial|weak|empty|conflicting|error",
            "summary": "evidence summary",
            "citations": [],
            "confidence": 0.0,
        },
        "recovery": {
            "required": False,
            "reason": None,
            "next_action": None,
        },
        "confidence": 0.0,
    }
    payload = {
        "goal": state.goal.model_dump(mode="json"),
        "budget": state.budget.model_dump(mode="json"),
        "available_tools": state.available_tools,
        "executed_tools": state.executed_tools,
        "evidence": [item.model_dump(mode="json") for item in state.evidence],
        "required_json_shape": schema_hint,
    }
    return json.dumps(payload, ensure_ascii=False)


def _identity_graph_node(payload: dict[str, Any]) -> dict[str, Any]:
    return payload


def _route_decision(payload: dict[str, Any]) -> str:
    decisions = payload.get("decisions")
    if not isinstance(decisions, list) or not decisions:
        return "end"
    latest = decisions[-1]
    if not isinstance(latest, dict):
        return "end"
    action_type = latest.get("action_type")
    if action_type == "call_tool":
        return "act"
    if action_type == "recover":
        return "recover"
    if action_type == "final_report":
        return "final_report"
    return "end"
