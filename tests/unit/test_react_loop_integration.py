"""Integration tests for the full BoundedReAct loop with tool execution."""

from __future__ import annotations

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
from app.agent_runtime.tool_executor import ToolExecutionResult


class _ToolCallProvider:
    """Provider that issues tool calls until budget exhaustion."""

    provider_name = "test"

    def decide(self, state: AgentDecisionState) -> AgentDecision:
        return AgentDecision(
            action_type="call_tool",
            selected_tool="SearchLog",
            reasoning_summary=f"step {len(state.decisions)}",
        )


class _TerminalProvider:
    """Provider that immediately emits a final_report."""

    provider_name = "test"

    def decide(self, state: AgentDecisionState) -> AgentDecision:
        return AgentDecision(
            action_type="final_report",
            selected_tool=None,
            reasoning_summary="evidence is sufficient",
            evidence=EvidenceAssessment(quality="strong", summary="root cause confirmed"),
            confidence=0.9,
        )


class _ApprovalProvider:
    """Provider that emits an action needing approval on step 0."""

    provider_name = "test"

    def decide(self, state: AgentDecisionState) -> AgentDecision:
        return AgentDecision(
            action_type="call_tool",
            selected_tool="RebootService",
            reasoning_summary="need to reboot",
        )


class _HandoffProvider:
    """Provider that emits a handoff decision."""

    provider_name = "test"

    def decide(self, state: AgentDecisionState) -> AgentDecision:
        return AgentDecision(
            action_type="handoff",
            selected_tool=None,
            reasoning_summary="cannot proceed without human",
        )


class _SuccessfulToolExecutor:
    """Returns a successful tool result for every call."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, decision: AgentDecision) -> ToolExecutionResult:
        tool = decision.selected_tool or "unknown"
        self.calls.append(tool)
        return ToolExecutionResult(
            tool_name=tool,
            status="success",
            arguments={},
            output="CPU: 92%, Memory: 87%, root cause: OOM killer active",
        )


class _FailingToolExecutor:
    """Returns an error result for every call."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, decision: AgentDecision) -> ToolExecutionResult:
        tool = decision.selected_tool or "unknown"
        self.calls.append(tool)
        return ToolExecutionResult(
            tool_name=tool,
            status="error",
            arguments={},
            error="tool execution timeout",
        )


class _ApprovalToolExecutor:
    """Returns approval_required for the first call, success afterwards."""

    def __init__(self) -> None:
        self.call_count = 0

    def __call__(self, decision: AgentDecision) -> ToolExecutionResult:
        self.call_count += 1
        if self.call_count == 1:
            return ToolExecutionResult(
                tool_name=decision.selected_tool or "unknown",
                status="approval_required",
                arguments={},
                policy={"tool_name": "RebootService", "approval_required": True},
            )
        return ToolExecutionResult(
            tool_name=decision.selected_tool or "unknown",
            status="success",
            arguments={},
            output="reboot completed",
        )


class _EmptyToolExecutor:
    """Returns empty output to trigger recovery."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, decision: AgentDecision) -> ToolExecutionResult:
        tool = decision.selected_tool or "unknown"
        self.calls.append(tool)
        return ToolExecutionResult(
            tool_name=tool,
            status="success",
            arguments={},
            output=None,
        )


class _LoopRecoveryManager:
    """Recovery manager that retries on empty evidence and downgrades after 3 failures."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def choose_strategy(
        self,
        *,
        evidence_quality: str,
        consecutive_failures: int = 0,
        tool_available: bool = True,
    ) -> RecoveryPlan:
        self.calls.append({
            "evidence_quality": evidence_quality,
            "consecutive_failures": consecutive_failures,
        })
        if consecutive_failures >= 3:
            return RecoveryPlan(
                action="downgrade_report",
                reason="too many consecutive failures",
            )
        return RecoveryPlan(
            action="retry",
            reason="evidence empty, retrying",
        )


def _make_state(tools: list[str] | None = None) -> AgentDecisionState:
    return AgentDecisionState(
        run_id="run-integration-1",
        goal=AgentGoalContract(goal="diagnose high memory usage"),
        available_tools=tools or ["SearchLog", "CheckMetric"],
    )


# --- tests ---


