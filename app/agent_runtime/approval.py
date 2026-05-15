"""Approval gating helpers for governed Agent tool execution."""

from __future__ import annotations

from typing import Any, Protocol

from app.agent_runtime.events import AgentRuntimeEvent
from app.agent_runtime.metrics_collector import MetricsCollector
from app.agent_runtime.ports import AgentRunStore


class ApprovalContext(Protocol):
    """Runtime fields needed when pausing for approval."""

    @property
    def run_id(self) -> str:
        """Agent run identifier."""
        ...


class EventRecorderProtocol(Protocol):
    """Small recorder interface used by runtime boundary helpers."""

    def record(
        self,
        run_id: str,
        *,
        event_type: str,
        stage: str,
        message: str,
        payload: dict[str, Any],
    ) -> AgentRuntimeEvent:
        """Persist an event and return the stream-friendly event."""
        ...


class ApprovalGate:
    """Centralize approval pause semantics for the Agent runtime."""

    waiting_message = "工具执行等待人工审批。"

    def __init__(
        self,
        *,
        run_store: AgentRunStore,
        event_recorder: EventRecorderProtocol,
        metrics_collector: MetricsCollector,
    ) -> None:
        self._run_store = run_store
        self._event_recorder = event_recorder
        self._metrics_collector = metrics_collector

    def pause(
        self,
        context: ApprovalContext,
        *,
        tool_name: str,
        payload: dict[str, Any],
    ) -> list[AgentRuntimeEvent]:
        self._run_store.update_run(
            context.run_id,
            status="waiting_approval",
            final_report=self.waiting_message,
        )
        event = self._event_recorder.record(
            context.run_id,
            event_type="approval_required",
            stage="approval",
            message=f"工具需要审批：{tool_name}",
            payload=payload,
        )
        self._metrics_collector.persist(context.run_id)
        return [
            event,
            AgentRuntimeEvent(
                type="approval_required",
                stage="approval",
                run_id=context.run_id,
                status="waiting_approval",
                message=f"工具需要审批：{tool_name}",
            ),
        ]
