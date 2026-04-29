"""Native Agent application orchestration."""

from __future__ import annotations

from typing import Any

from app.agent_runtime import AgentRuntime, ToolCatalog
from app.platform.persistence.repositories.native_agent import (
    AgentFeedbackRepository,
    AgentRunRepository,
    SceneRepository,
    ToolPolicyRepository,
    WorkspaceRepository,
)
from app.security import Principal


class NativeAgentApplicationService:
    """Coordinate Native Agent product workflows."""

    def __init__(
        self,
        *,
        agent_runtime: AgentRuntime,
        tool_catalog: ToolCatalog,
        workspace_repository: WorkspaceRepository,
        scene_repository: SceneRepository,
        tool_policy_repository: ToolPolicyRepository,
        agent_run_repository: AgentRunRepository,
        agent_feedback_repository: AgentFeedbackRepository,
    ) -> None:
        self._agent_runtime = agent_runtime
        self._tool_catalog = tool_catalog
        self._workspace_repository = workspace_repository
        self._scene_repository = scene_repository
        self._tool_policy_repository = tool_policy_repository
        self._agent_run_repository = agent_run_repository
        self._agent_feedback_repository = agent_feedback_repository

    def create_workspace(self, *, name: str, description: str | None) -> dict[str, Any] | None:
        workspace_id = self._workspace_repository.create_workspace(
            name=name,
            description=description,
        )
        return self._workspace_repository.get_workspace(workspace_id)

    def list_workspaces(self) -> list[dict[str, Any]]:
        return self._workspace_repository.list_workspaces()

    def create_scene(
        self,
        *,
        workspace_id: str,
        name: str,
        description: str | None,
        knowledge_base_ids: list[str] | None,
        tool_names: list[str] | None,
        agent_config: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        scene_id = self._scene_repository.create_scene(
            workspace_id,
            name=name,
            description=description,
            knowledge_base_ids=knowledge_base_ids,
            tool_names=tool_names,
            agent_config=agent_config,
        )
        return self._scene_repository.get_scene(scene_id)

    def list_scenes(self, *, workspace_id: str | None = None) -> list[dict[str, Any]]:
        return self._scene_repository.list_scenes(workspace_id=workspace_id)

    def get_scene(self, scene_id: str) -> dict[str, Any] | None:
        return self._scene_repository.get_scene(scene_id)

    async def list_tools(self) -> list[dict[str, Any]]:
        tools = await self._tool_catalog.get_tools("diagnosis")
        policies = {
            policy["tool_name"]: policy for policy in self._tool_policy_repository.list_policies()
        }
        data: list[dict[str, Any]] = []
        for tool in tools:
            tool_name = str(getattr(tool, "name", "unknown"))
            data.append(
                {
                    "name": tool_name,
                    "description": str(getattr(tool, "description", "")),
                    "policy": policies.get(tool_name),
                }
            )
        return data

    def update_tool_policy(
        self,
        tool_name: str,
        *,
        scope: str,
        risk_level: str,
        capability: str | None,
        enabled: bool,
        approval_required: bool,
    ) -> dict[str, Any]:
        return self._tool_policy_repository.upsert_policy(
            tool_name,
            scope=scope,
            risk_level=risk_level,
            capability=capability,
            enabled=enabled,
            approval_required=approval_required,
        )

    async def create_agent_run(
        self,
        *,
        scene_id: str,
        session_id: str,
        goal: str,
        principal: Principal,
    ) -> dict[str, Any] | None:
        final_event: dict[str, Any] | None = None
        async for event in self._agent_runtime.run(
            scene_id=scene_id,
            session_id=session_id,
            goal=goal,
            principal=principal,
        ):
            final_event = self._runtime_event_to_dict(event)

        if final_event is None:
            return None
        return {
            "run_id": final_event["run_id"],
            "status": final_event.get("status", "completed"),
            "final_report": final_event.get("final_report", ""),
        }

    @staticmethod
    def _runtime_event_to_dict(event: Any) -> dict[str, Any]:
        if hasattr(event, "to_dict"):
            data = event.to_dict()
            return data if isinstance(data, dict) else {}
        return event if isinstance(event, dict) else {}

    def get_agent_run(self, run_id: str) -> dict[str, Any] | None:
        return self._agent_run_repository.get_run(run_id)

    def list_agent_run_events(self, run_id: str) -> list[dict[str, Any]] | None:
        if self._agent_run_repository.get_run(run_id) is None:
            return None
        return self._agent_run_repository.list_events(run_id)

    def create_agent_feedback(
        self,
        run_id: str,
        *,
        rating: str,
        comment: str | None,
    ) -> dict[str, str] | None:
        if self._agent_run_repository.get_run(run_id) is None:
            return None
        feedback_id = self._agent_feedback_repository.create_feedback(
            run_id,
            rating=rating,
            comment=comment,
        )
        return {"feedback_id": feedback_id}
