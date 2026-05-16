"""AgentOps metrics collection for Native Agent runs."""

from __future__ import annotations

import json
from typing import Any

from loguru import logger

from app.agent_runtime.constants import RUNTIME_VERSION
from app.agent_runtime.ports import AgentRunStore
from app.core.config import AppSettings


class MetricsCollector:
    """Derive and persist run-level metrics from stored events."""

    def __init__(self, run_store: AgentRunStore, settings: AppSettings) -> None:
        self._run_store = run_store
        self._settings = settings

    def collect_run_metrics(self, run_id: str) -> dict[str, Any] | None:
        run = self._run_store.get_run(run_id)
        events = self._run_store.list_events(run_id)
        if run is None:
            return None
        return {
            "runtime_version": RUNTIME_VERSION,
            "trace_id": run_id,
            "model_name": _runtime_model_name(self._settings),
            "decision_provider": _runtime_decision_provider(self._settings),
            "step_count": _metric_step_count(events),
            "tool_call_count": len(_events_by_type(events, "tool_call")),
            "latency_ms": _latency_ms(run.get("created_at"), run.get("updated_at")),
            "error_type": _metric_error_type(run, events),
            "approval_state": _metric_approval_state(events),
            "retrieval_count": len(_events_by_type(events, "knowledge_context")),
            "token_usage": _metric_token_usage(run, events, self._settings),
            "cost_estimate": _metric_cost_estimate(run, events, self._settings),
            "handoff_reason": _metric_handoff_reason(run, events),
        }

    def persist(self, run_id: str) -> None:
        try:
            metrics = self.collect_run_metrics(run_id)
            if metrics is None:
                return
            self._run_store.update_run_metrics(run_id, **metrics)
        except Exception as exc:
            logger.warning(f"Failed to persist agent run metrics for {run_id}: {exc}")


def _events_by_type(events: list[dict[str, Any]], event_type: str) -> list[dict[str, Any]]:
    return [event for event in events if event.get("type") == event_type]


def _metric_step_count(events: list[dict[str, Any]]) -> int:
    step_events = {"hypothesis", "decision", "tool_call", "tool_result"}
    return len([event for event in events if event.get("type") in step_events])


def _metric_approval_state(events: list[dict[str, Any]]) -> str:
    for event in events:
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        if payload.get("approval_state") == "required":
            return "required"
        if payload.get("execution_status") == "approval_required":
            return "required"
    return "not_required"


def _metric_error_type(run: dict[str, Any], events: list[dict[str, Any]]) -> str | None:
    for event in reversed(events):
        if event.get("type") not in {"timeout", "error"}:
            continue
        payload = event.get("payload")
        if isinstance(payload, dict) and payload.get("error_type"):
            return str(payload["error_type"])
    error_message = run.get("error_message")
    if isinstance(error_message, str) and ":" in error_message:
        return error_message.split(":", 1)[0]
    return None


def _metric_handoff_reason(run: dict[str, Any], events: list[dict[str, Any]]) -> str | None:
    for event in reversed(events):
        if event.get("type") not in {"handoff", "recovery"}:
            continue
        payload = event.get("payload")
        if isinstance(payload, dict) and payload.get("handoff_reason"):
            return str(payload["handoff_reason"])
        if isinstance(payload, dict) and payload.get("reason"):
            return str(payload["reason"])
    if run.get("status") == "handoff_required":
        error_message = run.get("error_message")
        return str(error_message) if error_message else "handoff_required"
    return None


def _metric_token_usage(
    run: dict[str, Any], events: list[dict[str, Any]], settings: AppSettings
) -> dict[str, Any]:
    """Estimate token usage from persisted runtime artifacts.

    Deterministic runs do not receive provider token accounting, so this keeps
    AgentOps fields attributable without pretending to be vendor billing data.
    """

    provider_usage = _provider_token_usage(events, settings)
    if provider_usage is not None:
        return provider_usage

    prompt_sources: list[Any] = [
        run.get("goal"),
        run.get("session_id"),
        [
            event.get("payload")
            for event in events
            if event.get("type") in {"run_started", "hypothesis", "observation", "tool_call"}
        ],
    ]
    completion_sources: list[Any] = [
        run.get("final_report"),
        [
            {
                "message": event.get("message"),
                "payload": event.get("payload"),
            }
            for event in events
            if event.get("type")
            in {"decision", "evidence_assessment", "recovery", "handoff", "final_report"}
        ],
    ]
    tool_output_sources: list[Any] = [
        event.get("payload") for event in events if event.get("type") == "tool_result"
    ]

    prompt_tokens = _estimate_tokens(prompt_sources)
    completion_tokens = _estimate_tokens(completion_sources)
    tool_output_tokens = _estimate_tokens(tool_output_sources)
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "tool_output_tokens": tool_output_tokens,
        "total": prompt_tokens + completion_tokens + tool_output_tokens,
        "model": _runtime_model_name(settings),
        "source": "heuristic",
    }


