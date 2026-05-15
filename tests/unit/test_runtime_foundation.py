from __future__ import annotations

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