def test_full_loop_with_tool_execution():
    """Loop executes tools, collects evidence, stops at max_steps."""
    tool_executor = _SuccessfulToolExecutor()
    state = _make_state()

    result = BoundedReActLoop(
        provider=_ToolCallProvider(),
        tool_executor=tool_executor,
    ).run(
        state,
        LoopBudget(max_steps=3, max_time_seconds=30),
    )

    assert result.termination_reason == "max_steps_reached"
    assert result.step_count == 3
    assert tool_executor.calls == ["SearchLog", "SearchLog", "SearchLog"]
    assert len(result.evidence_items) == 3
    for item in result.evidence_items:
        assert item.status == "success"
        assert "OOM" in str(item.output)
    assert result.token_usage == 0


def test_loop_stops_on_final_report_with_evidence():
    """Loop terminates early on final_report decision and returns evidence."""
    tool_executor = _SuccessfulToolExecutor()
    state = _make_state()

    result = BoundedReActLoop(
        provider=_TerminalProvider(),
        tool_executor=tool_executor,
    ).run(
        state,
        LoopBudget(max_steps=5, max_time_seconds=30),
    )

    assert result.termination_reason == "final_report"
    assert result.step_count == 1
    assert tool_executor.calls == []  # final_report doesn't execute tools
    assert result.steps[0].decision.evidence.quality == "strong"


def test_loop_pauses_on_approval_required():
    """Loop returns approval_required when tool status is approval_required."""
    tool_executor = _ApprovalToolExecutor()
    state = _make_state()

    result = BoundedReActLoop(
        provider=_ApprovalProvider(),
        tool_executor=tool_executor,
    ).run(
        state,
        LoopBudget(max_steps=5, max_time_seconds=30),
    )

    assert result.termination_reason == "approval_required"
    assert result.step_count == 1
    assert result.steps[0].tool_result.status == "approval_required"
    assert len(result.evidence_items) == 1


def test_loop_collects_evidence_from_failing_tools():
    """Loop still collects evidence items when tool execution fails."""
    tool_executor = _FailingToolExecutor()
    state = _make_state()

    result = BoundedReActLoop(
        provider=_ToolCallProvider(),
        tool_executor=tool_executor,
    ).run(
        state,
        LoopBudget(max_steps=2, max_time_seconds=30),
    )

    assert result.termination_reason == "max_steps_reached"
    assert len(result.evidence_items) == 2
    for item in result.evidence_items:
        assert item.status == "error"
        assert item.error == "tool execution timeout"


def test_loop_with_recovery_manager_retries_on_empty_evidence():
    """Recovery manager intercepts empty evidence and issues retry decisions."""
    tool_executor = _EmptyToolExecutor()
    recovery = _LoopRecoveryManager()
    state = _make_state()

    result = BoundedReActLoop(
        provider=_ToolCallProvider(),
        tool_executor=tool_executor,
        recovery_manager=recovery,
    ).run(
        state,
        LoopBudget(max_steps=4, max_time_seconds=30),
    )

    assert result.step_count >= 2
    assert result.termination_reason in ("max_steps_reached", "final_report")
    assert len(recovery.calls) >= 1


def test_loop_handles_mixed_tool_results():
    """Loop handles a mix of success and failure tool results across steps."""
    call_count = 0

    def _mixed_executor(decision: AgentDecision) -> ToolExecutionResult:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return ToolExecutionResult(
                tool_name="SearchLog", status="success", arguments={},
                output="error logs found: OOM killer invoked",
            )
        return ToolExecutionResult(
            tool_name="SearchLog", status="error", arguments={},
            error="connection refused",
        )

    state = _make_state()

    result = BoundedReActLoop(
        provider=_ToolCallProvider(),
        tool_executor=_mixed_executor,
    ).run(
        state,
        LoopBudget(max_steps=2, max_time_seconds=30),
    )

    assert result.step_count == 2
    assert result.evidence_items[0].status == "success"
    assert result.evidence_items[1].status == "error"
    assert "OOM" in str(result.evidence_items[0].output)


def test_loop_handoff_decision_terminates_immediately():
    """Handoff decision terminates the loop with no tool execution."""
    state = _make_state()

    result = BoundedReActLoop(
        provider=_HandoffProvider(),
    ).run(
        state,
        LoopBudget(max_steps=5, max_time_seconds=30),
    )

    assert result.termination_reason == "handoff"
    assert result.step_count == 1
    assert len(result.evidence_items) == 0
