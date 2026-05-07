"""Native SRE Agent runtime.

The development runtime keeps reasoning deterministic and auditable: it builds
a small hypothesis set, executes scene-approved tools through the harness, and
persists every step as trajectory events.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from time import monotonic
from typing import Any

from loguru import logger

from app.agent_runtime.context import KnowledgeContextProvider
from app.agent_runtime.decision import (
    AgentDecisionRuntime,
    RuntimeBudget,
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
from app.platform.persistence import (
    agent_run_repository,
    scene_repository,
    tool_policy_repository,
)


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
        self._scene_store = scene_store or scene_repository
        self._run_store = run_store or agent_run_repository
        self._policy_store = policy_store or tool_policy_repository
        self._tool_catalog = tool_catalog or ToolCatalog()
        tool_executor = tool_executor or ToolExecutor(policy_store=self._policy_store)
        self._planner = planner or AgentPlanner()
        self._policy_gate = policy_gate or ToolPolicyGate(policy_store=self._policy_store)
        self._action_executor = action_executor or AgentToolExecutor(tool_executor=tool_executor)
        self._synthesizer = synthesizer or ReportSynthesizer()
        self._knowledge_context_provider = knowledge_context_provider or KnowledgeContextProvider()
        self._decision_runtime = decision_runtime or AgentDecisionRuntime()

    async def run(
        self,
        *,
        scene_id: str,
        session_id: str,
        goal: str,
        principal: Any,
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

        try:
            yield self._record_event(
                run_id,
                event_type="run_started",
                stage="start",
                message="Agent run started",
                payload={
                    "scene_id": scene_id,
                    "workspace_id": scene["workspace_id"],
                    "goal": goal,
                    "runtime_safety": safety_config.to_dict(),
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
            if _decision_runtime_enabled(scene):
                decision_state = build_initial_decision_state(
                    run_id=run_id,
                    goal=goal,
                    workspace_id=str(scene["workspace_id"]),
                    scene_id=scene_id,
                    available_tools=selected_tool_names,
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
                result = await self._execute_tool_with_timeout(
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
                state.add_evidence(EvidenceItem.from_tool_result(result))
                deadline.ensure_available()

            deadline.ensure_available()
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
            self._run_store.update_run(
                run_id,
                status="cancelled",
                error_message="Agent run cancelled",
            )
            self._record_event(
                run_id,
                event_type="cancelled",
                stage="cancelled",
                message="Agent run cancelled",
                payload={
                    "runtime_safety": safety_config.to_dict(),
                },
            )
            self._persist_run_metrics(run_id)
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
            self._run_store.update_run(
                run_id,
                status="failed",
                error_message=f"TimeoutError: {error_message}",
            )
            yield self._record_event(
                run_id,
                event_type="timeout",
                stage="error",
                message=f"Run timed out: {error_message}",
                payload={
                    "error_type": "TimeoutError",
                    "error_message": error_message,
                    "timeout_scope": "run",
                    "runtime_safety": safety_config.to_dict(),
                },
            )
            self._persist_run_metrics(run_id)
            yield AgentRuntimeEvent(
                type="timeout",
                stage="error",
                run_id=run_id,
                status="failed",
                message=f"TimeoutError: {error_message}",
            )
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

            self._run_store.update_run(
                run_id,
                status="failed",
                error_message=f"{error_type}: {error_message}",
            )
            yield self._record_event(
                run_id,
                event_type="error",
                stage="error",
                message=f"Run failed: {error_message}",
                payload={
                    "error_type": error_type,
                    "error_message": error_message,
                    "runtime_safety": safety_config.to_dict(),
                },
            )
            self._persist_run_metrics(run_id)
            yield AgentRuntimeEvent(
                type="error",
                stage="error",
                run_id=run_id,
                status="failed",
                message=f"{error_type}: {error_message}",
            )

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

    def _persist_run_metrics(self, run_id: str) -> None:
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
                step_count=_metric_step_count(events),
                tool_call_count=len(_events_by_type(events, "tool_call")),
                latency_ms=_latency_ms(run.get("created_at"), run.get("updated_at")),
                error_type=_metric_error_type(run, events),
                approval_state=_metric_approval_state(events),
                retrieval_count=len(_events_by_type(events, "knowledge_context")),
                token_usage=None,
            )
        except Exception as exc:
            logger.warning(f"Failed to persist agent run metrics for {run_id}: {exc}")


def _positive_int(value: Any, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _positive_float(value: Any, *, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


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


def _latency_ms(created_at: Any, updated_at: Any) -> int | None:
    if created_at is None or updated_at is None:
        return None
    try:
        return int((updated_at - created_at).total_seconds() * 1000)
    except AttributeError:
        return None
