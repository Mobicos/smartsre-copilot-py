from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.agent_runtime.metrics_collector import MetricsCollector
from app.core.config import AppSettings


class _RunStore:
    def __init__(self) -> None:
        created_at = datetime.now(UTC)
        self.run = {
            "run_id": "run-1",
            "goal": "diagnose latency",
            "session_id": "session-1",
            "status": "completed",
            "final_report": "Latency was caused by upstream 5xx spikes.",
            "created_at": created_at,
            "updated_at": created_at + timedelta(milliseconds=250),
        }
        self.events = [
            {
                "type": "decision",
                "payload": {
                    "decision": {"action_type": "final_report"},
                    "token_usage": {
                        "prompt_tokens": 12,
                        "completion_tokens": 8,
                        "total": 20,
                        "source": "provider_usage",
                    },
                    "cost_estimate": {
                        "currency": "USD",
                        "total_cost": 0.0012,
                        "source": "provider_usage",
                    },
                },
            },
            {"type": "tool_call", "payload": {"tool": "SearchLog"}},
            {"type": "knowledge_context", "payload": {"citations": []}},
        ]
        self.persisted: dict[str, Any] | None = None

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        return self.run if run_id == "run-1" else None

    def list_events(self, run_id: str) -> list[dict[str, Any]]:
        return list(self.events) if run_id == "run-1" else []

    def update_run_metrics(self, run_id: str, **metrics: Any) -> None:
        self.persisted = metrics


def test_metrics_collector_prefers_provider_token_and_cost_events():
    run_store = _RunStore()
    collector = MetricsCollector(
        run_store,  # type: ignore[arg-type]
        AppSettings(agent_decision_provider="qwen", dashscope_model="qwen-max"),
    )

    metrics = collector.collect_run_metrics("run-1")
    collector.persist("run-1")

    assert metrics is not None
    assert metrics["model_name"] == "qwen-max"
    assert metrics["decision_provider"] == "qwen"
    assert metrics["step_count"] == 2
    assert metrics["tool_call_count"] == 1
    assert metrics["retrieval_count"] == 1
    assert metrics["latency_ms"] == 250
    assert metrics["token_usage"] == {
        "prompt_tokens": 12,
        "completion_tokens": 8,
        "tool_output_tokens": 0,
        "total": 20,
        "model": "qwen-max",
        "source": "provider_usage",
    }
    assert metrics["cost_estimate"] == {
        "currency": "USD",
        "total_cost": 0.0012,
        "model": "qwen-max",
        "source": "provider_usage",
        "components": {
            "tokens": 20,
            "tool_calls": 1,
            "retrievals": 1,
            "tool_latency_ms": {"count": 0, "total": 0, "avg": 0, "max": 0},
        },
    }
    assert run_store.persisted == metrics


def test_metrics_collector_aggregates_tool_result_latency():
    run_store = _RunStore()
    run_store.events = [
        {"type": "tool_call", "payload": {"tool_name": "SearchLog"}},
        {
            "type": "tool_result",
            "payload": {"tool_name": "SearchLog", "status": "success", "latency_ms": 12},
        },
        {"type": "tool_call", "payload": {"tool_name": "GetMetrics"}},
        {
            "type": "tool_result",
            "payload": {"tool_name": "GetMetrics", "status": "success", "latency_ms": 30},
        },
    ]
    collector = MetricsCollector(run_store, AppSettings(agent_decision_provider="deterministic"))  # type: ignore[arg-type]

    metrics = collector.collect_run_metrics("run-1")

    assert metrics is not None
    assert metrics["tool_call_count"] == 2
    assert metrics["cost_estimate"]["components"]["tool_latency_ms"] == {
        "count": 2,
        "total": 42,
        "avg": 21,
        "max": 30,
    }


# ---------------------------------------------------------------------------
# Tests for new Phase 11 metric functions
# ---------------------------------------------------------------------------


def test_recovery_count_from_recovery_events():
    run_store = _RunStore()
    run_store.events = [
        {"type": "recovery", "payload": {"reason": "timeout", "recovery_action": "retry"}},
        {"type": "tool_call", "payload": {"tool": "SearchLog"}},
        {"type": "recovery", "payload": {"reason": "empty_evidence"}},
        {
            "type": "tool_result",
            "payload": {"tool_name": "SearchLog", "recovery_action": "try_alternative"},
        },
    ]
    collector = MetricsCollector(run_store, AppSettings(agent_decision_provider="deterministic"))  # type: ignore[arg-type]
    metrics = collector.collect_run_metrics("run-1")
    assert metrics is not None
    assert metrics["recovery_count"] == 3


