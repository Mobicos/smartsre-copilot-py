"""Decision Runtime contracts and deterministic providers.

The V2 decision layer stores structured decisions and short reasoning summaries.
It intentionally does not persist private chain-of-thought.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Sequence
from contextlib import contextmanager, nullcontext
from typing import Any, Literal, TypedDict, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from app.agent_runtime.ports import DecisionProvider

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


class DecisionGraphPayload(TypedDict, total=False):
    """LangGraph transport payload validated at every runtime node boundary."""

    run_id: str | None
    status: DecisionRunStatus
    goal: dict[str, Any]
    budget: dict[str, Any]
    available_tools: list[str]
    executed_tools: list[str]
    observations: list[dict[str, Any]]
    hypothesis_queue: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    consecutive_empty_evidence: int
    decisions: list[dict[str, Any]]


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


class DeterministicDecisionProvider:
    """Rule-based provider used before model-backed decisioning is enabled."""

    provider_name = "deterministic"

    def get_token_usage(self) -> dict[str, Any]:
        return {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total": 0,
            "source": "deterministic_zero",
        }

    def get_cost_estimate(self) -> dict[str, Any]:
        return {
            "currency": "USD",
            "total_cost": 0.0,
            "source": "deterministic_zero",
        }

    def decide(self, state: AgentDecisionState) -> AgentDecision:
        if state.budget.exhausted:
            return AgentDecision(
                action_type="handoff",
                reasoning_summary="运行时预算已耗尽，应进行人工交接。",
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
                reasoning_summary="已有充分证据支持生成最终报告。",
                evidence=strong_evidence,
                confidence=max(strong_evidence.confidence, 0.8),
            )

        if state.consecutive_empty_evidence >= 2:
            return AgentDecision(
                action_type="recover",
                reasoning_summary="多次尝试后证据仍为空。",
                evidence=EvidenceAssessment(quality="empty", summary="尚无可用证据。"),
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
                expected_evidence=[f"来自 {tool_name} 的证据"],
                reasoning_summary=f"调用 {tool_name} 采集与目标相关的证据。",
                evidence=_best_evidence(state.evidence),
                confidence=0.7,
            )

        return AgentDecision(
            action_type="handoff",
            reasoning_summary="当前目标没有可用的可执行工具。",
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

    provider_name = "qwen"

    def __init__(self, invoke_json: Callable[[AgentDecisionState], str]) -> None:
        self._invoke_json = invoke_json

    def get_token_usage(self) -> dict[str, Any]:
        if hasattr(self._invoke_json, "get_token_usage"):
            usage = self._invoke_json.get_token_usage()
            if isinstance(usage, dict):
                return usage
        return {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total": 0,
            "source": "provider_usage_unavailable",
        }

    def get_cost_estimate(self) -> dict[str, Any]:
        if hasattr(self._invoke_json, "get_cost_estimate"):
            cost = self._invoke_json.get_cost_estimate()
            if isinstance(cost, dict):
                return cost
        return {
            "currency": "USD",
            "total_cost": 0.0,
            "source": "provider_usage_unavailable",
        }

    def decide(self, state: AgentDecisionState) -> AgentDecision:
        raw = self._invoke_json(state)
        try:
            payload = _parse_strict_json(raw)
            decision = AgentDecision.model_validate(payload)
        except (ValueError, ValidationError, TypeError) as exc:
            return AgentDecision(
                action_type="recover",
                reasoning_summary="模型输出不是有效的结构化决策 JSON。",
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
                reasoning_summary="模型选择了可用工具集之外的工具。",
                evidence=EvidenceAssessment(
                    quality="error",
                    summary=f"未知工具：{decision.selected_tool}",
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
        self._last_token_usage: dict[str, Any] = _unavailable_token_usage()

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
        self._last_token_usage = _extract_response_token_usage(response)
        content = getattr(response, "content", response)
        if isinstance(content, list):
            parts = [
                str(item.get("text", item)) if isinstance(item, dict) else str(item)
                for item in content
            ]
            return "".join(parts)
        return str(content)

    def get_token_usage(self) -> dict[str, Any]:
        return self._last_token_usage

    def get_cost_estimate(self) -> dict[str, Any]:
        token_total = int(self._last_token_usage.get("total") or 0)
        if token_total <= 0:
            return {
                "currency": "USD",
                "total_cost": 0.0,
                "source": "provider_usage_unavailable",
            }
        return {
            "currency": "USD",
            "total_cost": round(token_total * 0.000002, 6),
            "source": "heuristic_from_provider_tokens",
            "components": {
                "tokens": token_total,
            },
        }


class DecisionProviderFactory:
    """Create decision providers from runtime settings."""

    def __init__(
        self,
        settings: Any,
        *,
        chat_model_factory: Callable[[str], Any] | None = None,
    ) -> None:
        self._settings = settings
        self._chat_model_factory = chat_model_factory

    def create_provider(self, provider_name: str | None = None) -> DecisionProvider:
        selected = (provider_name or self._settings.agent_decision_provider).strip().lower()
        if selected == "qwen":
            if self._chat_model_factory is None:
                raise ValueError("qwen decision provider requires chat_model_factory")
            return QwenDecisionProvider(
                LangChainQwenDecisionInvoker(
                    self._chat_model_factory(self._settings.dashscope_model),
                )
            )
        return DeterministicDecisionProvider()

    def create_runtime(self, *, checkpoint_saver: Any | None = None) -> AgentDecisionRuntime:
        selected = self._settings.agent_decision_provider.strip().lower()
        provider = self.create_provider(selected)
        fallback_provider = DeterministicDecisionProvider() if selected == "qwen" else None
        return AgentDecisionRuntime(
            provider=provider,
            fallback_provider=fallback_provider,
            checkpoint_saver=checkpoint_saver,
        )


class AgentDecisionRuntime:
    """Small graph-compatible runtime skeleton for V2 decisions."""

    checkpoint_ns = "agent-v2"

    def __init__(
        self,
        *,
        provider: DecisionProvider | None = None,
        fallback_provider: DecisionProvider | None = None,
        checkpoint_saver: Any | None = None,
    ) -> None:
        self._provider = provider or DeterministicDecisionProvider()
        self._fallback_provider = fallback_provider
        self._checkpoint_saver = checkpoint_saver
        self._compiled_graph: Any | None = None
        self._provider_fallback_events: list[dict[str, Any]] = []
        self._last_token_usage: dict[str, Any] = _unavailable_token_usage()
        self._last_cost_estimate: dict[str, Any] = _unavailable_cost_estimate()

    @property
    def provider(self) -> DecisionProvider:
        """Return the active decision provider for runtime adapters."""

        return self._provider

    def decide_once(self, state: AgentDecisionState) -> AgentDecisionState:
        try:
            decision = self._provider.decide(state)
            self._record_provider_metrics(self._provider)
        except Exception as exc:
            if self._fallback_provider is None:
                raise
            decision = self._fallback_provider.decide(state)
            self._record_provider_metrics(self._fallback_provider)
            self._provider_fallback_events.append(
                {
                    "from_provider": _provider_name(self._provider),
                    "to_provider": _provider_name(self._fallback_provider),
                    "reason": type(exc).__name__,
                    "error_message": str(exc),
                }
            )
        return state.with_decision(decision)

    def get_token_usage(self) -> dict[str, Any]:
        return dict(self._last_token_usage)

    def get_cost_estimate(self) -> dict[str, Any]:
        return dict(self._last_cost_estimate)

    def _record_provider_metrics(self, provider: DecisionProvider) -> None:
        self._last_token_usage = provider.get_token_usage()
        self._last_cost_estimate = provider.get_cost_estimate()

    def consume_provider_fallback_events(self) -> list[dict[str, Any]]:
        events = list(self._provider_fallback_events)
        self._provider_fallback_events.clear()
        return events

    def run_graph_once(self, state: AgentDecisionState) -> AgentDecisionState:
        graph = self.build_graph()
        thread_id = state.run_id or str(uuid.uuid4())
        with _optional_span("agent.decision_graph", {"agent.run_id": thread_id}):
            result = graph.invoke(
                _state_to_graph_payload(state),
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

        graph = StateGraph(DecisionGraphPayload)
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

    def _graph_initialize(self, payload: DecisionGraphPayload) -> DecisionGraphPayload:
        state = _state_from_graph_payload(payload)
        return _state_to_graph_payload(state)

    def _graph_observe(self, payload: DecisionGraphPayload) -> DecisionGraphPayload:
        state = _state_from_graph_payload(payload)
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
                    summary=f"可用场景工具 {len(state.available_tools)} 个。",
                    confidence=1.0,
                    citations=[{"tools": state.available_tools}],
                )
            )
        return _state_to_graph_payload(state.model_copy(update={"observations": observations}))

    def _graph_decide(self, payload: DecisionGraphPayload) -> DecisionGraphPayload:
        state = _state_from_graph_payload(payload)
        return _state_to_graph_payload(self.decide_once(state))

    def _graph_validate_decision(self, payload: DecisionGraphPayload) -> DecisionGraphPayload:
        state = _state_from_graph_payload(payload)
        if not state.decisions:
            return _state_to_graph_payload(state)

        latest = state.decisions[-1]
        if latest.selected_tool and latest.selected_tool not in state.available_tools:
            decision = AgentDecision(
                action_type="recover",
                reasoning_summary="决策选择了场景允许工具集之外的工具。",
                evidence=EvidenceAssessment(
                    quality="error",
                    summary=f"未知工具：{latest.selected_tool}",
                ),
                recovery=RecoveryDecision(
                    required=True,
                    reason="unknown_tool",
                    next_action="retry",
                ),
                confidence=0.0,
            )
            return _state_to_graph_payload(
                state.model_copy(update={"decisions": [*state.decisions[:-1], decision]})
            )

        if latest.action_type == "call_tool" and not latest.selected_tool:
            decision = AgentDecision(
                action_type="recover",
                reasoning_summary="决策请求调用工具但未选择具体工具。",
                evidence=EvidenceAssessment(
                    quality="error",
                    summary="call_tool 决策缺少 selected_tool。",
                ),
                recovery=RecoveryDecision(
                    required=True,
                    reason="invalid_tool_decision",
                    next_action="retry",
                ),
                confidence=0.0,
            )
            return _state_to_graph_payload(
                state.model_copy(update={"decisions": [*state.decisions[:-1], decision]})
            )
        return _state_to_graph_payload(state)

    def _graph_act(self, payload: DecisionGraphPayload) -> DecisionGraphPayload:
        state = _state_from_graph_payload(payload)
        if not state.decisions:
            return _state_to_graph_payload(state)
        latest = state.decisions[-1]
        if latest.action_type != "call_tool" or not latest.selected_tool:
            return _state_to_graph_payload(state)

        executed_tools = [*state.executed_tools, latest.selected_tool]
        budget = state.budget.model_copy(
            update={
                "remaining_steps": max(state.budget.remaining_steps - 1, 0),
                "remaining_tool_calls": max(state.budget.remaining_tool_calls - 1, 0),
            }
        )
        return _state_to_graph_payload(
            state.model_copy(update={"executed_tools": executed_tools, "budget": budget})
        )

    def _graph_evaluate_evidence(self, payload: DecisionGraphPayload) -> DecisionGraphPayload:
        state = _state_from_graph_payload(payload)
        if not state.decisions:
            return _state_to_graph_payload(state)
        latest = state.decisions[-1]
        if latest.action_type != "call_tool":
            return _state_to_graph_payload(state)
        expected = latest.expected_evidence or ["工具证据等待执行。"]
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
        return _state_to_graph_payload(
            state.model_copy(update={"evidence": [*state.evidence, evidence]})
        )

    def _graph_recover(self, payload: DecisionGraphPayload) -> DecisionGraphPayload:
        state = _state_from_graph_payload(payload)
        if not state.decisions:
            return _state_to_graph_payload(state)
        latest = state.decisions[-1]
        status: DecisionRunStatus = (
            "handoff_required" if latest.recovery.next_action == "handoff" else "running"
        )
        return _state_to_graph_payload(state.model_copy(update={"status": status}))

    def _graph_final_report(self, payload: DecisionGraphPayload) -> DecisionGraphPayload:
        state = _state_from_graph_payload(payload)
        return _state_to_graph_payload(state.model_copy(update={"status": "completed"}))


def _state_to_graph_payload(state: AgentDecisionState) -> DecisionGraphPayload:
    return cast(DecisionGraphPayload, state.model_dump(mode="json"))


def _state_from_graph_payload(payload: DecisionGraphPayload | dict[str, Any]) -> AgentDecisionState:
    return AgentDecisionState.model_validate(payload)


def _provider_name(provider: DecisionProvider) -> str:
    value = getattr(provider, "provider_name", None)
    if isinstance(value, str) and value:
        return value
    return provider.__class__.__name__


@contextmanager
def _optional_span(name: str, attributes: dict[str, Any]):
    try:
        from opentelemetry import trace
    except Exception:
        with nullcontext():
            yield
        return

    with trace.get_tracer("smartsre.agent_runtime.decision").start_as_current_span(name) as span:
        for key, value in attributes.items():
            span.set_attribute(key, value)
        yield


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
                summary="验证目标相关的日志、指标、告警和近期变更。",
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
        return EvidenceAssessment(quality="empty", summary="尚未采集到任何证据。")
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


def _unavailable_token_usage() -> dict[str, Any]:
    return {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total": 0,
        "source": "provider_usage_unavailable",
    }


def _unavailable_cost_estimate() -> dict[str, Any]:
    return {
        "currency": "USD",
        "total_cost": 0.0,
        "source": "provider_usage_unavailable",
    }


def _extract_response_token_usage(response: Any) -> dict[str, Any]:
    usage = getattr(response, "usage_metadata", None)
    if not isinstance(usage, dict):
        metadata = getattr(response, "response_metadata", None)
        if isinstance(metadata, dict):
            usage = metadata.get("token_usage")
    if not isinstance(usage, dict):
        return _unavailable_token_usage()

    prompt_tokens = _usage_int(usage, "prompt_tokens", "input_tokens")
    completion_tokens = _usage_int(usage, "completion_tokens", "output_tokens")
    total = _usage_int(usage, "total", "total_tokens")
    if total <= 0:
        total = prompt_tokens + completion_tokens
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total": total,
        "source": "provider_usage",
    }


def _usage_int(usage: dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = usage.get(key)
        if value is None:
            continue
        try:
            return max(int(value), 0)
        except (TypeError, ValueError):
            return 0
    return 0


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
