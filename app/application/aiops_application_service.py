"""AIOps application orchestration."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

from app.agent_runtime import AgentRuntime
from app.platform.persistence.repositories.aiops import AIOpsRunRepository
from app.platform.persistence.repositories.conversation import ConversationRepository
from app.platform.persistence.repositories.native_agent import (
    SceneRepository,
    WorkspaceRepository,
)
from app.security.auth import Principal


class AIOpsApplicationService:
    """Coordinate AIOps runtime and persistence."""

    def __init__(
        self,
        *,
        agent_runtime: AgentRuntime,
        aiops_run_repository: AIOpsRunRepository,
        conversation_repository: ConversationRepository,
        workspace_repository: WorkspaceRepository,
        scene_repository: SceneRepository,
    ) -> None:
        self._agent_runtime = agent_runtime
        self._aiops_run_repository = aiops_run_repository
        self._conversation_repository = conversation_repository
        self._workspace_repository = workspace_repository
        self._scene_repository = scene_repository

    async def stream_diagnosis(
        self,
        session_id: str,
        principal: Principal | None = None,
        *,
        task_input: str | None = None,
    ) -> AsyncGenerator[dict[str, str], None]:
        """Run a streaming diagnosis flow and persist runtime events."""
        task_input = (
            task_input.strip()
            if task_input and task_input.strip()
            else "诊断当前系统是否存在告警，如果存在告警请详细分析告警原因并生成诊断报告"
        )
        run_id = self._aiops_run_repository.create_run(session_id, task_input)
        scene_id = self._ensure_default_scene()
        runtime_principal = principal or Principal(role="admin", subject="aiops-compat")

        try:
            async for event in self._agent_runtime.run(
                scene_id=scene_id,
                session_id=session_id,
                goal=task_input,
                principal=runtime_principal,
            ):
                native_event = self._runtime_event_to_dict(event)
                translated = self._translate_native_event(native_event)
                event_payload = {
                    **translated,
                    "run_id": run_id,
                    "native_run_id": native_event.get("run_id"),
                }
                self._aiops_run_repository.append_event(
                    run_id,
                    event_type=str(event_payload.get("type", "status")),
                    stage=str(event_payload.get("stage", "unknown")),
                    message=str(event_payload.get("message", "")),
                    payload=event_payload,
                )

                if translated.get("type") == "complete":
                    report = (
                        translated.get("diagnosis", {}).get("report", "")
                        if isinstance(translated.get("diagnosis"), dict)
                        else ""
                    )
                    self._aiops_run_repository.update_run(
                        run_id,
                        status="completed",
                        report=report,
                    )
                    if report:
                        self._conversation_repository.save_aiops_report(
                            session_id,
                            "AIOps 自动诊断",
                            report,
                        )
                elif translated.get("type") == "error":
                    self._aiops_run_repository.update_run(
                        run_id,
                        status="failed",
                        error_message=translated.get("message", "未知错误"),
                    )

                yield {
                    "event": "message",
                    "data": json.dumps(event_payload, ensure_ascii=False),
                }

                if translated.get("type") in {"complete", "error"}:
                    break
        except Exception as exc:
            self._aiops_run_repository.update_run(
                run_id,
                status="failed",
                error_message=str(exc),
            )
            error_event = {
                "type": "error",
                "stage": "exception",
                "message": f"诊断异常: {str(exc)}",
                "run_id": run_id,
            }
            self._aiops_run_repository.append_event(
                run_id,
                event_type="error",
                stage="exception",
                message=error_event["message"],
                payload=error_event,
            )
            yield {
                "event": "message",
                "data": json.dumps(error_event, ensure_ascii=False),
            }

    def _ensure_default_scene(self) -> str:
        workspaces = self._workspace_repository.list_workspaces()
        if workspaces:
            workspace_id = str(workspaces[0]["id"])
        else:
            workspace_id = self._workspace_repository.create_workspace(
                name="Default SRE Workspace",
                description="Default workspace for AIOps diagnosis",
            )

        scenes = self._scene_repository.list_scenes(workspace_id=workspace_id)
        if scenes:
            return str(scenes[0]["id"])
        return self._scene_repository.create_scene(
            workspace_id,
            name="Default AIOps Diagnosis",
            description="Default AIOps compatibility scene",
            agent_config={"mode": "compat"},
        )

    @staticmethod
    def _runtime_event_to_dict(event: Any) -> dict[str, Any]:
        if hasattr(event, "to_dict"):
            data = event.to_dict()
            return data if isinstance(data, dict) else {}
        return event if isinstance(event, dict) else {}

    @staticmethod
    def _translate_native_event(event: dict[str, Any]) -> dict[str, Any]:
        event_type = event.get("type")
        if event_type == "run_started":
            return {
                "type": "status",
                "stage": "agent_started",
                "message": "原生 Agent 诊断已启动",
            }
        if event_type == "hypothesis":
            return {
                "type": "plan",
                "stage": "plan_created",
                "message": "原生 Agent 已生成初始诊断假设",
                "plan": [str(event.get("message", ""))],
            }
        if event_type == "tool_call":
            payload = AIOpsApplicationService._event_payload(event)
            return {
                "type": "status",
                "stage": "tool_call",
                "message": f"正在调用工具: {payload.get('tool_name', 'unknown')}",
            }
        if event_type == "tool_result":
            payload = AIOpsApplicationService._event_payload(event)
            return {
                "type": "step_complete",
                "stage": "step_executed",
                "message": "工具执行完成",
                "current_step": payload.get("tool_name", "unknown"),
                "result_preview": str(payload.get("output") or payload.get("error") or "")[:300],
                "remaining_steps": 0,
            }
        if event_type == "final_report":
            payload = AIOpsApplicationService._event_payload(event)
            return {
                "type": "report",
                "stage": "final_report",
                "message": "最终诊断报告已生成",
                "report": payload.get("report", ""),
            }
        if event_type == "complete":
            report = str(event.get("final_report", ""))
            return {
                "type": "complete",
                "stage": "diagnosis_complete",
                "message": "诊断流程完成",
                "diagnosis": {"status": "completed", "report": report},
            }
        return {
            "type": "status",
            "stage": str(event.get("stage", "native_agent")),
            "message": str(event.get("message", "")),
        }

    @staticmethod
    def _event_payload(event: dict[str, Any]) -> dict[str, Any]:
        payload = event.get("payload")
        return payload if isinstance(payload, dict) else {}