def test_empty_result_count_from_failed_tool_results():
    run_store = _RunStore()
    run_store.events = [
        {"type": "tool_call", "payload": {"tool": "SearchLog"}},
        {
            "type": "tool_result",
            "payload": {"tool_name": "SearchLog", "status": "error", "output": None},
        },
        {
            "type": "tool_result",
            "payload": {"tool_name": "GetMetrics", "status": "success", "output": "data"},
        },
        {
            "type": "tool_result",
            "payload": {"tool_name": "Timeout", "status": "timeout"},
        },
    ]
    collector = MetricsCollector(run_store, AppSettings(agent_decision_provider="deterministic"))  # type: ignore[arg-type]
    metrics = collector.collect_run_metrics("run-1")
    assert metrics is not None
    assert metrics["empty_result_count"] == 2


def test_duplicate_tool_call_detection():
    run_store = _RunStore()
    run_store.events = [
        {"type": "tool_call", "payload": {"tool_name": "SearchLog", "arguments": {"query": "cpu"}}},
        {"type": "tool_call", "payload": {"tool_name": "SearchLog", "arguments": {"query": "cpu"}}},
        {"type": "tool_call", "payload": {"tool_name": "SearchLog", "arguments": {"query": "mem"}}},
    ]
    collector = MetricsCollector(run_store, AppSettings(agent_decision_provider="deterministic"))  # type: ignore[arg-type]
    metrics = collector.collect_run_metrics("run-1")
    assert metrics is not None
    assert metrics["duplicate_tool_call_count"] == 1


def test_no_duplicates_for_different_arguments():
    run_store = _RunStore()
    run_store.events = [
        {"type": "tool_call", "payload": {"tool_name": "SearchLog", "arguments": {"query": "cpu"}}},
        {"type": "tool_call", "payload": {"tool_name": "SearchLog", "arguments": {"query": "mem"}}},
    ]
    collector = MetricsCollector(run_store, AppSettings(agent_decision_provider="deterministic"))  # type: ignore[arg-type]
    metrics = collector.collect_run_metrics("run-1")
    assert metrics is not None
    assert metrics["duplicate_tool_call_count"] == 0


def test_step_latencies_computed_from_step_index():
    from datetime import timezone

    base = datetime(2026, 5, 17, 10, 0, 0, tzinfo=timezone.utc)
    run_store = _RunStore()
    run_store.events = [
        {"type": "decision", "step_index": 0, "created_at": base},
        {"type": "tool_call", "step_index": 0, "created_at": base + timedelta(seconds=2)},
        {"type": "tool_result", "step_index": 0, "created_at": base + timedelta(seconds=5)},
        {"type": "decision", "step_index": 1, "created_at": base + timedelta(seconds=8)},
        {"type": "tool_call", "step_index": 1, "created_at": base + timedelta(seconds=10)},
        {"type": "tool_result", "step_index": 1, "created_at": base + timedelta(seconds=20)},
    ]
    collector = MetricsCollector(run_store, AppSettings(agent_decision_provider="deterministic"))  # type: ignore[arg-type]
    metrics = collector.collect_run_metrics("run-1")
    assert metrics is not None
    sl = metrics["step_latencies"]
    assert sl["count"] == 2
    assert sl["steps"][0]["step_index"] == 0
    assert sl["steps"][0]["duration_ms"] == 8000
    assert sl["steps"][1]["step_index"] == 1
    assert sl["steps"][1]["duration_ms"] == 12000
    assert sl["avg_ms"] == 10000
    assert sl["max_ms"] == 12000


def test_step_latencies_empty_when_no_step_index():
    run_store = _RunStore()
    run_store.events = [
        {"type": "decision", "payload": {"action": "tool_call"}},
        {"type": "tool_call", "payload": {"tool": "SearchLog"}},
    ]
    collector = MetricsCollector(run_store, AppSettings(agent_decision_provider="deterministic"))  # type: ignore[arg-type]
    metrics = collector.collect_run_metrics("run-1")
    assert metrics is not None
    assert metrics["step_latencies"]["count"] == 0


def test_regression_score_default_none():
    run_store = _RunStore()
    collector = MetricsCollector(run_store, AppSettings(agent_decision_provider="deterministic"))  # type: ignore[arg-type]
    metrics = collector.collect_run_metrics("run-1")
    assert metrics is not None
    assert metrics["regression_score"] is None


def test_new_metrics_persisted_to_store():
    run_store = _RunStore()
    run_store.events = [
        {"type": "recovery", "payload": {"reason": "timeout", "recovery_action": "retry"}},
        {"type": "tool_call", "payload": {"tool_name": "SearchLog", "arguments": {"q": "cpu"}}},
        {"type": "tool_call", "payload": {"tool_name": "SearchLog", "arguments": {"q": "cpu"}}},
        {"type": "tool_result", "payload": {"tool_name": "SearchLog", "status": "error"}},
    ]
    collector = MetricsCollector(run_store, AppSettings(agent_decision_provider="deterministic"))  # type: ignore[arg-type]
    collector.persist("run-1")

    assert run_store.persisted is not None
    assert run_store.persisted["recovery_count"] == 1
    assert run_store.persisted["empty_result_count"] == 1
    assert run_store.persisted["duplicate_tool_call_count"] == 1
    assert run_store.persisted["step_latencies"]["count"] == 0
    assert run_store.persisted["regression_score"] is None
