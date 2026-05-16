from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from app.agent_runtime.decision import AgentDecision, AgentDecisionState, AgentGoalContract
from app.agent_runtime.evidence import EvidenceAssessor
from app.agent_runtime.loop import BoundedReActLoop, LoopBudget
from app.agent_runtime.recovery import RecoveryManager
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


class _FailingProvider:
    provider_name = "qwen"

    def decide(self, state: AgentDecisionState) -> AgentDecision:
        raise RuntimeError("qwen unavailable")


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

    plan = manager.choose_strategy(evidence_quality="empty", consecutive_failures=1)

    assert plan.action == "handoff"
    assert plan.reason == "insufficient_evidence"
    assert plan.handoff_required is True


def test_trace_collector_span_is_optional_runtime_boundary():
    collector = TraceCollector("smartsre.tests")

    with collector.span("agent.test", {"agent.step_index": 1}):
        observed = "inside-span"

    assert observed == "inside-span"