def _metric_cost_estimate(
    run: dict[str, Any], events: list[dict[str, Any]], settings: AppSettings
) -> dict[str, Any]:
    token_usage = _metric_token_usage(run, events, settings)
    provider_cost = _provider_cost_estimate(events, token_usage, settings)
    if provider_cost is not None:
        return provider_cost

    tool_call_count = len(_events_by_type(events, "tool_call"))
    retrieval_count = len(_events_by_type(events, "knowledge_context"))
    return {
        "currency": "USD",
        "total_cost": _estimate_agentops_cost(
            token_usage=token_usage,
            tool_call_count=tool_call_count,
            retrieval_count=retrieval_count,
        ),
        "model": _runtime_model_name(settings),
        "source": "heuristic",
        "components": {
            "tokens": token_usage["total"],
            "tool_calls": tool_call_count,
            "retrievals": retrieval_count,
            "tool_latency_ms": _metric_tool_latency_ms(events),
        },
    }


def _provider_token_usage(
    events: list[dict[str, Any]],
    settings: AppSettings,
) -> dict[str, Any] | None:
    for event in reversed(events):
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        token_usage = payload.get("token_usage")
        if not isinstance(token_usage, dict):
            continue
        prompt_tokens = _int_value(token_usage.get("prompt_tokens"))
        completion_tokens = _int_value(token_usage.get("completion_tokens"))
        tool_output_tokens = _int_value(token_usage.get("tool_output_tokens"))
        total = _int_value(token_usage.get("total"))
        if total == 0:
            total = prompt_tokens + completion_tokens + tool_output_tokens
        if total == 0:
            continue
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "tool_output_tokens": tool_output_tokens,
            "total": total,
            "model": str(token_usage.get("model") or _runtime_model_name(settings)),
            "source": str(token_usage.get("source") or "provider_usage"),
        }
    return None


def _provider_cost_estimate(
    events: list[dict[str, Any]],
    token_usage: dict[str, Any],
    settings: AppSettings,
) -> dict[str, Any] | None:
    for event in reversed(events):
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        cost_estimate = payload.get("cost_estimate")
        if not isinstance(cost_estimate, dict):
            continue
        total_cost = _float_value(cost_estimate.get("total_cost"))
        if total_cost == 0:
            continue
        tool_call_count = len(_events_by_type(events, "tool_call"))
        retrieval_count = len(_events_by_type(events, "knowledge_context"))
        return {
            "currency": str(cost_estimate.get("currency") or "USD"),
            "total_cost": total_cost,
            "model": str(cost_estimate.get("model") or _runtime_model_name(settings)),
            "source": str(cost_estimate.get("source") or "provider_usage"),
            "components": {
                "tokens": _int_value(token_usage.get("total")),
                "tool_calls": tool_call_count,
                "retrievals": retrieval_count,
                "tool_latency_ms": _metric_tool_latency_ms(events),
            },
        }
    return None


def _metric_tool_latency_ms(events: list[dict[str, Any]]) -> dict[str, int]:
    values: list[int] = []
    for event in events:
        if event.get("type") != "tool_result":
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        latency_ms = _int_value(payload.get("latency_ms"))
        if latency_ms > 0:
            values.append(latency_ms)
    if not values:
        return {"count": 0, "total": 0, "avg": 0, "max": 0}
    total = sum(values)
    return {
        "count": len(values),
        "total": total,
        "avg": total // len(values),
        "max": max(values),
    }


def _estimate_tokens(value: Any) -> int:
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except TypeError:
        encoded = str(value)
    compact = encoded.strip()
    if not compact or compact in {"null", "[]", "{}"}:
        return 0
    return max(1, (len(compact) + 3) // 4)


def _estimate_agentops_cost(
    *,
    token_usage: dict[str, Any],
    tool_call_count: int,
    retrieval_count: int,
) -> float:
    token_total = int(token_usage.get("total") or 0)
    token_cost = token_total * 0.000002
    tool_cost = tool_call_count * 0.01
    retrieval_cost = retrieval_count * 0.002
    return round(token_cost + tool_cost + retrieval_cost, 6)


def _int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float_value(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _runtime_model_name(settings: AppSettings) -> str:
    provider = settings.agent_decision_provider.strip().lower()
    if provider == "qwen":
        return settings.dashscope_model
    return "deterministic-native-agent"


def _runtime_decision_provider(settings: AppSettings) -> str:
    provider = settings.agent_decision_provider.strip().lower()
    return provider or "deterministic"


def _latency_ms(created_at: Any, updated_at: Any) -> int | None:
    if created_at is None or updated_at is None:
        return None
    try:
        return int((updated_at - created_at).total_seconds() * 1000)
    except AttributeError:
        return None
