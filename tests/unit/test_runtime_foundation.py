from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from app.agent_runtime.decision import (
    AgentDecision,
    AgentDecisionState,
    AgentGoalContract,
    EvidenceAssessment,
)
from app.agent_runtime.evidence import EvidenceAssessor
from app.agent_runtime.loop import BoundedReActLoop, LoopBudget
from app.agent_runtime.recovery import RecoveryManager, RecoveryPlan
from app.agent_runtime.state import EvidenceItem
from app.agent_runtime.trace_collector import TraceCollector


class _RepeatingProvider:
    provider_name = "test"

    def decide(self, state: AgentDecisionState) -> AgentDecision:
        return AgentDecision(
            action_type="call_tool",
            selected_tool="SearchLog",
            reasoning_summary=f"step {len(state.decisions)}",
        )


class _MetricsProvider(_RepeatingProvider):
    provider_name = "qwen"

    def get_token_usage(self) -> dict[str, Any]:
        return {
            "prompt_tokens": 12,
            "completion_tokens": 8,
            "total": 20,
            "source": "provider_usage",
        }

    def get_cost_estimate(self) -> dict[str, Any]:
        return {
            "currency": "USD",
            "total_cost": 0.0012,
            "source": "provider_usage",
        }


class _FailingProvider:
    provider_name = "qwen"

    def decide(self, state: AgentDecisionState) -> AgentDecision:
        raise RuntimeError("qwen unavailable")


class _ExplodingProvider:
    provider_name = "should-not-run"

    def decide(self, state: AgentDecisionState) -> AgentDecision:
        raise AssertionError("provider should not run when recovery is required")


class _StaticRecoveryManager:
    def __init__(self, plan: RecoveryPlan) -> None:
        self.plan = plan
        self.calls: list[dict[str, Any]] = []

    def choose_strategy(
        self,
        *,
        evidence_quality: str,
        consecutive_failures: int = 0,
        tool_available: bool = True,
    ) -> RecoveryPlan:
        self.calls.append(
            {
                "evidence_quality": evidence_quality,
                "consecutive_failures": consecutive_failures,
                "tool_available": tool_available,
            }
        )
        return self.plan


class _RecordingTraceCollector:
    def __init__(self) -> None:
        self.spans: list[tuple[str, dict[str, Any] | None]] = []

    @contextmanager
    def span(self, name: str, attributes: dict[str, Any] | None = None):
        self.spans.append((name, attributes))
        yield _RecordingSpan(attributes or {})


class _RecordingSpan:
    def __init__(self, attributes: dict[str, Any]) -> None:
        self._attributes = attributes

    def set_attribute(self, key: str, value: Any) -> None:
        self._attributes[key] = value


class _FakeClock:
    def __init__(self, *values: float) -> None:
        self._values = list(values)

    def __call__(self) -> float:
        if not self._values:
            raise AssertionError("Fake clock exhausted")
        return self._values.pop(0)


def test_bounded_react_loop_stops_at_max_steps():
    state = AgentDecisionState(
        run_id="run-1",
        goal=AgentGoalContract(goal="diagnose latency"),
        available_tools=["SearchLog"],
    )
    result = BoundedReActLoop(provider=_RepeatingProvider()).run(
        state,
        LoopBudget(max_steps=2, max_time_seconds=30),
    )

    assert result.termination_reason == "max_steps_reached"
    assert result.step_count == 2
    assert [step.step_index for step in result.steps] == [0, 1]


def test_bounded_react_loop_stops_when_time_budget_is_exhausted():
    state = AgentDecisionState(
        run_id="run-1",
        goal=AgentGoalContract(goal="diagnose latency"),
        available_tools=["SearchLog"],
    )

    result = BoundedReActLoop(
        provider=_RepeatingProvider(),
        clock=_FakeClock(0.0, 31.0),
    ).run(
        state,
        LoopBudget(max_steps=3, max_time_seconds=30),
    )

    assert result.termination_reason == "max_time_seconds_reached"
    assert result.step_count == 0


