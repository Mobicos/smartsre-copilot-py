"""Recovery and failure boundary helpers for Native Agent runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.agent_runtime.approval import EventRecorderProtocol
from app.agent_runtime.events import AgentRuntimeEvent
from app.agent_runtime.metrics_collector import MetricsCollector
from app.agent_runtime.ports import AgentRunStore

RecoveryAction = str


@dataclass(frozen=True)
class RecoveryPlan:
    """Structured recovery strategy selected from evidence quality."""

    action: RecoveryAction
    reason: str
    handoff_required: bool = False


class RuntimeSafetyProtocol(Protocol):
    """Runtime safety fields used in recovery events."""

    @property
    def run_timeout_seconds(self) -> float:
        """Maximum runtime in seconds."""
        ...

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe safety config snapshot."""
        ...


class RecoveryContext(Protocol):
    """Runtime fields needed by recovery and failure handling."""

    @property
    def run_id(self) -> str:
        """Agent run identifier."""
        ...

    @property
    def safety_config(self) -> RuntimeSafetyProtocol:
        """Runtime safety config snapshot."""
        ...


class RecoveryManager:
    """Translate runtime failures into persisted run state and stream events."""

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

    def choose_strategy(
        self,
        *,
        evidence_quality: str,
        consecutive_failures: int = 0,
        tool_available: bool = True,
    ) -> RecoveryPlan:
        """Choose a bounded recovery action from evidence and failure state."""

        if evidence_quality == "strong":
            return RecoveryPlan(action="continue", reason="strong_evidence")
        if evidence_quality in {"partial", "weak"} and tool_available:
            return RecoveryPlan(action="try_alternative", reason=f"{evidence_quality}_evidence")
        if evidence_quality in {"empty", "insufficient"}:
            if consecutive_failures <= 0 and tool_available:
                return RecoveryPlan(action="try_alternative", reason="insufficient_evidence")
            return RecoveryPlan(
                action="handoff",
                reason="insufficient_evidence",
                handoff_required=True,
            )
        if evidence_quality in {"conflict", "conflicting"}:
            return RecoveryPlan(
                action="handoff",
                reason="conflicting_evidence",
                handoff_required=True,
            )
        if (
            evidence_quality in {"timeout", "error"}
            and consecutive_failures <= 0
            and tool_available
        ):
            return RecoveryPlan(action="try_alternative", reason=f"{evidence_quality}_evidence")
        return RecoveryPlan(action="handoff", reason="evidence_error", handoff_required=True)

    def mark_cancelled(
        self,
        context: RecoveryContext,
    ) -> None:
        self._run_store.update_run(
            context.run_id,
            status="cancelled",
            error_message="Agent 运行已取消",
        )
        self._event_recorder.record(
            context.run_id,
            event_type="cancelled",
            stage="cancelled",
            message="Agent 运行已取消",
            payload={"runtime_safety": context.safety_config.to_dict()},
        )
        self._metrics_collector.persist(context.run_id)

    def timeout_event(self, context: RecoveryContext, exc: TimeoutError) -> list[AgentRuntimeEvent]:
        error_message = str(exc) or (
            f"Agent 运行超时，已运行 {context.safety_config.run_timeout_seconds:g} 秒"
        )
        self._run_store.update_run(
            context.run_id,
            status="failed",
            error_message=f"TimeoutError: {error_message}",
        )
        event = self._event_recorder.record(
            context.run_id,
            event_type="timeout",
            stage="error",
            message=f"运行超时：{error_message}",
            payload={
                "error_type": "TimeoutError",
                "error_message": error_message,
                "timeout_scope": "run",
                "runtime_safety": context.safety_config.to_dict(),
            },
        )
        self._metrics_collector.persist(context.run_id)
        return [
            event,
            AgentRuntimeEvent(
                type="timeout",
                stage="error",
                run_id=context.run_id,
                status="failed",
                message=f"TimeoutError: {error_message}",
            ),
        ]

    def error_event(self, context: RecoveryContext, exc: Exception) -> list[AgentRuntimeEvent]:
        error_type = type(exc).__name__
        error_message = str(exc)
        self._run_store.update_run(
            context.run_id,
            status="failed",
            error_message=f"{error_type}: {error_message}",
        )
        event = self._event_recorder.record(
            context.run_id,
            event_type="error",
            stage="error",
            message=f"运行失败：{error_message}",
            payload={
                "error_type": error_type,
                "error_message": error_message,
                "runtime_safety": context.safety_config.to_dict(),
            },
        )
        self._metrics_collector.persist(context.run_id)
        return [
            event,
            AgentRuntimeEvent(
                type="error",
                stage="error",
                run_id=context.run_id,
                status="failed",
                message=f"{error_type}: {error_message}",
            ),
        ]
