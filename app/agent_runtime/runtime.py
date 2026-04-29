"""Native SRE Agent runtime.

V1 intentionally keeps reasoning deterministic and auditable: the runtime builds
a small hypothesis set, executes scene-approved tools through the harness, and
persists every step as trajectory events.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from app.agent_runtime.context import KnowledgeContextProvider
from app.agent_runtime.events import AgentRuntimeEvent
from app.agent_runtime.executor import AgentToolExecutor
from app.agent_runtime.planner import AgentPlanner
from app.agent_runtime.policy import ToolPolicyGate
from app.agent_runtime.ports import AgentRunStore, SceneStore, ToolPolicyStore
from app.agent_runtime.state import EvidenceItem
from app.agent_runtime.synthesizer import ReportSynthesizer
from app.agent_runtime.tool_catalog import ToolCatalog
from app.agent_runtime.tool_executor import ToolExecutor
from app.platform.persistence import (
    agent_run_repository,
    scene_repository,
    tool_policy_repository,
)


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

    async def run(
        self,
        *,
        scene_id: str,
        session_id: str,
        goal: str,
        principal: Any,
    ) -> AsyncGenerator[AgentRuntimeEvent, None]:
        """Execute an auditable diagnosis run."""
        scene = self._scene_store.get_scene(scene_id)
        if scene is None:
            raise ValueError(f"Scene not found: {scene_id}")

        run_id = self._run_store.create_run(
            workspace_id=str(scene["workspace_id"]),
            scene_id=scene_id,
            session_id=session_id,
            goal=goal,
        )

        yield self._record_event(
            run_id,
            event_type="run_started",
            stage="start",
            message="Agent run started",
            payload={
                "scene_id": scene_id,
                "workspace_id": scene["workspace_id"],
                "goal": goal,
            },
        )

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
            yield AgentRuntimeEvent(
                type="complete",
                stage="complete",
                run_id=run_id,
                status="completed",
                final_report=final_report,
            )
            return

        tools = await self._tool_catalog.get_tools("diagnosis")
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
            yield AgentRuntimeEvent(
                type="complete",
                stage="complete",
                run_id=run_id,
                status="completed",
                final_report=final_report,
            )
            return

        for tool_name in selected_tool_names:
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
            result = await self._action_executor.execute(
                tool,
                action,
                principal=principal,
            )
            yield self._record_event(
                run_id,
                event_type="tool_result",
                stage="tool",
                message=f"Tool {result.tool_name} finished with status {result.status}",
                payload=action.result_event_payload(result),
            )
            state.add_evidence(EvidenceItem.from_tool_result(result))

        final_report = self._synthesizer.build_report(state)
        self._run_store.update_run(run_id, status="completed", final_report=final_report)
        yield self._record_event(
            run_id,
            event_type="final_report",
            stage="complete",
            message="Final report generated",
            payload={"report": final_report},
        )
        yield AgentRuntimeEvent(
            type="complete",
            stage="complete",
            run_id=run_id,
            status="completed",
            final_report=final_report,
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