def test_bounded_react_loop_stops_when_token_budget_is_exhausted():
    state = AgentDecisionState(
        run_id="run-1",
        goal=AgentGoalContract(goal="diagnose latency"),
        available_tools=["SearchLog"],
    )

    result = BoundedReActLoop(
        provider=_RepeatingProvider(),
        token_estimator=lambda _: 2,
    ).run(
        state,
        LoopBudget(max_steps=3, max_time_seconds=30, max_tokens=1),
    )

    assert result.termination_reason == "max_tokens_reached"
    assert result.step_count == 0
    assert result.token_usage == 2


def test_bounded_react_loop_records_trace_span_for_each_step():
    state = AgentDecisionState(
        run_id="run-1",
        goal=AgentGoalContract(goal="diagnose latency"),
        available_tools=["SearchLog"],
    )
    trace_collector = _RecordingTraceCollector()

    result = BoundedReActLoop(
        provider=_RepeatingProvider(),
        token_estimator=lambda _: 17,
        trace_collector=trace_collector,
    ).run(
        state,
        LoopBudget(max_steps=2, max_time_seconds=30),
    )

    assert result.step_count == 2
    assert trace_collector.spans == [
        (
            "agent.loop_step",
            {
                "agent.run_id": "run-1",
                "agent.step_index": 0,
                "agent.max_steps": 2,
                "agent.action_type": "call_tool",
                "agent.tool_name": "SearchLog",
                "agent.evidence_quality": "empty",
                "agent.token_usage": 17,
                "agent.cost_estimate": 0.0,
            },
        ),
        (
            "agent.loop_step",
            {
                "agent.run_id": "run-1",
                "agent.step_index": 1,
                "agent.max_steps": 2,
                "agent.action_type": "call_tool",
                "agent.tool_name": "SearchLog",
                "agent.evidence_quality": "empty",
                "agent.token_usage": 17,
                "agent.cost_estimate": 0.0,
            },
        ),
    ]


def test_bounded_react_loop_records_step_metrics_from_provider():
    state = AgentDecisionState(
        run_id="run-1",
        goal=AgentGoalContract(goal="diagnose latency"),
        available_tools=["SearchLog"],
    )

    result = BoundedReActLoop(provider=_MetricsProvider()).run(
        state,
        LoopBudget(max_steps=1, max_time_seconds=30),
    )

    assert result.step_count == 1
    assert result.token_usage == 20
    assert result.steps[0].token_usage == 20
    assert result.steps[0].token_usage_detail == {
        "prompt_tokens": 12,
        "completion_tokens": 8,
        "total": 20,
        "source": "provider_usage",
    }
    assert result.steps[0].cost_estimate == {
        "currency": "USD",
        "total_cost": 0.0012,
        "source": "provider_usage",
    }
    assert result.step_metrics == [
        {
            "step_index": 0,
            "token_usage": result.steps[0].token_usage_detail,
            "cost_estimate": result.steps[0].cost_estimate,
        }
    ]


def test_bounded_react_loop_falls_back_when_primary_provider_fails():
    state = AgentDecisionState(
        run_id="run-1",
        goal=AgentGoalContract(goal="diagnose latency"),
        available_tools=["SearchLog"],
    )
    loop = BoundedReActLoop(
        provider=_FailingProvider(),
        fallback_provider=_RepeatingProvider(),
    )

    result = loop.run(
        state,
        LoopBudget(max_steps=1, max_time_seconds=30),
    )

    assert result.step_count == 1
    assert result.steps[0].decision.selected_tool == "SearchLog"
    assert loop.consume_provider_fallback_events() == [
        {
            "from_provider": "qwen",
            "to_provider": "test",
            "reason": "RuntimeError",
            "error_message": "qwen unavailable",
        }
    ]
    assert loop.consume_provider_fallback_events() == []


