from __future__ import annotations

from app.agent_runtime.recovery import RecoveryManager


def _manager() -> RecoveryManager:
    return RecoveryManager(
        run_store=object(),  # type: ignore[arg-type]
        event_recorder=object(),  # type: ignore[arg-type]
        metrics_collector=object(),  # type: ignore[arg-type]
    )


def test_recovery_manager_retries_empty_evidence_once():
    plan = _manager().choose_strategy(
        evidence_quality="empty",
        consecutive_failures=0,
        tool_available=True,
    )

    assert plan.action == "retry_same_tool"
    assert plan.reason == "insufficient_evidence"
    assert plan.handoff_required is False


def test_recovery_manager_downgrades_report_after_empty_retry_when_tools_remain():
    plan = _manager().choose_strategy(
        evidence_quality="empty",
        consecutive_failures=1,
        tool_available=True,
    )

    assert plan.action == "downgrade_report"
    assert plan.reason == "insufficient_evidence"
    assert plan.handoff_required is False


def test_recovery_manager_hands_off_after_repeated_empty_evidence():
    plan = _manager().choose_strategy(
        evidence_quality="empty",
        consecutive_failures=2,
        tool_available=True,
    )

    assert plan.action == "handoff"
    assert plan.reason == "insufficient_evidence"
    assert plan.handoff_required is True


def test_recovery_manager_hands_off_conflicting_evidence():
    plan = _manager().choose_strategy(
        evidence_quality="conflicting",
        consecutive_failures=0,
        tool_available=True,
    )

    assert plan.action == "handoff"
    assert plan.reason == "conflicting_evidence"
    assert plan.handoff_required is True


def test_recovery_manager_downgrades_weak_evidence_when_no_tool_remains():
    plan = _manager().choose_strategy(
        evidence_quality="weak",
        consecutive_failures=0,
        tool_available=False,
    )

    assert plan.action == "downgrade_report"
    assert plan.reason == "weak_evidence"
    assert plan.handoff_required is False
