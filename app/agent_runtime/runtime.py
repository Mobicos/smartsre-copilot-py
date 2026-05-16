"""Native SRE Agent runtime.

The runtime keeps reasoning deterministic and auditable around the model-facing
decision layer: it builds an explicit state, routes scene-approved tools through
policy gates, assesses evidence, and persists every step as replayable events.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass, replace
from time import monotonic
from types import SimpleNamespace
from typing import Any, cast

from loguru import logger

from app.agent_runtime.approval import ApprovalGate
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
from app.agent_runtime.evidence import EvidenceAssessor
from app.agent_runtime.executor import AgentToolExecutor
from app.agent_runtime.guardrails import sanitize_goal
from app.agent_runtime.loop import BoundedReActLoop, LoopBudget, LoopResult, LoopStep
from app.agent_runtime.metrics_collector import MetricsCollector
from app.agent_runtime.planner import AgentPlanner
from app.agent_runtime.policy import ToolPolicyGate
from app.agent_runtime.ports import AgentMemoryStore, AgentRunStore, SceneStore, ToolPolicyStore
from app.agent_runtime.recovery import RecoveryManager
from app.agent_runtime.state import AgentRunState, EvidenceItem
from app.agent_runtime.synthesizer import ReportSynthesizer
from app.agent_runtime.tool_catalog import ToolCatalog
from app.agent_runtime.tool_executor import ToolExecutionResult, ToolExecutor
from app.agent_runtime.trace_collector import TraceCollector
from app.core.config import AppSettings


@dataclass(frozen=True)
class RuntimeSafetyConfig:
    """Bounded execution defaults for one Native Agent run."""

    max_steps: int = 5
    tool_timeout_seconds: float = 30.0
    run_timeout_seconds: float = 120.0

    @classmethod
    def from_scene(
        cls,
        scene: dict[str, Any],
        settings: AppSettings | None = None,
    ) -> RuntimeSafetyConfig:
        settings = settings or AppSettings.from_env()
        agent_config = scene.get("agent_config")
        if not isinstance(agent_config, dict):
            agent_config = {}

        defaults = cls(
            max_steps=_positive_int(settings.agent_max_steps, default=cls.max_steps),
            tool_timeout_seconds=_positive_float(
                settings.agent_step_timeout_seconds,
                default=cls.tool_timeout_seconds,
            ),
            run_timeout_seconds=_positive_float(
                settings.agent_total_timeout_seconds,
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

    def record_loop_step(self, run_id: str, step: LoopStep) -> AgentRuntimeEvent:
        """Persist one loop decision step with event-level AgentOps metrics."""

        payload = {
            **step.metrics,
            "decision": step.decision.to_event_payload(),
        }
        return self.record(
            run_id,
            event_type="decision",
            stage="decision",
            message=step.decision.reasoning_summary,
            payload=payload,
        )


class DecisionRuntimeProviderAdapter:
    """Expose AgentDecisionRuntime's provider as the bounded-loop provider seam."""

    provider_name = "decision_runtime"

    def __init__(self, decision_runtime: AgentDecisionRuntime) -> None:
        self._decision_runtime = decision_runtime

    def decide(self, state: Any) -> AgentDecision:
        provider = self._decision_runtime.provider
        return provider.decide(state)

    def get_token_usage(self) -> dict[str, Any]:
        provider = self._decision_runtime.provider
        get_token_usage = getattr(provider, "get_token_usage", None)
        return cast(dict[str, Any], get_token_usage()) if callable(get_token_usage) else {}

    def get_cost_estimate(self) -> dict[str, Any]:
        provider = self._decision_runtime.provider
        get_cost_estimate = getattr(provider, "get_cost_estimate", None)
        return cast(dict[str, Any], get_cost_estimate()) if callable(get_cost_estimate) else {}


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
            await self._runtime.execute_tool_with_timeout(
                tool,
                action,
                principal=principal,
                safety_config=safety_config,
                deadline=deadline,
            ),
        )


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
        settings: AppSettings | None = None,
        *,
        tool_catalog: Any | None = None,
        tool_executor: Any | None = None,
        scene_store: SceneStore | None = None,
        run_store: AgentRunStore | None = None,
        policy_store: ToolPolicyStore | None = None,
        memory_store: AgentMemoryStore | None = None,
        planner: AgentPlanner | None = None,
        policy_gate: ToolPolicyGate | None = None,
        action_executor: AgentToolExecutor | None = None,
        synthesizer: ReportSynthesizer | None = None,
        knowledge_context_provider: KnowledgeContextProvider | None = None,
        decision_runtime: AgentDecisionRuntime | None = None,
    ) -> None:
        self._settings = settings or AppSettings.from_env()
        self._scene_store = _required_dependency(scene_store, "scene_store")
        self._run_store = _required_dependency(run_store, "run_store")
        self._policy_store = _required_dependency(policy_store, "policy_store")
        self._memory_store = memory_store
        self._event_recorder = EventRecorder(self._run_store)
        self._metrics_collector = MetricsCollector(self._run_store, self._settings)
        self._tool_catalog = tool_catalog or ToolCatalog()
        tool_executor = tool_executor or ToolExecutor(policy_store=self._policy_store)
        self._planner = planner or AgentPlanner()
        self._policy_gate = policy_gate or ToolPolicyGate(policy_store=self._policy_store)
        self._action_executor = action_executor or AgentToolExecutor(tool_executor=tool_executor)
        self._synthesizer = synthesizer or ReportSynthesizer()
        self._evidence_assessor = EvidenceAssessor()
        self._knowledge_context_provider = knowledge_context_provider or KnowledgeContextProvider()
        self._decision_runtime = decision_runtime or AgentDecisionRuntime()
        self._trace_collector = TraceCollector()
        self._step_runner = StepRunner(self)
        self._approval_boundary = ApprovalGate(
            run_store=self._run_store,
            event_recorder=self._event_recorder,
            metrics_collector=self._metrics_collector,
        )
        self._failure_handler = RecoveryManager(
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
        goal = sanitize_goal(goal)

        scene = self._scene_store.get_scene(scene_id)
        if scene is None:
            raise ValueError(f"Scene not found: {scene_id}")

        safety_config = RuntimeSafetyConfig.from_scene(scene, self._settings)
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
                message="Agent 运行已启动",
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
            memories = self._search_memory(runtime_context)
            if memories:
                yield self._record_event(
                    run_id,
                    event_type="memory_context",
                    stage="context",
                    message=f"已检索到历史记忆 {len(memories)} 条。",
                    payload={"memories": memories},
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
                if _bounded_react_loop_enabled(scene):
                    loop = BoundedReActLoop(
                        provider=DecisionRuntimeProviderAdapter(self._decision_runtime),
                        trace_collector=self._trace_collector,
                        recovery_manager=self._failure_handler,
                        tool_executor=self._make_loop_tool_executor(
                            principal=principal,
                            safety_config=safety_config,
                            deadline=deadline,
                        ),
                        evidence_assessor=self._evidence_assessor,
                    )
                    loop_result = loop.run(
                        decision_state,
                        LoopBudget(
                            max_steps=safety_config.max_steps,
                            max_time_seconds=max(deadline.remaining_seconds(), 0.001),
                        ),
                    )
                    decision_state = loop_result.state
                    for fallback_payload in loop.consume_provider_fallback_events():
                        yield self._record_event(
                            run_id,
                            event_type="provider_fallback",
                            stage="decision",
                            message=(
                                "决策 Provider 不可用，"
                                f"已降级到 {fallback_payload.get('to_provider')}"
                            ),
                            payload=fallback_payload,
                        )
                    for step in loop_result.steps:
                        yield self._event_recorder.record_loop_step(run_id, step)

                    # --- approval_required: pause and wait ---
                    if loop_result.termination_reason == "approval_required":
                        last_step = loop_result.steps[-1] if loop_result.steps else None
                        tool_name = (
                            last_step.decision.selected_tool if last_step and last_step.decision.selected_tool else "unknown"
                        )
                        tool_result = last_step.tool_result if last_step else None
                        for event in self._approval_boundary.pause(
                            runtime_context,
                            tool_name=tool_name,
                            payload=(
                                tool_result.governance_payload()
                                if tool_result and hasattr(tool_result, "governance_payload")
                                else {}
                            ),
                        ):
                            yield event
                        return

                    # --- handoff: persist and return ---
                    if loop_result.termination_reason == "handoff":
                        last_decision = decision_state.decisions[-1] if decision_state.decisions else None
                        reason = (
                            (last_decision.handoff_reason or last_decision.recovery.reason or "证据不足")
                            if last_decision
                            else "证据不足"
                        )
                        report_contract = FinalReportContract(
                            summary="证据不足以得出安全的自主结论，因此运行交由人工处理。",
                            verified_facts=[],
                            inferences=["当前工具结果未提供足够的经验证证据来确认根因。"],
                            recommendations=[
                                "请运维人员检查引用的工具输出，收集额外证据，并在理解边界条件后恢复运行。"
                            ],
                            citations=[],
                            confidence=0.3,
                            handoff_required=True,
                            handoff_reason=reason,
                        )
                        final_report = _handoff_report(goal, report_contract)
                        self._run_store.update_run(
                            run_id, status="handoff_required",
                            final_report=final_report, error_message=reason,
                        )
                        self._persist_run_memory(
                            runtime_context, final_report,
                            conclusion_type="handoff", confidence=0.3,
                            metadata={"handoff_reason": reason},
                        )
                        yield self._record_event(
                            run_id, event_type="handoff", stage="handoff",
                            message="Agent 运行需要人工交接",
                            payload=report_contract.to_event_payload(),
                        )
                        self._persist_run_metrics(run_id)
                        yield AgentRuntimeEvent(
                            type="handoff", stage="handoff", run_id=run_id,
                            status="handoff_required", final_report=final_report,
                        )
                        return

                    # --- normal / final_report / max_steps: generate report ---
                    evidence_items = list(loop_result.evidence_items)
                    state_for_report = AgentRunState.from_goal(goal)
                    for item in evidence_items:
                        state_for_report.add_evidence(item)
                    state_for_report.set_knowledge_context(
                        self._knowledge_context_provider.build_context(scene)
                    )
                    final_report = ReportSynthesizer.build_report(state_for_report)
                    self._run_store.update_run(run_id, status="completed", final_report=final_report)
                    self._persist_run_memory(runtime_context, final_report)
                    yield self._record_event(
                        run_id, event_type="final_report", stage="complete",
                        message="最终报告已生成",
                        payload={"report": final_report},
                    )
                    self._persist_run_metrics(run_id)
                    yield AgentRuntimeEvent(
                        type="complete", stage="complete", run_id=run_id,
                        status="completed", final_report=final_report,
                    )
                    return
                else:
                    try:
                        decision_state = self._decision_runtime.run_graph_once(decision_state)
                    except Exception as exc:
                        logger.warning(
                            "Decision graph execution failed; falling back to direct provider: {exc}",
                            exc=exc,
                        )
                        decision_state = self._decision_runtime.decide_once(decision_state)
                for fallback_payload in self._decision_runtime.consume_provider_fallback_events():
                    yield self._record_event(
                        run_id,
                        event_type="provider_fallback",
                        stage="decision",
                        message=(
                            f"决策 Provider 不可用，已降级到 {fallback_payload.get('to_provider')}"
                        ),
                        payload=fallback_payload,
                    )
                for observation in decision_state.observations:
                    yield self._record_event(
                        run_id,
                        event_type="observation",
                        stage="observe",
                        message=observation.summary,
                        payload=observation.model_dump(mode="json"),
                    )
                if not _bounded_react_loop_enabled(scene):
                    latest_decision = decision_state.decisions[-1]
                    yield self._record_event(
                        run_id,
                        event_type="decision",
                        stage="decision",
                        message=latest_decision.reasoning_summary,
                        payload={
                            "checkpoint_ns": self._decision_runtime.checkpoint_ns,
                            "step_index": len(decision_state.decisions) - 1,
                            "decision": latest_decision.to_event_payload(),
                            "token_usage": self._decision_runtime.get_token_usage(),
                            "cost_estimate": self._decision_runtime.get_cost_estimate(),
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
                    message="工具步骤已达上限",
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
                self._persist_run_memory(runtime_context, final_report)
                yield self._record_event(
                    run_id,
                    event_type="final_report",
                    stage="complete",
                    message="最终报告已生成",
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
                self._persist_run_memory(runtime_context, final_report)
                yield self._record_event(
                    run_id,
                    event_type="final_report",
                    stage="complete",
                    message="最终报告已生成",
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
                    message=f"正在调用工具：{tool_name}",
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
                    message=f"工具 {result.tool_name} 执行完成，状态：{result.status}",
                    payload=action.result_event_payload(result),
                )
                evidence_item = EvidenceItem.from_tool_result(result)
                state.add_evidence(evidence_item)
                if decision_runtime_enabled:
                    assessment = self._evidence_assessor.assess(evidence_item)
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
                        recovery_plan = self._failure_handler.choose_strategy(
                            evidence_quality=assessment.quality,
                            consecutive_failures=1,
                            tool_available=False,
                        )
                        reason = recovery_plan.reason or self._evidence_assessor.handoff_reason(
                            assessment
                        )
                        recovery = RecoveryDecision(
                            required=True,
                            reason=reason,
                            next_action="handoff",
                        )
                        recovery_payload = recovery.model_dump(mode="json")
                        recovery_payload["recovery_action"] = recovery_plan.action
                        yield self._record_event(
                            run_id,
                            event_type="recovery",
                            stage="recover",
                            message=f"需要恢复：{reason}",
                            payload=recovery_payload,
                        )
                        report_contract = FinalReportContract(
                            summary=("证据不足以得出安全的自主结论，因此运行交由人工处理。"),
                            verified_facts=[],
                            inferences=[
                                ("当前工具结果未提供足够的经验证证据来确认根因。"),
                            ],
                            recommendations=[
                                (
                                    "请运维人员检查引用的工具输出，收集额外证据，"
                                    "并在理解边界条件后恢复运行。"
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
                        self._persist_run_memory(
                            runtime_context,
                            final_report,
                            conclusion_type="handoff",
                            confidence=0.3,
                            metadata={"handoff_reason": reason},
                        )
                        yield self._record_event(
                            run_id,
                            event_type="handoff",
                            stage="handoff",
                            message="Agent 运行需要人工交接",
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
                            reasoning_summary=("已有充分证据支持生成最终报告。"),
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
            if decision_runtime_enabled and len(state.evidence) > 1:
                aggregate_assessment, aggregate_handoff_reason = _aggregate_runtime_evidence(
                    self._evidence_assessor,
                    state.evidence,
                )
                if aggregate_assessment.quality == "conflicting":
                    recovery_plan = self._failure_handler.choose_strategy(
                        evidence_quality=aggregate_assessment.quality,
                        consecutive_failures=1,
                        tool_available=False,
                    )
                    reason = recovery_plan.reason or aggregate_handoff_reason
                    recovery = RecoveryDecision(
                        required=True,
                        reason=reason,
                        next_action="handoff",
                    )
                    recovery_payload = recovery.model_dump(mode="json")
                    recovery_payload["recovery_action"] = recovery_plan.action
                    yield self._record_event(
                        run_id,
                        event_type="recovery",
                        stage="recover",
                        message=f"需要恢复：{reason}",
                        payload=recovery_payload,
                    )
                    report_contract = _evidence_handoff_contract(
                        assessment=aggregate_assessment,
                        reason=reason,
                    )
                    final_report = _handoff_report(goal, report_contract)
                    self._run_store.update_run(
                        run_id,
                        status="handoff_required",
                        final_report=final_report,
                        error_message=reason,
                    )
                    self._persist_run_memory(
                        runtime_context,
                        final_report,
                        conclusion_type="handoff",
                        confidence=0.3,
                        metadata={"handoff_reason": reason},
                    )
                    yield self._record_event(
                        run_id,
                        event_type="handoff",
                        stage="handoff",
                        message="Agent 运行需要人工交接",
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
                    message="需要恢复：执行预算已耗尽",
                    payload=recovery.model_dump(mode="json"),
                )
                report_contract = FinalReportContract(
                    summary=("执行预算已耗尽，现有证据不足以得出安全的最终结论。"),
                    verified_facts=state.evidence_report_lines(),
                    inferences=[
                        ("部分场景允许的工具因达到运行时边界而被跳过。"),
                    ],
                    recommendations=[
                        ("增加运行预算或缩小场景工具集，然后根据剩余证据需求恢复运行。"),
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
                self._persist_run_memory(
                    runtime_context,
                    final_report,
                    conclusion_type="handoff",
                    confidence=0.3,
                    metadata={"handoff_reason": "budget_exhausted"},
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
            self._persist_run_memory(runtime_context, final_report)
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
                f"Agent 运行超时，已运行 {safety_config.run_timeout_seconds:g} 秒"
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
            logger.error(
                "Agent run {run_id} failed: {error_type}: {error_message}",
                run_id=run_id,
                error_type=error_type,
                error_message=error_message,
                exc_info=True,
            )

            for event in self._failure_handler.error_event(runtime_context, exc):
                yield event

    async def execute_tool_with_timeout(
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
        started_at = monotonic()
        try:
            with self._trace_collector.span(
                "agent.tool_call",
                {
                    "agent.tool_name": str(action.tool_name),
                    "agent.run_timeout_seconds": deadline.timeout_seconds,
                    "agent.tool_timeout_seconds": timeout_seconds,
                },
            ):
                result = await asyncio.wait_for(
                    self._action_executor.execute(
                        tool,
                        action,
                        principal=principal,
                    ),
                    timeout=timeout_seconds,
                )
                latency_ms = _elapsed_ms(started_at)
                return _result_with_latency(result, latency_ms)
        except TimeoutError:
            latency_ms = _elapsed_ms(started_at)
            return ToolExecutionResult(
                tool_name=action.tool_name,
                status="timeout",
                arguments=action.arguments,
                error=f"工具执行超时，已运行 {timeout_seconds:g} 秒",
                policy=action.policy_snapshot.to_dict(),
                decision="timeout",
                decision_reason=f"工具执行超时：{timeout_seconds:g} 秒",
                latency_ms=latency_ms,
            )

    def _make_loop_tool_executor(
        self,
        *,
        principal: Any,
        safety_config: RuntimeSafetyConfig,
        deadline: RuntimeDeadline,
    ) -> Any:
        """Return a sync callback that executes a tool from the bounded loop.

        The callback bridges the sync loop.run() to the async tool execution
        path via a background thread with its own event loop.
        """
        import concurrent.futures

        runtime = self
        _pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)

        def _exec(decision: Any) -> Any:
            tool_name = getattr(decision, "selected_tool", None)
            if not tool_name:
                return ToolExecutionResult(
                    tool_name="unknown", status="error",
                    arguments={}, error="决策未选择工具",
                    policy={}, decision="error", decision_reason="未选择工具",
                )
            tools = _pool.submit(
                asyncio.run,
                runtime._tool_catalog.get_tools("diagnosis"),
            ).result()
            tool_by_name = {
                str(getattr(t, "name", "")): t for t in tools
            }
            tool = tool_by_name.get(tool_name)
            if tool is None:
                return ToolExecutionResult(
                    tool_name=tool_name, status="error",
                    arguments=getattr(decision, "tool_arguments", {}),
                    error=f"工具 {tool_name} 不在可用列表中",
                    policy={}, decision="denied",
                    decision_reason=f"工具 {tool_name} 不可用",
                )
            action = runtime._policy_gate.create_action(
                tool_name, goal=getattr(decision, "reasoning_summary", ""),
            )
            if getattr(decision, "tool_arguments", None):
                from dataclasses import replace as _dc_replace
                action = _dc_replace(action, arguments=decision.tool_arguments)
            result = _pool.submit(
                asyncio.run,
                runtime.execute_tool_with_timeout(
                    tool, action,
                    principal=principal,
                    safety_config=safety_config,
                    deadline=deadline,
                ),
            ).result()
            return result

        return _exec

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

    def _search_memory(self, context: RuntimeContext) -> list[dict[str, Any]]:
        if self._memory_store is None:
            return []
        try:
            return self._memory_store.search_memory(
                workspace_id=context.workspace_id,
                query=context.goal,
                limit=3,
            )
        except Exception as exc:
            logger.warning(
                "Failed to search agent memory for run {run_id}: {exc}",
                run_id=context.run_id,
                exc=exc,
            )
            return []

    def _persist_run_memory(
        self,
        context: RuntimeContext,
        final_report: str,
        *,
        conclusion_type: str = "final_report",
        confidence: float = 0.6,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if self._memory_store is None or not final_report.strip():
            return
        try:
            self._memory_store.create_memory(
                workspace_id=context.workspace_id,
                run_id=context.run_id,
                conclusion_text=_memory_excerpt(final_report),
                conclusion_type=conclusion_type,
                confidence=confidence,
                metadata={"source": "agent_run", **(metadata or {})},
            )
        except Exception as exc:
            logger.warning(
                "Failed to persist agent memory for run {run_id}: {exc}",
                run_id=context.run_id,
                exc=exc,
            )


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


def _elapsed_ms(started_at: float) -> int:
    return max(int((monotonic() - started_at) * 1000), 0)


def _result_with_latency(result: Any, latency_ms: int) -> Any:
    if isinstance(result, ToolExecutionResult):
        return result if result.latency_ms is not None else replace(result, latency_ms=latency_ms)
    if hasattr(result, "__dict__"):
        result.latency_ms = latency_ms
        return result
    return SimpleNamespace(
        tool_name=str(getattr(result, "tool_name", "")),
        status=str(getattr(result, "status", "unknown")),
        arguments=getattr(result, "arguments", {}),
        output=getattr(result, "output", result),
        error=getattr(result, "error", None),
        latency_ms=latency_ms,
    )


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


def _bounded_react_loop_enabled(scene: dict[str, Any]) -> bool:
    agent_config = scene.get("agent_config")
    if not isinstance(agent_config, dict):
        return False
    return bool(agent_config.get("bounded_react_loop_enabled"))


def _handoff_report(goal: str, report: FinalReportContract) -> str:
    lines = [
        f"# Agent 交接报告：{goal}",
        "",
        report.summary,
        "",
        f"- 交接原因：{report.handoff_reason or '未知'}",
        f"- 置信度：{report.confidence:.2f}",
    ]
    if report.inferences:
        lines.extend(["", "## 推断", *[f"- {item}" for item in report.inferences]])
    if report.recommendations:
        lines.extend(["", "## 建议", *[f"- {item}" for item in report.recommendations]])
    return "\n".join(lines)


def _aggregate_runtime_evidence(
    assessor: EvidenceAssessor,
    evidence_items: list[EvidenceItem],
) -> tuple[EvidenceAssessment, str]:
    assessment = assessor.assess_many(evidence_items)
    return assessment, assessor.handoff_reason(assessment)


def _evidence_handoff_contract(
    *,
    assessment: EvidenceAssessment,
    reason: str,
) -> FinalReportContract:
    return FinalReportContract(
        summary="证据存在冲突或不足以得出安全的自主结论，因此运行交由人工处理。",
        verified_facts=[],
        inferences=[
            "当前工具结果未提供一致的经验证据来确认根因。",
        ],
        recommendations=[
            "请运维人员检查引用的工具输出，补充验证证据后再恢复运行。",
        ],
        citations=assessment.citations,
        confidence=assessment.confidence,
        handoff_required=True,
        handoff_reason=reason,
    )


def _memory_excerpt(text: str, *, limit: int = 2000) -> str:
    normalized = text.strip()
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 3].rstrip()}..."