def test_bounded_react_loop_routes_empty_evidence_to_recovery_before_provider():
    recovery_manager = _StaticRecoveryManager(
        RecoveryPlan(action="retry_same_tool", reason="insufficient_evidence")
    )
    state = AgentDecisionState(
        run_id="run-1",
        goal=AgentGoalContract(goal="diagnose latency"),
        available_tools=["SearchLog"],
        evidence=[EvidenceAssessment(quality="empty", summary="no matching logs")],
        consecutive_empty_evidence=1,
    )

    result = BoundedReActLoop(
        provider=_ExplodingProvider(),
        recovery_manager=recovery_manager,
    ).run(
        state,
        LoopBudget(max_steps=1, max_time_seconds=30),
    )

    assert result.step_count == 1
    assert result.steps[0].decision.action_type == "recover"
    assert result.steps[0].decision.recovery.reason == "insufficient_evidence"
    assert result.steps[0].decision.recovery.next_action == "retry"
    assert recovery_manager.calls == [
        {
            "evidence_quality": "empty",
            "consecutive_failures": 1,
            "tool_available": True,
        }
    ]


def test_bounded_react_loop_handoffs_after_repeated_empty_evidence():
    recovery_manager = _StaticRecoveryManager(
        RecoveryPlan(
            action="handoff",
            reason="insufficient_evidence",
            handoff_required=True,
        )
    )
    state = AgentDecisionState(
        run_id="run-1",
        goal=AgentGoalContract(goal="diagnose latency"),
        available_tools=["SearchLog"],
        evidence=[EvidenceAssessment(quality="empty", summary="still no signal")],
        consecutive_empty_evidence=3,
    )

    result = BoundedReActLoop(
        provider=_ExplodingProvider(),
        recovery_manager=recovery_manager,
    ).run(
        state,
        LoopBudget(max_steps=2, max_time_seconds=30),
    )

    assert result.termination_reason == "handoff"
    assert result.status == "handoff_required"
    assert result.step_count == 1
    assert result.steps[0].decision.action_type == "handoff"
    assert result.steps[0].decision.handoff_reason == "insufficient_evidence"


def test_bounded_react_loop_downgrades_weak_evidence_to_bounded_report():
    recovery_manager = _StaticRecoveryManager(
        RecoveryPlan(action="downgrade_report", reason="weak_evidence")
    )
    state = AgentDecisionState(
        run_id="run-1",
        goal=AgentGoalContract(goal="diagnose latency"),
        evidence=[
            EvidenceAssessment(
                quality="weak",
                summary="single low-confidence symptom",
                confidence=0.35,
            )
        ],
    )

    result = BoundedReActLoop(
        provider=_ExplodingProvider(),
        recovery_manager=recovery_manager,
    ).run(
        state,
        LoopBudget(max_steps=2, max_time_seconds=30),
    )

    assert result.termination_reason == "final_report"
    assert result.status == "completed"
    assert result.step_count == 1
    assert result.steps[0].decision.action_type == "final_report"
    assert result.steps[0].decision.recovery.reason == "weak_evidence"
    assert result.steps[0].decision.recovery.next_action == "final_report"


def test_evidence_assessor_accepts_mapping_outputs_as_strong_evidence():
    assessment = EvidenceAssessor().assess(
        EvidenceItem(
            tool_name="SearchLog",
            status="success",
            output={"errors": 12},
        )
    )

    assert assessment.quality == "strong"
    assert assessment.confidence > 0


def test_recovery_manager_selects_handoff_after_repeated_empty_evidence():
    manager = RecoveryManager(
        run_store=object(),  # type: ignore[arg-type]
        event_recorder=object(),  # type: ignore[arg-type]
        metrics_collector=object(),  # type: ignore[arg-type]
    )

    plan = manager.choose_strategy(evidence_quality="empty", consecutive_failures=2)

    assert plan.action == "handoff"
    assert plan.reason == "insufficient_evidence"
    assert plan.handoff_required is True


def test_trace_collector_span_is_optional_runtime_boundary():
    collector = TraceCollector("smartsre.tests")

    with collector.span("agent.test", {"agent.step_index": 1}):
        observed = "inside-span"

    assert observed == "inside-span"
