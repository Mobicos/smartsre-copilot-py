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
    RuntimeBudget,
)
from app.agent_runtime.trace_collector import TraceCollector, TraceSpan

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


@dataclass(frozen=True)
class LoopResult:
    """Outcome of a bounded ReAct loop execution."""

    state: AgentDecisionState
    steps: list[LoopStep] = field(default_factory=list)
    status: str = "running"
    termination_reason: str = "not_terminated"
    token_usage: int = 0

    @property
    def step_count(self) -> int:
        return len(self.steps)


class LoopTraceCollector(Protocol):
    """Tracing boundary used by the loop without depending on OTel directly."""

    @contextmanager
    def span(
        self,
        name: str,
        attributes: dict[str, Any] | None = None,
    ) -> Iterator[TraceSpan]:
        """Open an optional tracing span."""


class BoundedReActLoop:
    """Run structured observe/decide steps under strict budget boundaries.

    This first extraction intentionally keeps tool execution outside the loop.
    It gives the runtime a stable seam for the next phases while preserving the
    existing public AgentRuntime API.
    """

    def __init__(
        self,
        provider: DecisionProvider | None = None,
        fallback_provider: DecisionProvider | None = None,
        token_estimator: Callable[[AgentDecision], int] | None = None,
        trace_collector: LoopTraceCollector | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._provider = provider or DeterministicDecisionProvider()
        self._fallback_provider = fallback_provider
        self._token_estimator = token_estimator or _zero_token_estimator
        self._trace_collector = trace_collector or TraceCollector()
        self._clock = clock or monotonic
        self._provider_fallback_events: list[dict[str, str]] = []

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
        token_usage = 0

        for step_index in range(budget.max_steps):
            if self._clock() >= deadline:
                return LoopResult(
                    state=current_state,
                    steps=steps,
                    status=current_state.status,
                    termination_reason="max_time_seconds_reached",
                    token_usage=token_usage,
                )

            current_state = _state_with_remaining_budget(
                current_state,
                budget=budget,
                remaining_steps=budget.max_steps - step_index,
            )
            with self._trace_collector.span(
                "agent.loop_step",
                {
                    "agent.run_id": str(current_state.run_id or ""),
                    "agent.step_index": step_index,
                    "agent.max_steps": budget.max_steps,
                },
            ) as span:
                decision = self._decide_with_fallback(current_state, span)
                span.set_attribute("agent.action_type", decision.action_type)
                if decision.selected_tool:
                    span.set_attribute("agent.tool_name", decision.selected_tool)
                span.set_attribute("agent.evidence_quality", decision.evidence.quality)
                step_tokens = self._token_estimator(decision)
                span.set_attribute("agent.token_usage", step_tokens)
                span.set_attribute("agent.cost_estimate", 0.0)
            token_usage += step_tokens

            if budget.max_tokens is not None and token_usage > budget.max_tokens:
                return LoopResult(
                    state=current_state,
                    steps=steps,
                    status=current_state.status,
                    termination_reason="max_tokens_reached",
                    token_usage=token_usage,
                )

            current_state = current_state.with_decision(decision)
            steps.append(
                LoopStep(
                    step_index=step_index,
                    decision=decision,
                    token_usage=step_tokens,
                )
            )

            if decision.action_type in TerminalAction:
                return LoopResult(
                    state=current_state,
                    steps=steps,
                    status=current_state.status,
                    termination_reason=decision.action_type,
                    token_usage=token_usage,
                )

        return LoopResult(
            state=current_state,
            steps=steps,
            status=current_state.status,
            termination_reason="max_steps_reached",
            token_usage=token_usage,
        )

    def _decide_with_fallback(
        self,
        state: AgentDecisionState,
        span: TraceSpan,
    ) -> AgentDecision:
        try:
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
            return self._fallback_provider.decide(state)


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


def _zero_token_estimator(_: AgentDecision) -> int:
    return 0


def _provider_name(provider: DecisionProvider) -> str:
    return str(getattr(provider, "provider_name", provider.__class__.__name__))
