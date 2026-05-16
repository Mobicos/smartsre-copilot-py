"""Unit tests for AgentMetricsService (Release Gate)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from app.application.agent_metrics_service import AgentMetricsService


class _FakeRunRepository:
    def __init__(self, runs: list[dict[str, Any]], events_map: dict[str, list[dict[str, Any]]]):
        self._runs = runs
        self._events_map = events_map

    def list_runs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        return self._runs[:limit]

    def list_events(self, run_id: str) -> list[dict[str, Any]]:
        return self._events_map.get(run_id, [])


def _make_run(
    run_id: str,
    *,
    status: str = "completed",
    tool_call_count: int = 5,
    latency_ms: int | None = 30000,
    approval_state: str | None = None,
    duplicate_tool_call_count: int = 0,
    empty_result_count: int = 0,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "status": status,
        "tool_call_count": tool_call_count,
        "latency_ms": latency_ms,
        "approval_state": approval_state,
        "duplicate_tool_call_count": duplicate_tool_call_count,
        "empty_result_count": empty_result_count,
        "recovery_count": 0,
        "step_count": 3,
        "token_usage": {"total": 100},
        "cost_estimate": {"total_cost": 0.01},
    }


def _make_service(
    runs: list[dict[str, Any]],
    events_map: dict[str, list[dict[str, Any]]] | None = None,
) -> AgentMetricsService:
    repo = _FakeRunRepository(runs, events_map or {})
    mock_scenario = MagicMock()
    mock_scenario.evaluate_run.return_value = {"score": 0.9, "status": "passed"}
    return AgentMetricsService(
        agent_run_repository=repo,  # type: ignore[arg-type]
        scenario_regression_service=mock_scenario,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# goal_completion_rate
# ---------------------------------------------------------------------------


def test_goal_completion_rate_with_matching_runs():
    runs = [_make_run("r1"), _make_run("r2"), _make_run("r3")]
    service = _make_service(runs)
    result = service.compute_release_gate(limit=10)
    assert result["goal_completion_rate"] == 0.9


def test_goal_completion_rate_zero_when_no_runs():
    service = _make_service([])
    result = service.compute_release_gate(limit=10)
    assert result["goal_completion_rate"] == 0.0


# ---------------------------------------------------------------------------
# unnecessary_tool_call_ratio
# ---------------------------------------------------------------------------


def test_unnecessary_tool_call_ratio_zero_for_clean_runs():
    runs = [_make_run("r1", tool_call_count=10), _make_run("r2", tool_call_count=8)]
    service = _make_service(runs)
    result = service.compute_release_gate(limit=10)
    assert result["unnecessary_tool_call_ratio"] == 0.0


def test_unnecessary_tool_call_ratio_calculates_correctly():
    runs = [
        _make_run("r1", tool_call_count=10, duplicate_tool_call_count=2, empty_result_count=1),
        _make_run("r2", tool_call_count=5),
    ]
    service = _make_service(runs)
    result = service.compute_release_gate(limit=10)
    # (2 + 1 + 0 + 0) / (10 + 5) = 3/15 = 0.2
    assert abs(result["unnecessary_tool_call_ratio"] - 0.2) < 0.01


# ---------------------------------------------------------------------------
# P95 latency
# ---------------------------------------------------------------------------


def test_p95_latency_computed_correctly():
    runs = [_make_run(f"r{i}", latency_ms=i * 1000) for i in range(1, 101)]
    service = _make_service(runs)
    result = service.compute_release_gate(limit=200)
    # P95 of 1..100 * 1000 = 95000
    assert result["p95_latency_ms"] == 95000


def test_p95_latency_none_when_no_runs():
    service = _make_service([])
    result = service.compute_release_gate(limit=10)
    assert result["p95_latency_ms"] is None


# ---------------------------------------------------------------------------
# approval_override_rate
# ---------------------------------------------------------------------------


def test_approval_override_rate_zero_when_enforced():
    runs = [_make_run("r1", approval_state="required")]
    events_map = {"r1": [{"type": "approval_decision"}]}
    service = _make_service(runs, events_map)
    result = service.compute_release_gate(limit=10)
    assert result["approval_override_rate"] == 0.0


def test_approval_override_rate_detects_bypass():
    runs = [_make_run("r1", approval_state="required")]
    # No approval_decision event → bypass
    service = _make_service(runs, events_map={})
    result = service.compute_release_gate(limit=10)
    assert result["approval_override_rate"] == 1.0


# ---------------------------------------------------------------------------
# gate_pass
# ---------------------------------------------------------------------------


def test_release_gate_pass_all_thresholds_met():
    runs = [_make_run(f"r{i}", latency_ms=30000) for i in range(10)]
    service = _make_service(runs)
    result = service.compute_release_gate(limit=20)
    assert result["gate_pass"] is True


def test_release_gate_fail_when_p95_latency_breached():
    runs = [_make_run(f"r{i}", latency_ms=90000) for i in range(10)]
    service = _make_service(runs)
    result = service.compute_release_gate(limit=20)
    assert result["gate_pass"] is False


# ---------------------------------------------------------------------------
# compute_summary
# ---------------------------------------------------------------------------


def test_compute_summary_returns_aggregate_stats():
    runs = [
        _make_run("r1", latency_ms=20000, tool_call_count=5),
        _make_run("r2", latency_ms=40000, tool_call_count=3),
        _make_run("r3", status="failed", latency_ms=None, tool_call_count=0),
    ]
    service = _make_service(runs)
    result = service.compute_summary(limit=10)
    assert result["total_runs"] == 3
    assert result["completed"] == 2
    assert result["failed"] == 1
    assert result["avg_latency_ms"] == 30000
    assert result["total_tool_calls"] == 8
