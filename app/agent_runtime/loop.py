"""Bounded ReAct loop primitives for the Native Agent runtime."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from time import monotonic
from typing import Any, Protocol

from app.agent_runtime.decision import (
    AgentDecision,
    AgentDecisionState,
    DecisionProvider,
    DeterministicDecisionProvider,
    EvidenceAssessment,
    RecoveryDecision,
    RuntimeBudget,
)
from app.agent_runtime.evidence import EvidenceAssessor
from app.agent_runtime.recovery import RecoveryPlan
from app.agent_runtime.state import EvidenceItem
from app.agent_runtime.trace_collector import TraceCollector, TraceSpan

ToolExecutorCallback = Callable[[AgentDecision], Any]

TerminalAction = {"ask_approval", "final_report", "handoff"}


@dataclass(frozen=True)
class LoopBudget:
    """Hard execution boundaries for one loop invocation."""

    max_steps: int = 5
    max_time_seconds: float = 120.0
    max_tokens: int | None = None

    def normalize(self) -> LoopBudget:
        return LoopBudget(
            max_steps=max(self.max_steps, 1),
            max_time_seconds=max(self.max_time_seconds, 0.001),
            max_tokens=self.max_tokens if self.max_tokens is None else max(self.max_tokens, 0),
        )


@dataclass(frozen=True)
class LoopStep:
    """One structured decision step produced by the bounded loop."""

    step_index: int
    decision: AgentDecision
    token_usage: int = 0
    token_usage_detail: dict[str, Any] = field(default_factory=dict)
    cost_estimate: dict[str, Any] = field(default_factory=dict)
    tool_result: Any = field(default=None, repr=False)

    @property
    def metrics(self) -> dict[str, Any]:
        return {
            "step_index": self.step_index,
            "token_usage": self.token_usage_detail,
            "cost_estimate": self.cost_estimate,
        }


@dataclass(frozen=True)
class LoopResult:
    """Outcome of a bounded ReAct loop execution."""

    state: AgentDecisionState
    steps: list[LoopStep] = field(default_factory=list)
    evidence_items: list[EvidenceItem] = field(default_factory=list)
    status: str = "running"
    termination_reason: str = "not_terminated"
    token_usage: int = 0

    @property
    def step_count(self) -> int:
        return len(self.steps)

    @property
    def step_metrics(self) -> list[dict[str, Any]]:
        return [step.metrics for step in self.steps]


class LoopTraceCollector(Protocol):
    """Tracing boundary used by the loop without depending on OTel directly."""

    @contextmanager
    def span(
        self,
        name: str,
        attributes: dict[str, Any] | None = None,
    ) -> Iterator[TraceSpan]:
        """Open an optional tracing span."""


class LoopRecoveryManager(Protocol):
    """Recovery strategy boundary used by the bounded loop."""

    def choose_strategy(
        self,
        *,
        evidence_quality: str,
        consecutive_failures: int = 0,
        tool_available: bool = True,
    ) -> RecoveryPlan:
        """Choose the next bounded recovery action."""


class BoundedReActLoop:
    """Run structured observe/decide/act steps under strict budget boundaries.

    The loop calls the decision provider, executes tools via the optional
    ``tool_executor`` callback, assesses evidence, and repeats until a
    terminal action or budget exhaustion.
    """

    def __init__(
        self,
        provider: DecisionProvider | None = None,
        fallback_provider: DecisionProvider | None = None,
        token_estimator: Callable[[AgentDecision], int] | None = None,
        trace_collector: LoopTraceCollector | None = None,
        recovery_manager: LoopRecoveryManager | None = None,
        tool_executor: ToolExecutorCallback | None = None,
        evidence_assessor: EvidenceAssessor | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._provider = provider or DeterministicDecisionProvider()
        self._fallback_provider = fallback_provider
        self._token_estimator = token_estimator
        self._trace_collector = trace_collector or TraceCollector()
        self._recovery_manager = recovery_manager
        self._tool_executor = tool_executor
        self._evidence_assessor = evidence_assessor
        self._clock = clock or monotonic
        self._provider_fallback_events: list[dict[str, str]] = []
        self._last_decision_provider: DecisionProvider = self._provider

    def consume_provider_fallback_events(self) -> list[dict[str, str]]:
        """Return and clear provider fallback events for replay/SSE adapters."""

        events = list(self._provider_fallback_events)
        self._provider_fallback_events.clear()
        return events

    def run(self, state: AgentDecisionState, budget: LoopBudget | None = None) -> LoopResult:
        budget = (budget or _budget_from_state(state)).normalize()
        deadline = self._clock() + budget.max_time_seconds
        current_state = state
        steps: list[LoopStep] = []
        evidence_items: list[EvidenceItem] = []
        token_usage = 0

        for step_index in range(budget.max_steps):
            if self._clock() >= deadline:
                return self._result(
                    current_state, steps, evidence_items, token_usage,
                    "max_time_seconds_reached",
                )

            current_state = _state_with_remaining_budget(
                current_state,
                budget=budget,
                remaining_steps=budget.max_steps - step_index,
            )
            tool_result: Any = None
            with self._trace_collector.span(
                "agent.loop_step",
                {
                    "agent.run_id": str(current_state.run_id or ""),
                    "agent.step_index": step_index,
                    "agent.max_steps": budget.max_steps,
                },
            ) as span:
                decision = self._decide(current_state, span)
                span.set_attribute("agent.action_type", decision.action_type)
                if decision.selected_tool:
                    span.set_attribute("agent.tool_name", decision.selected_tool)
                span.set_attribute("agent.evidence_quality", decision.evidence.quality)

                # --- act phase: execute tool if requested ---
                if (
                    decision.action_type == "action"
                    and decision.selected_tool
                    and self._tool_executor is not None
                ):
                    tool_result = self._tool_executor(decision)
                    evidence_item = EvidenceItem.from_tool_result(tool_result)
                    evidence_items.append(evidence_item)
                    assessment = self._assess(decision, evidence_item)
                    current_state = _add_tool_evidence(
                        current_state, decision, assessment, evidence_item,
                    )
                    span.set_attribute("agent.evidence_quality", assessment.quality)
                    if assessment.confidence > 0:
                        span.set_attribute("agent.evidence_confidence", assessment.confidence)

                    # approval_required → pause loop, let runtime handle
                    if getattr(tool_result, "status", "") == "approval_required":
                        steps.append(self._make_step(
                            step_index, decision, tool_result=tool_result,
                        ))
                        return self._result(
                            current_state, steps, evidence_items, token_usage,
                            "approval_required",
                        )

                token_usage_detail = _step_token_usage(
                    provider=self._last_decision_provider,
                    decision=decision,
                    token_estimator=self._token_estimator,
                )
                cost_estimate = _step_cost_estimate(self._last_decision_provider)
                step_tokens = _token_total(token_usage_detail)
                span.set_attribute("agent.token_usage", step_tokens)
                span.set_attribute("agent.cost_estimate", _cost_total(cost_estimate))
            token_usage += step_tokens

            if budget.max_tokens is not None and token_usage > budget.max_tokens:
                return self._result(
                    current_state, steps, evidence_items, token_usage,
                    "max_tokens_reached",
                )

            current_state = current_state.with_decision(decision)
            steps.append(self._make_step(
                step_index, decision, tool_result=tool_result,
                token_usage=step_tokens,
                token_usage_detail=token_usage_detail,
                cost_estimate=cost_estimate,
            ))

            if decision.action_type in TerminalAction:
                return self._result(
                    current_state, steps, evidence_items, token_usage,
                    decision.action_type,
                )

        return self._result(
            current_state, steps, evidence_items, token_usage,
            "max_steps_reached",
        )

    # -- helpers ---------------------------------------------------------------

    def _assess(
        self, decision: AgentDecision, evidence_item: EvidenceItem,
    ) -> EvidenceAssessment:
        """Assess tool evidence, preferring the injected assessor."""
        if self._evidence_assessor is not None:
            return self._evidence_assessor.assess(evidence_item)
        return decision.evidence

    @staticmethod
    def _make_step(
        step_index: int,
        decision: AgentDecision,
        *,
        tool_result: Any = None,
        token_usage: int = 0,
        token_usage_detail: dict[str, Any] | None = None,
        cost_estimate: dict[str, Any] | None = None,
    ) -> LoopStep:
        return LoopStep(
            step_index=step_index,
            decision=decision,
            token_usage=token_usage,
            token_usage_detail=token_usage_detail or {},
            cost_estimate=cost_estimate or {},
            tool_result=tool_result,
        )

    @staticmethod
    def _result(
        state: AgentDecisionState,
        steps: list[LoopStep],
        evidence_items: list[EvidenceItem],
        token_usage: int,
        termination_reason: str,
    ) -> LoopResult:
        return LoopResult(
            state=state,
            steps=steps,
            evidence_items=evidence_items,
            status=state.status,
            termination_reason=termination_reason,
            token_usage=token_usage,
        )

    def _decide_with_fallback(
        self,
        state: AgentDecisionState,
        span: TraceSpan,
    ) -> AgentDecision:
        try:
            self._last_decision_provider = self._provider
            return self._provider.decide(state)
        except Exception as exc:
            if self._fallback_provider is None:
                raise

            event = {
                "from_provider": _provider_name(self._provider),
                "to_provider": _provider_name(self._fallback_provider),
                "reason": exc.__class__.__name__,
                "error_message": str(exc),
            }
            self._provider_fallback_events.append(event)
            span.set_attribute("agent.provider_fallback", True)
            span.set_attribute("agent.provider_fallback.from", event["from_provider"])
            span.set_attribute("agent.provider_fallback.to", event["to_provider"])
            span.set_attribute("agent.provider_fallback.reason", event["reason"])
            self._last_decision_provider = self._fallback_provider
            return self._fallback_provider.decide(state)

    def _decide(self, state: AgentDecisionState, span: TraceSpan) -> AgentDecision:
        recovery_decision = self._recover_if_required(state)
        if recovery_decision is not None:
            self._last_decision_provider = self._provider
            span.set_attribute(
                "agent.recovery_action", recovery_decision.recovery.next_action or ""
            )
            span.set_attribute("agent.recovery_reason", recovery_decision.recovery.reason or "")
            return recovery_decision
        return self._decide_with_fallback(state, span)

    def _recover_if_required(self, state: AgentDecisionState) -> AgentDecision | None:
        if self._recovery_manager is None or not _requires_recovery(state):
            return None

        evidence = _latest_evidence(state)
        plan = self._recovery_manager.choose_strategy(
            evidence_quality=evidence.quality,
            consecutive_failures=state.consecutive_empty_evidence,
            tool_available=_has_remaining_tool(state),
        )
        if plan.action == "continue":
            return None
        return _decision_from_recovery_plan(plan, evidence)


def _budget_from_state(state: AgentDecisionState) -> LoopBudget:
    return LoopBudget(
        max_steps=state.budget.max_steps,
        max_time_seconds=state.budget.run_timeout_seconds,
    )


def _state_with_remaining_budget(
    state: AgentDecisionState,
    *,
    budget: LoopBudget,
    remaining_steps: int,
) -> AgentDecisionState:
    runtime_budget = RuntimeBudget(
        max_steps=budget.max_steps,
        remaining_steps=remaining_steps,
        max_tool_calls=state.budget.max_tool_calls,
        remaining_tool_calls=state.budget.remaining_tool_calls,
        run_timeout_seconds=budget.max_time_seconds,
        remaining_seconds=budget.max_time_seconds,
    )
    return state.model_copy(update={"budget": runtime_budget})


def _requires_recovery(state: AgentDecisionState) -> bool:
    if state.consecutive_empty_evidence > 0:
        return True
    if not state.evidence:
        return False
    return _latest_evidence(state).quality != "strong"


def _latest_evidence(state: AgentDecisionState) -> EvidenceAssessment:
    if not state.evidence:
        return EvidenceAssessment(quality="empty", summary="尚未采集到任何证据。")
    return state.evidence[-1]


def _has_remaining_tool(state: AgentDecisionState) -> bool:
    executed = set(state.executed_tools)
    return any(tool not in executed for tool in state.available_tools)


def _decision_from_recovery_plan(
    plan: RecoveryPlan,
    evidence: EvidenceAssessment,
) -> AgentDecision:
    if plan.handoff_required or plan.action == "handoff":
        return AgentDecision(
            action_type="handoff",
            reasoning_summary="证据不足或存在冲突，当前运行需要人工接手。",
            evidence=evidence,
            recovery=RecoveryDecision(
                required=True,
                reason=plan.reason,
                next_action="handoff",
            ),
            confidence=0.3,
        )
    if plan.action == "downgrade_report":
        return AgentDecision(
            action_type="final_report",
            reasoning_summary="证据不足以确认根因，只能生成降级诊断报告。",
            evidence=evidence,
            recovery=RecoveryDecision(
                required=True,
                reason=plan.reason,
                next_action="final_report",
            ),
            confidence=max(min(evidence.confidence, 0.5), 0.2),
        )
    return AgentDecision(
        action_type="recover",
        reasoning_summary="当前证据不足，需要先执行受控恢复策略。",
        evidence=evidence,
        recovery=RecoveryDecision(
            required=True,
            reason=plan.reason,
            next_action="retry",
        ),
        confidence=max(min(evidence.confidence, 0.4), 0.2),
    )


def _provider_name(provider: DecisionProvider) -> str:
    return str(getattr(provider, "provider_name", provider.__class__.__name__))


def _step_token_usage(
    *,
    provider: DecisionProvider,
    decision: AgentDecision,
    token_estimator: Callable[[AgentDecision], int] | None,
) -> dict[str, Any]:
    if token_estimator is not None:
        total = max(int(token_estimator(decision)), 0)
        return {
            "prompt_tokens": 0,
            "completion_tokens": total,
            "total": total,
            "source": "loop_estimator",
        }
    get_token_usage = getattr(provider, "get_token_usage", None)
    if not callable(get_token_usage):
        return _empty_token_usage()
    usage = get_token_usage()
    if not isinstance(usage, dict):
        return _empty_token_usage()
    total = _int_value(usage.get("total"))
    prompt_tokens = _int_value(usage.get("prompt_tokens"))
    completion_tokens = _int_value(usage.get("completion_tokens"))
    if total == 0:
        total = prompt_tokens + completion_tokens
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total": total,
        "source": str(usage.get("source") or "provider_usage"),
    }


def _step_cost_estimate(provider: DecisionProvider) -> dict[str, Any]:
    get_cost_estimate = getattr(provider, "get_cost_estimate", None)
    if not callable(get_cost_estimate):
        return _empty_cost_estimate()
    estimate = get_cost_estimate()
    if not isinstance(estimate, dict):
        return _empty_cost_estimate()
    return {
        "currency": str(estimate.get("currency") or "USD"),
        "total_cost": _float_value(estimate.get("total_cost")),
        "source": str(estimate.get("source") or "provider_usage"),
    }


def _token_total(token_usage: dict[str, Any]) -> int:
    return _int_value(token_usage.get("total"))


def _cost_total(cost_estimate: dict[str, Any]) -> float:
    return _float_value(cost_estimate.get("total_cost"))


def _empty_token_usage() -> dict[str, Any]:
    return {"prompt_tokens": 0, "completion_tokens": 0, "total": 0, "source": "unavailable"}


def _empty_cost_estimate() -> dict[str, Any]:
    return {"currency": "USD", "total_cost": 0.0, "source": "unavailable"}


def _int_value(value: Any) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def _float_value(value: Any) -> float:
    try:
        return max(float(value or 0.0), 0.0)
    except (TypeError, ValueError):
        return 0.0


def _add_tool_evidence(
    state: AgentDecisionState,
    decision: AgentDecision,
    assessment: EvidenceAssessment,
    evidence_item: EvidenceItem,
) -> AgentDecisionState:
    """Return a new state with tool evidence and assessment appended."""
    executed = list(state.executed_tools)
    if decision.selected_tool and decision.selected_tool not in executed:
        executed.append(decision.selected_tool)

    evidence = list(state.evidence)
    evidence.append(assessment)

    consecutive_empty = state.consecutive_empty_evidence
    if assessment.quality == "empty":
        consecutive_empty += 1
    else:
        consecutive_empty = 0

    return state.model_copy(update={
        "executed_tools": executed,
        "evidence": evidence,
        "consecutive_empty_evidence": consecutive_empty,
    })
