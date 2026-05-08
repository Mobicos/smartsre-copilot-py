"""Native SRE Agent runtime.

The runtime keeps reasoning deterministic and auditable around the model-facing
decision layer: it builds an explicit state, routes scene-approved tools through
policy gates, assesses evidence, and persists every step as replayable events.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from time import monotonic
from typing import Any, cast

from loguru import logger

from app.agent_runtime.context import KnowledgeContextProvider
from app.agent_runtime.decision import (
    AgentDecision,
    AgentDecisionRuntime,
    EvidenceAssessment,
    FinalReportContract,
    Priority,
    RecoveryDecision,
    RuntimeBudget,
    StopCondition,
    build_initial_decision_state,
)
from app.agent_runtime.events import AgentRuntimeEvent
from app.agent_runtime.executor import AgentToolExecutor
from app.agent_runtime.planner import AgentPlanner
from app.agent_runtime.policy import ToolPolicyGate
from app.agent_runtime.ports import AgentRunStore, SceneStore, ToolPolicyStore
from app.agent_runtime.state import EvidenceItem
from app.agent_runtime.synthesizer import ReportSynthesizer
from app.agent_runtime.tool_catalog import ToolCatalog
from app.agent_runtime.tool_executor import ToolExecutionResult, ToolExecutor
from app.config import config


@dataclass(frozen=True)
class RuntimeSafetyConfig:
    """Bounded execution defaults for one Native Agent run."""

    max_steps: int = 5
    tool_timeout_seconds: float = 30.0
    run_timeout_seconds: float = 120.0

    @classmethod
    def from_scene(cls, scene: dict[str, Any]) -> RuntimeSafetyConfig:
        agent_config = scene.get("agent_config")
        if not isinstance(agent_config, dict):
            agent_config = {}

        defaults = cls(
            max_steps=_positive_int(config.agent_max_steps, default=cls.max_steps),
            tool_timeout_seconds=_positive_float(
                config.agent_step_timeout_seconds,
                default=cls.tool_timeout_seconds,
            ),
            run_timeout_seconds=_positive_float(
                config.agent_total_timeout_seconds,
                default=cls.run_timeout_seconds,
            ),
        )
        return cls(
            max_steps=_positive_int(
                agent_config.get("max_steps"),
                default=defaults.max_steps,
            ),
            tool_timeout_seconds=_positive_float(
                agent_config.get("tool_timeout_seconds"),
                default=defaults.tool_timeout_seconds,
            ),
            run_timeout_seconds=_positive_float(
                agent_config.get("run_timeout_seconds"),
                default=defaults.run_timeout_seconds,
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_steps": self.max_steps,
            "tool_timeout_seconds": self.tool_timeout_seconds,
            "run_timeout_seconds": self.run_timeout_seconds,
        }


@dataclass(frozen=True)
class RuntimeDeadline:
    """Monotonic deadline for one Agent run."""

    expires_at: float
    timeout_seconds: float

    @classmethod
    def start(cls, timeout_seconds: float) -> RuntimeDeadline:
        return cls(expires_at=monotonic() + timeout_seconds, timeout_seconds=timeout_seconds)

    def remaining_seconds(self) -> float:
        return self.expires_at - monotonic()

    def ensure_available(self) -> None:
        if self.remaining_seconds() <= 0:
            raise TimeoutError(f"Agent run timed out after {self.timeout_seconds:g} seconds")


@dataclass(frozen=True)
class RuntimeContext:
    """Immutable runtime envelope shared by orchestration helpers."""

    run_id: str
    scene_id: str
    workspace_id: str
    session_id: str
    goal: str
    success_criteria: list[str]
    stop_condition: dict[str, Any]
    priority: Priority
    safety_config: RuntimeSafetyConfig
    deadline: RuntimeDeadline


class EventRecorder:
    """Persist trajectory events and return stream-friendly runtime events."""

    def __init__(self, run_store: AgentRunStore) -> None:
        self._run_store = run_store

    def record(
        self,
        run_id: str,
        *,
        event_type: str,
        stage: str,
        message: str,
        payload: dict[str, Any],
    ) -> AgentRuntimeEvent:
        self._run_store.append_event(
            run_id,
            event_type=event_type,
            stage=stage,
            message=message,
            payload=payload,
        )
        return AgentRuntimeEvent(
            type=event_type,
            stage=stage,
            run_id=run_id,
            message=message,
            payload=payload,
        )


class MetricsCollector:
    """Derive and persist run-level metrics from stored events."""

    def __init__(self, run_store: AgentRunStore) -> None:
        self._run_store = run_store

    def persist(self, run_id: str) -> None:
        try:
            run = self._run_store.get_run(run_id)
            events = self._run_store.list_events(run_id)
            if run is None:
                return
            self._run_store.update_run_metrics(
                run_id,
                runtime_version="native-agent-dev",
                trace_id=run_id,
                model_name=_runtime_model_name(),
                decision_provider=_runtime_decision_provider(),
                step_count=_metric_step_count(events),
                tool_call_count=len(_events_by_type(events, "tool_call")),
                latency_ms=_latency_ms(run.get("created_at"), run.get("updated_at")),
                error_type=_metric_error_type(run, events),
                approval_state=_metric_approval_state(events),
                retrieval_count=len(_events_by_type(events, "knowledge_context")),
                token_usage=None,
                cost_estimate=None,
                handoff_reason=_metric_handoff_reason(run, events),
            )
        except Exception as exc:
            logger.warning(f"Failed to persist agent run metrics for {run_id}: {exc}")


class StepRunner:
    """Execute one governed tool step for the runtime orchestrator."""

    def __init__(self, runtime: AgentRuntime) -> None:
        self._runtime = runtime

    async def execute_tool(
        self,
        tool: Any,
        action: Any,
        *,
        principal: Any,
        safety_config: RuntimeSafetyConfig,
        deadline: RuntimeDeadline,
    ) -> ToolExecutionResult:
        return cast(
            ToolExecutionResult,
            await self._runtime._execute_tool_with_timeout(
                tool,
                action,
                principal=principal,
                safety_config=safety_config,
                deadline=deadline,
            ),
        )


class ApprovalBoundary:
    """Centralize approval pause semantics for the Agent runtime."""

    waiting_message = "Tool execution is waiting for human approval."

    def __init__(
        self,
        *,
        run_store: AgentRunStore,
        event_recorder: EventRecorder,
        metrics_collector: MetricsCollector,
    ) -> None:
        self._run_store = run_store
        self._event_recorder = event_recorder
        self._metrics_collector = metrics_collector

    def pause(
        self,
        context: RuntimeContext,
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
            message=f"Tool approval required: {tool_name}",
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
                message=f"Tool approval required: {tool_name}",
            ),
        ]


class RuntimeFailureHandler:
    """Translate runtime failures into persisted run state and stream events."""

    def __init__(
        self,
        *,
        run_store: AgentRunStore,
        event_recorder: EventRecorder,
        metrics_collector: MetricsCollector,
    ) -> None:
        self._run_store = run_store
        self._event_recorder = event_recorder
        self._metrics_collector = metrics_collector

    def mark_cancelled(
        self,
        context: RuntimeContext,
    ) -> None:
        self._run_store.update_run(
            context.run_id,
            status="cancelled",
            error_message="Agent run cancelled",
        )
        self._event_recorder.record(
            context.run_id,
            event_type="cancelled",
            stage="cancelled",
            message="Agent run cancelled",
            payload={"runtime_safety": context.safety_config.to_dict()},
        )
        self._metrics_collector.persist(context.run_id)

    def timeout_event(self, context: RuntimeContext, exc: TimeoutError) -> list[AgentRuntimeEvent]:
        error_message = str(exc) or (
            f"Agent run timed out after {context.safety_config.run_timeout_seconds:g} seconds"
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
            message=f"Run timed out: {error_message}",
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

    def error_event(self, context: RuntimeContext, exc: Exception) -> list[AgentRuntimeEvent]:
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
            message=f"Run failed: {error_message}",
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


class AgentOrchestrator:
    """Coordinate a complete Agent run while AgentRuntime remains the public facade."""

    def __init__(self, runtime: AgentRuntime) -> None:
        self._runtime = runtime

    async def execute(
        self,
        **kwargs: Any,
    ) -> AsyncGenerator[AgentRuntimeEvent, None]:
        async for event in self._runtime._run_orchestration(**kwargs):
            yield event


class AgentRuntime:
    """Run a scene-scoped native SRE agent workflow."""

    def __init__(
        self,
        *,
        tool_catalog: Any | None = None,
        tool_executor: Any | None = None,
        scene_store: SceneStore | None = None,
        run_store: AgentRunStore | None = None,
        policy_store: ToolPolicyStore | None = None,
        planner: AgentPlanner | None = None,
        policy_gate: ToolPolicyGate | None = None,
        action_executor: AgentToolExecutor | None = None,
        synthesizer: ReportSynthesizer | None = None,
        knowledge_context_provider: KnowledgeContextProvider | None = None,
        decision_runtime: AgentDecisionRuntime | None = None,
    ) -> None:
        self._scene_store = _required_dependency(scene_store, "scene_store")
        self._run_store = _required_dependency(run_store, "run_store")
        self._policy_store = _required_dependency(policy_store, "policy_store")
        self._event_recorder = EventRecorder(self._run_store)
        self._metrics_collector = MetricsCollector(self._run_store)
        self._tool_catalog = tool_catalog or ToolCatalog()
        tool_executor = tool_executor or ToolExecutor(policy_store=self._policy_store)
        self._planner = planner or AgentPlanner()
        self._policy_gate = policy_gate or ToolPolicyGate(policy_store=self._policy_store)
        self._action_executor = action_executor or AgentToolExecutor(tool_executor=tool_executor)
        self._synthesizer = synthesizer or ReportSynthesizer()
        self._knowledge_context_provider = knowledge_context_provider or KnowledgeContextProvider()
        self._decision_runtime = decision_runtime or AgentDecisionRuntime()
        self._step_runner = StepRunner(self)
        self._approval_boundary = ApprovalBoundary(
            run_store=self._run_store,
            event_recorder=self._event_recorder,
            metrics_collector=self._metrics_collector,
        )
        self._failure_handler = RuntimeFailureHandler(
            run_store=self._run_store,
            event_recorder=self._event_recorder,
            metrics_collector=self._metrics_collector,
        )
        self._orchestrator = AgentOrchestrator(self)

    async def run(
        self,
        *,
        scene_id: str,
        session_id: str,
        goal: str,
        principal: Any,
        success_criteria: list[str] | None = None,
        stop_condition: dict[str, Any] | None = None,
        priority: str = "P2",
    ) -> AsyncGenerator[AgentRuntimeEvent, None]:
        """Execute an auditable diagnosis run."""
        async for event in self._orchestrator.execute(
            scene_id=scene_id,
            session_id=session_id,
            goal=goal,
            principal=principal,
            success_criteria=success_criteria,
            stop_condition=stop_condition,
            priority=priority,
        ):
            yield event

    async def _run_orchestration(
        self,
        *,
        scene_id: str,
        session_id: str,
        goal: str,
        principal: Any,
        success_criteria: list[str] | None = None,
        stop_condition: dict[str, Any] | None = None,
        priority: str = "P2",
    ) -> AsyncGenerator[AgentRuntimeEvent, None]:
        """Execute an auditable diagnosis run.

        If any unexpected exception occurs, the run is marked as ``failed``
        and an ``error`` event is persisted and yielded so callers can handle
        the failure gracefully.
        """
        scene = self._scene_store.get_scene(scene_id)
        if scene is None:
            raise ValueError(f"Scene not found: {scene_id}")

        safety_config = RuntimeSafetyConfig.from_scene(scene)
        deadline = RuntimeDeadline.start(safety_config.run_timeout_seconds)
        run_id = self._run_store.create_run(
            workspace_id=str(scene["workspace_id"]),
            scene_id=scene_id,
            session_id=session_id,
            goal=goal,
        )
        runtime_context = RuntimeContext(
            run_id=run_id,
            scene_id=scene_id,
            workspace_id=str(scene["workspace_id"]),
            session_id=session_id,
            goal=goal,
            success_criteria=success_criteria or [],
            stop_condition=stop_condition or {},
            priority=_priority_or_default(priority),
            safety_config=safety_config,
            deadline=deadline,
        )

        try:
            yield self._record_event(
                runtime_context.run_id,
                event_type="run_started",
                stage="start",
                message="Agent run started",
                payload={
                    "scene_id": runtime_context.scene_id,
                    "workspace_id": runtime_context.workspace_id,
                    "goal": runtime_context.goal,
                    "success_criteria": runtime_context.success_criteria,
                    "stop_condition": runtime_context.stop_condition,
                    "priority": runtime_context.priority,
                    "runtime_safety": runtime_context.safety_config.to_dict(),
                },
            )

            deadline.ensure_available()
            state = self._planner.create_initial_state(goal)
            yield self._record_event(
                run_id,
                event_type="hypothesis",
                stage="reasoning",
                message=state.hypothesis.summary,
                payload={"hypothesis": state.hypothesis.summary},
            )
            knowledge_context = self._knowledge_context_provider.build_context(scene)
            state.set_knowledge_context(knowledge_context)
            if knowledge_context.has_knowledge():
                yield self._record_event(
                    run_id,
                    event_type="knowledge_context",
                    stage="context",
                    message=knowledge_context.summary,
                    payload=knowledge_context.to_event_payload(),
                )

            selected_tool_names = self._planner.select_tool_names(scene)
            decision_runtime_enabled = _decision_runtime_enabled(scene)
            if decision_runtime_enabled:
                decision_state = build_initial_decision_state(
                    run_id=run_id,
                    goal=goal,
                    workspace_id=str(scene["workspace_id"]),
                    scene_id=scene_id,
                    available_tools=selected_tool_names,
                    success_criteria=success_criteria,
                    stop_condition=_stop_condition_from_payload(stop_condition),
                    priority=_priority_or_default(priority),
                    budget=RuntimeBudget(
                        max_steps=safety_config.max_steps,
                        remaining_steps=safety_config.max_steps,
                        max_tool_calls=max(len(selected_tool_names), 1),
                        remaining_tool_calls=len(selected_tool_names),
                        run_timeout_seconds=safety_config.run_timeout_seconds,
                        remaining_seconds=max(deadline.remaining_seconds(), 0),
                    ),
                )
                try:
                    decision_state = self._decision_runtime.run_graph_once(decision_state)
                except Exception as exc:
                    logger.warning(
                        "Decision graph execution failed; falling back to direct provider: {exc}",
                        exc=exc,
                    )
                    decision_state = self._decision_runtime.decide_once(decision_state)
                for observation in decision_state.observations:
                    yield self._record_event(
                        run_id,
                        event_type="observation",
                        stage="observe",
                        message=observation.summary,
                        payload=observation.model_dump(mode="json"),
                    )
                latest_decision = decision_state.decisions[-1]
                yield self._record_event(
                    run_id,
                    event_type="decision",
                    stage="decision",
                    message=latest_decision.reasoning_summary,
                    payload={
                        "checkpoint_ns": self._decision_runtime.checkpoint_ns,
                        "decision": latest_decision.to_event_payload(),
                        "state_status": decision_state.status,
                    },
                )

            selected_tool_names, skipped_tool_names = _limit_tool_steps(
                selected_tool_names,
                max_steps=safety_config.max_steps,
            )
            if skipped_tool_names:
                yield self._record_event(
                    run_id,
                    event_type="limit_reached",
                    stage="planning",
                    message="Tool step limit reached",
                    payload={
                        "max_steps": safety_config.max_steps,
                        "executed_tools": selected_tool_names,
                        "skipped_tools": skipped_tool_names,
                    },
                )

            if not selected_tool_names:
                final_report = self._synthesizer.unavailable_report(
                    goal,
                    state.knowledge_context,
                )
                self._run_store.update_run(run_id, status="completed", final_report=final_report)
                yield self._record_event(
                    run_id,
                    event_type="final_report",
                    stage="complete",
                    message="Final report generated",
                    payload={"report": final_report},
                )
                self._persist_run_metrics(run_id)
                yield AgentRuntimeEvent(
                    type="complete",
                    stage="complete",
                    run_id=run_id,
                    status="completed",
                    final_report=final_report,
                )
                return

            deadline.ensure_available()
            tools = await asyncio.wait_for(
                self._tool_catalog.get_tools("diagnosis"),
                timeout=deadline.remaining_seconds(),
            )
            tool_by_name = {
                str(getattr(tool, "name", "")): tool
                for tool in tools
                if str(getattr(tool, "name", "")) in selected_tool_names
            }

            if not tool_by_name:
                final_report = self._synthesizer.unavailable_report(
                    goal,
                    state.knowledge_context,
                )
                self._run_store.update_run(run_id, status="completed", final_report=final_report)
                yield self._record_event(
                    run_id,
                    event_type="final_report",
                    stage="complete",
                    message="Final report generated",
                    payload={"report": final_report},
                )
                self._persist_run_metrics(run_id)
                yield AgentRuntimeEvent(
                    type="complete",
                    stage="complete",
                    run_id=run_id,
                    status="completed",
                    final_report=final_report,
                )
                return

            strong_evidence_found = False
            for tool_name in selected_tool_names:
                deadline.ensure_available()
                tool = tool_by_name.get(tool_name)
                if tool is None:
                    continue
                action = self._policy_gate.create_action(tool_name, goal=state.goal)
                state.add_action(action)
                yield self._record_event(
                    run_id,
                    event_type="tool_call",
                    stage="tool",
                    message=f"Calling tool: {tool_name}",
                    payload=action.to_event_payload(),
                )
                result = await self._step_runner.execute_tool(
                    tool,
                    action,
                    principal=principal,
                    safety_config=safety_config,
                    deadline=deadline,
                )
                yield self._record_event(
                    run_id,
                    event_type="tool_result",
                    stage="tool",
                    message=f"Tool {result.tool_name} finished with status {result.status}",
                    payload=action.result_event_payload(result),
                )
                evidence_item = EvidenceItem.from_tool_result(result)
                state.add_evidence(evidence_item)
                if decision_runtime_enabled:
                    assessment = _assess_evidence_item(evidence_item)
                    yield self._record_event(
                        run_id,
                        event_type="evidence_assessment",
                        stage="evidence",
                        message=assessment.summary,
                        payload=assessment.model_dump(mode="json"),
                    )
                    if evidence_item.status == "approval_required":
                        for event in self._approval_boundary.pause(
                            runtime_context,
                            tool_name=tool_name,
                            payload=action.result_event_payload(result),
                        ):
                            yield event
                        return
                    if assessment.quality in {"empty", "error", "conflicting"}:
                        reason = _handoff_reason_from_evidence(assessment)
                        recovery = RecoveryDecision(
                            required=True,
                            reason=reason,
                            next_action="handoff",
                        )
                        yield self._record_event(
                            run_id,
                            event_type="recovery",
                            stage="recover",
                            message=f"Recovery required: {reason}",
                            payload=recovery.model_dump(mode="json"),
                        )
                        report_contract = FinalReportContract(
                            summary=(
                                "Evidence is not strong enough for a safe autonomous "
                                "conclusion, so the run is handing off to a human."
                            ),
                            verified_facts=[],
                            inferences=[
                                (
                                    "The current tool result did not provide enough "
                                    "verified evidence to confirm a root cause."
                                ),
                            ],
                            recommendations=[
                                (
                                    "Have an operator inspect the cited tool output, "
                                    "collect additional evidence, and resume the run "
                                    "only after the boundary condition is understood."
                                ),
                            ],
                            citations=assessment.citations,
                            confidence=assessment.confidence,
                            handoff_required=True,
                            handoff_reason=reason,
                        )
                        final_report = _handoff_report(goal, report_contract)
                        self._run_store.update_run(
                            run_id,
                            status="handoff_required",
                            final_report=final_report,
                            error_message=reason,
                        )
                        yield self._record_event(
                            run_id,
                            event_type="handoff",
                            stage="handoff",
                            message="Agent run requires human handoff",
                            payload=report_contract.to_event_payload(),
                        )
                        self._persist_run_metrics(run_id)
                        yield AgentRuntimeEvent(
                            type="handoff",
                            stage="handoff",
                            run_id=run_id,
                            status="handoff_required",
                            final_report=final_report,
                        )
                        return
                    if assessment.quality == "strong":
                        strong_evidence_found = True
                        final_decision = AgentDecision(
                            action_type="final_report",
                            reasoning_summary=(
                                "Strong evidence is available and can support a final report."
                            ),
                            evidence=assessment,
                            actual_evidence=assessment,
                            confidence=max(assessment.confidence, 0.8),
                        )
                        yield self._record_event(
                            run_id,
                            event_type="decision",
                            stage="decision",
                            message=final_decision.reasoning_summary,
                            payload={
                                "checkpoint_ns": self._decision_runtime.checkpoint_ns,
                                "decision": final_decision.to_event_payload(),
                                "state_status": "completed",
                            },
                        )
                        break
                deadline.ensure_available()

            deadline.ensure_available()
            if decision_runtime_enabled and skipped_tool_names and not strong_evidence_found:
                recovery = RecoveryDecision(
                    required=True,
                    reason="budget_exhausted",
                    next_action="handoff",
                )
                yield self._record_event(
                    run_id,
                    event_type="recovery",
                    stage="recover",
                    message="Recovery required: budget_exhausted",
                    payload=recovery.model_dump(mode="json"),
                )
                report_contract = FinalReportContract(
                    summary=(
                        "The execution budget is exhausted and the available evidence "
                        "is not sufficient for a safe final conclusion."
                    ),
                    verified_facts=state.evidence_report_lines(),
                    inferences=[
                        (
                            "Some scene-approved tools were skipped because the "
                            "runtime boundary was reached."
                        ),
                    ],
                    recommendations=[
                        (
                            "Increase the run budget or narrow the scene tool set, "
                            "then resume with the remaining evidence requirements."
                        ),
                    ],
                    confidence=0.3,
                    handoff_required=True,
                    handoff_reason="budget_exhausted",
                )
                final_report = _handoff_report(goal, report_contract)
                self._run_store.update_run(
                    run_id,
                    status="handoff_required",
                    final_report=final_report,
                    error_message="budget_exhausted",
                )
                yield self._record_event(
                    run_id,
                    event_type="handoff",
                    stage="handoff",
                    message="Agent run requires human handoff",
                    payload=report_contract.to_event_payload(),
                )
                self._persist_run_metrics(run_id)
                yield AgentRuntimeEvent(
                    type="handoff",
                    stage="handoff",
                    run_id=run_id,
                    status="handoff_required",
                    final_report=final_report,
                )
                return

            final_report = (
                self._synthesizer.build_bounded_report(
                    state,
                    max_steps=safety_config.max_steps,
                    executed_tools=selected_tool_names,
                    skipped_tools=skipped_tool_names,
                )
                if skipped_tool_names
                else self._synthesizer.build_report(state)
            )
            self._run_store.update_run(run_id, status="completed", final_report=final_report)
            yield self._record_event(
                run_id,
                event_type="final_report",
                stage="complete",
                message="Final report generated",
                payload={"report": final_report},
            )
            self._persist_run_metrics(run_id)
            yield AgentRuntimeEvent(
                type="complete",
                stage="complete",
                run_id=run_id,
                status="completed",
                final_report=final_report,
            )

        except asyncio.CancelledError:
            self._failure_handler.mark_cancelled(runtime_context)
            raise
        except TimeoutError as exc:
            error_message = str(exc) or (
                f"Agent run timed out after {safety_config.run_timeout_seconds:g} seconds"
            )
            logger.warning(
                "Agent run {run_id} timed out: {error_message}",
                run_id=run_id,
                error_message=error_message,
            )
            for event in self._failure_handler.timeout_event(runtime_context, exc):
                yield event
        except Exception as exc:
            error_type = type(exc).__name__
            error_message = str(exc)
            if isinstance(exc, TimeoutError) and not error_message:
                error_message = (
                    f"Agent run timed out after {safety_config.run_timeout_seconds:g} seconds"
                )
            logger.error(
                "Agent run {run_id} failed: {error_type}: {error_message}",
                run_id=run_id,
                error_type=error_type,
                error_message=error_message,
                exc_info=True,
            )

            for event in self._failure_handler.error_event(runtime_context, exc):
                yield event

    async def _execute_tool_with_timeout(
        self,
        tool: Any,
        action: Any,
        *,
        principal: Any,
        safety_config: RuntimeSafetyConfig,
        deadline: RuntimeDeadline,
    ) -> Any:
        remaining_seconds = deadline.remaining_seconds()
        if remaining_seconds <= 0:
            raise TimeoutError(f"Agent run timed out after {deadline.timeout_seconds:g} seconds")

        timeout_seconds = min(safety_config.tool_timeout_seconds, remaining_seconds)
        try:
            with _optional_span(
                "agent.tool_call",
                {
                    "agent.tool_name": str(action.tool_name),
                    "agent.run_timeout_seconds": deadline.timeout_seconds,
                    "agent.tool_timeout_seconds": timeout_seconds,
                },
            ):
                return await asyncio.wait_for(
                    self._action_executor.execute(
                        tool,
                        action,
                        principal=principal,
                    ),
                    timeout=timeout_seconds,
                )
        except TimeoutError:
            return ToolExecutionResult(
                tool_name=action.tool_name,
                status="timeout",
                arguments=action.arguments,
                error=f"Tool execution timed out after {timeout_seconds:g} seconds",
                policy=action.policy_snapshot.to_dict(),
                decision="timeout",
                decision_reason=f"Tool execution exceeded timeout: {timeout_seconds:g} seconds",
            )

    def _record_event(
        self,
        run_id: str,
        *,
        event_type: str,
        stage: str,
        message: str,
        payload: dict[str, Any],
    ) -> AgentRuntimeEvent:
        return self._event_recorder.record(
            run_id,
            event_type=event_type,
            stage=stage,
            message=message,
            payload=payload,
        )

    def _persist_run_metrics(self, run_id: str) -> None:
        self._metrics_collector.persist(run_id)


def _positive_int(value: Any, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _required_dependency(value: Any | None, name: str) -> Any:
    if value is None:
        raise ValueError(
            f"AgentRuntime requires explicit {name}; construct it through "
            "app.api.providers.get_agent_runtime() or pass a test adapter."
        )
    return value


def _positive_float(value: Any, *, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _stop_condition_from_payload(payload: dict[str, Any] | None) -> StopCondition | None:
    if not payload:
        return None
    try:
        return StopCondition.model_validate(payload)
    except Exception:
        return None


def _priority_or_default(value: str) -> Priority:
    if value in {"P0", "P1", "P2", "P3"}:
        return cast(Priority, value)
    return "P2"


def _limit_tool_steps(
    selected_tool_names: list[str],
    *,
    max_steps: int,
) -> tuple[list[str], list[str]]:
    return selected_tool_names[:max_steps], selected_tool_names[max_steps:]


def _decision_runtime_enabled(scene: dict[str, Any]) -> bool:
    agent_config = scene.get("agent_config")
    if not isinstance(agent_config, dict):
        return True
    value = agent_config.get("decision_runtime_enabled")
    return value if value is not None else True


def _runtime_model_name() -> str:
    provider = config.agent_decision_provider.strip().lower()
    if provider == "qwen":
        return config.dashscope_model
    return "deterministic-native-agent"


def _runtime_decision_provider() -> str:
    provider = config.agent_decision_provider.strip().lower()
    return provider or "deterministic"


def _assess_evidence_item(evidence: EvidenceItem) -> EvidenceAssessment:
    citation = {
        "source": "tool",
        "tool_name": evidence.tool_name,
        "status": evidence.status,
    }
    if evidence.status in {"timeout", "disabled", "forbidden"} or evidence.error:
        return EvidenceAssessment(
            quality="error",
            summary=f"{evidence.tool_name} returned {evidence.status}: {evidence.error or 'no detail'}",
            citations=[citation],
            confidence=0.0,
        )
    if evidence.status == "approval_required":
        return EvidenceAssessment(
            quality="partial",
            summary=f"{evidence.tool_name} requires approval before evidence can be collected.",
            citations=[citation],
            confidence=0.2,
        )
    if evidence.status == "partial":
        return EvidenceAssessment(
            quality="partial",
            summary=f"{evidence.tool_name} returned partial evidence.",
            citations=[citation],
            confidence=0.4,
        )
    if evidence.output in {None, ""}:
        return EvidenceAssessment(
            quality="empty",
            summary=f"{evidence.tool_name} returned no usable evidence.",
            citations=[citation],
            confidence=0.0,
        )
    return EvidenceAssessment(
        quality="strong",
        summary=f"{evidence.tool_name} returned usable evidence.",
        citations=[citation],
        confidence=0.8,
    )


def _handoff_reason_from_evidence(assessment: EvidenceAssessment) -> str:
    if assessment.quality == "empty":
        return "insufficient_evidence"
    if assessment.quality == "conflicting":
        return "conflicting_evidence"
    return "evidence_error"


def _handoff_report(goal: str, report: FinalReportContract) -> str:
    lines = [
        f"# Agent Handoff Report: {goal}",
        "",
        report.summary,
        "",
        f"- handoff_reason: {report.handoff_reason or 'unknown'}",
        f"- confidence: {report.confidence:.2f}",
    ]
    if report.inferences:
        lines.extend(["", "## Inferences", *[f"- {item}" for item in report.inferences]])
    if report.recommendations:
        lines.extend(["", "## Recommendations", *[f"- {item}" for item in report.recommendations]])
    return "\n".join(lines)


@contextmanager
def _optional_span(name: str, attributes: dict[str, Any]):
    try:
        from opentelemetry import trace
    except Exception:
        with nullcontext():
            yield
        return

    with trace.get_tracer("smartsre.agent_runtime").start_as_current_span(name) as span:
        for key, value in attributes.items():
            span.set_attribute(key, value)
        yield


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


def _latency_ms(created_at: Any, updated_at: Any) -> int | None:
    if created_at is None or updated_at is None:
        return None
    try:
        return int((updated_at - created_at).total_seconds() * 1000)
    except AttributeError:
        return None
