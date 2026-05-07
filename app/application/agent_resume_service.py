"""Approval resume orchestration for Native Agent runs."""

from __future__ import annotations

from typing import Any, cast

from loguru import logger

from app.agent_runtime import AgentDecisionRuntime, ToolCatalog, ToolExecutor
from app.infrastructure import checkpoint_saver
from app.platform.persistence.repositories.native_agent import AgentRunRepository
from app.security import Principal


class AgentResumeService:
    """Consume approved-action resume tasks without regenerating risky actions."""

    def __init__(
        self,
        *,
        agent_run_repository: AgentRunRepository,
        tool_catalog: ToolCatalog,
        tool_executor: ToolExecutor,
        decision_runtime: AgentDecisionRuntime | None = None,
    ) -> None:
        self._agent_run_repository = agent_run_repository
        self._tool_catalog = tool_catalog
        self._tool_executor = tool_executor
        self._decision_runtime = decision_runtime or AgentDecisionRuntime(
            checkpoint_saver=checkpoint_saver
        )

    async def process_resume_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        run_id = str(payload.get("run_id") or "")
        tool_name = str(payload.get("tool_name") or "")
        decision = str(payload.get("decision") or "")
        actor = str(payload.get("actor") or "approval-resume")
        checkpoint_ns = str(payload.get("checkpoint_ns") or self._decision_runtime.checkpoint_ns)

        if not run_id or not tool_name or decision != "approved":
            result = {
                "status": "ignored",
                "reason": "invalid_resume_payload",
                "payload": payload,
            }
            logger.warning(f"Invalid approval resume payload: {payload}")
            return result

        run = self._agent_run_repository.get_run(run_id)
        if run is None:
            return {
                "status": "ignored",
                "reason": "run_not_found",
                "run_id": run_id,
                "tool_name": tool_name,
            }

        audited_decision = self._latest_approval_decision(run_id, tool_name)
        if audited_decision.get("decision") != "approved":
            return {
                "status": "ignored",
                "reason": "approval_not_found",
                "run_id": run_id,
                "tool_name": tool_name,
            }

        checkpoint_status = self._checkpoint_status(run_id, checkpoint_ns)
        original_action = self._find_original_action(run_id, tool_name)
        if original_action is None:
            event_payload = {
                "tool_name": tool_name,
                "decision": decision,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_status": checkpoint_status,
                "resume_status": "original_action_missing",
                "safety": {
                    "regenerate_high_risk_action": False,
                    "execute_without_original_action": False,
                },
            }
            self._append_resume_event(run_id, tool_name, event_payload)
            return {
                "status": "original_action_missing",
                "run_id": run_id,
                "tool_name": tool_name,
                "checkpoint_status": checkpoint_status,
            }

        event_payload = {
            "tool_name": tool_name,
            "decision": decision,
            "checkpoint_ns": checkpoint_ns,
            "checkpoint_status": checkpoint_status,
            "resume_status": (
                "ready_for_resume" if checkpoint_status == "available" else "checkpoint_missing"
            ),
            "safety": {
                "regenerate_high_risk_action": False,
                "execute_without_checkpoint": False,
            },
        }
        self._append_resume_event(run_id, tool_name, event_payload)
        if checkpoint_status == "available":
            result = await self._execute_approved_original_action(
                tool_name=tool_name,
                arguments=cast(dict[str, Any], original_action.get("arguments") or {}),
                approval={
                    "tool_name": tool_name,
                    "decision": decision,
                    "actor": actor,
                    "checkpoint_ns": checkpoint_ns,
                },
            )
            self._agent_run_repository.append_event(
                run_id,
                event_type="approval_resumed_tool_result",
                stage="tool",
                message=f"Approved tool {result.tool_name} finished with status {result.status}",
                payload={
                    "tool_name": result.tool_name,
                    "arguments": result.arguments,
                    "status": result.status,
                    "output": result.output,
                    "error": result.error,
                    "governance": result.governance_payload(),
                },
            )
            return {
                "status": "executed",
                "execution_status": result.status,
                "run_id": run_id,
                "tool_name": tool_name,
                "checkpoint_status": checkpoint_status,
            }
        return {
            "status": event_payload["resume_status"],
            "run_id": run_id,
            "tool_name": tool_name,
            "checkpoint_status": checkpoint_status,
        }

    def _append_resume_event(
        self,
        run_id: str,
        tool_name: str,
        payload: dict[str, Any],
    ) -> None:
        self._agent_run_repository.append_event(
            run_id,
            event_type="approval_resume",
            stage="approval",
            message=f"Approval resume evaluated for {tool_name}",
            payload=payload,
        )

    def _find_original_action(self, run_id: str, tool_name: str) -> dict[str, Any] | None:
        events = self._agent_run_repository.list_events(run_id)
        for event in reversed(events):
            if event.get("type") != "tool_call":
                continue
            payload = event.get("payload")
            if not isinstance(payload, dict):
                continue
            if payload.get("tool_name") != tool_name:
                continue
            return payload
        return None

    def _latest_approval_decision(self, run_id: str, tool_name: str) -> dict[str, Any]:
        events = self._agent_run_repository.list_events(run_id)
        for event in reversed(events):
            if event.get("type") != "approval_decision":
                continue
            payload = event.get("payload")
            if not isinstance(payload, dict):
                continue
            if payload.get("tool_name") != tool_name:
                continue
            return payload
        return {}

    async def _execute_approved_original_action(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        approval: dict[str, Any],
    ) -> Any:
        tools = await self._tool_catalog.get_tools("diagnosis")
        tool = next((item for item in tools if str(getattr(item, "name", "")) == tool_name), None)
        if tool is None:
            from app.agent_runtime import ToolExecutionResult

            return ToolExecutionResult(
                tool_name=tool_name,
                status="error",
                arguments=arguments,
                error="Approved tool is not available in the current catalog",
                decision="denied",
                decision_reason="Tool catalog did not contain the approved tool",
            )
        return await self._tool_executor.execute_approved(
            tool,
            arguments,
            principal=Principal(role="admin", subject=str(approval.get("actor") or "resume")),
            approval=approval,
        )

    def _checkpoint_status(self, run_id: str, checkpoint_ns: str) -> str:
        try:
            checkpoint = checkpoint_saver.get_tuple(
                cast(
                    Any,
                    {
                        "configurable": {
                            "thread_id": run_id,
                            "checkpoint_ns": checkpoint_ns,
                        }
                    },
                )
            )
        except Exception as exc:
            logger.warning(f"Checkpoint lookup failed for run {run_id}: {exc}")
            return "error"
        return "available" if checkpoint is not None else "missing"
