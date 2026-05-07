"""Native Agent application orchestration."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any

from app.agent_runtime import AgentRuntime, ToolCatalog
from app.config import config
from app.infrastructure import redis_manager
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
                    "schema": _tool_schema(tool),
                    "risk_level": (policies.get(tool_name) or {}).get(
                        "risk_level",
                        getattr(tool, "risk_level", "low"),
                    ),
                    "capability": (policies.get(tool_name) or {}).get(
                        "capability",
                        getattr(tool, "capability", None),
                    ),
                    "approval_required": (policies.get(tool_name) or {}).get(
                        "approval_required",
                        getattr(tool, "approval_required", False),
                    ),
                    "timeout_seconds": getattr(tool, "timeout_seconds", None),
                    "retry_count": getattr(tool, "retry_count", None),
                    "owner": getattr(tool, "owner", "SmartSRE"),
                    "data_boundary": getattr(tool, "data_boundary", "workspace"),
                    "side_effect": getattr(tool, "side_effect", "none"),
                    "allowed_scopes": [str(getattr(tool, "scope", "diagnosis"))],
                    "policy": policies.get(tool_name),
                }
            )
        return data

    def update_tool_policy(
        self,
        tool_name: str,
        *,
        scope: str | None,
        risk_level: str | None,
        capability: str | None,
        enabled: bool | None,
        approval_required: bool | None,
    ) -> dict[str, Any]:
        current = self._tool_policy_repository.get_policy(tool_name) or {}
        return self._tool_policy_repository.upsert_policy(
            tool_name,
            scope=scope if scope is not None else str(current.get("scope") or "diagnosis"),
            risk_level=risk_level
            if risk_level is not None
            else str(current.get("risk_level") or "low"),
            capability=capability if capability is not None else current.get("capability"),
            enabled=enabled if enabled is not None else bool(current.get("enabled", True)),
            approval_required=approval_required
            if approval_required is not None
            else bool(current.get("approval_required", False)),
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

    async def stream_agent_run(
        self,
        *,
        scene_id: str,
        session_id: str,
        goal: str,
        principal: Principal,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream agent run events as dictionaries."""
        async for event in self._agent_runtime.run(
            scene_id=scene_id,
            session_id=session_id,
            goal=goal,
            principal=principal,
        ):
            yield self._runtime_event_to_dict(event)

    @staticmethod
    def _runtime_event_to_dict(event: Any) -> dict[str, Any]:
        if hasattr(event, "to_dict"):
            data = event.to_dict()
            return data if isinstance(data, dict) else {}
        return event if isinstance(event, dict) else {}

    def get_agent_run(self, run_id: str) -> dict[str, Any] | None:
        run = self._agent_run_repository.get_run(run_id)
        if run is None:
            return None
        return self._enrich_run_with_metrics(run)

    def list_agent_runs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        return [
            self._enrich_run_with_metrics(run)
            for run in self._agent_run_repository.list_runs(limit=limit)
        ]

    def list_agent_run_events(self, run_id: str) -> list[dict[str, Any]] | None:
        if self._agent_run_repository.get_run(run_id) is None:
            return None
        return self._agent_run_repository.list_events(run_id)

    def get_agent_run_replay(self, run_id: str) -> dict[str, Any] | None:
        """Return a read-only replay snapshot for one persisted run."""
        run = self._agent_run_repository.get_run(run_id)
        if run is None:
            return None

        events = self._agent_run_repository.list_events(run_id)
        feedback = self._agent_feedback_repository.list_feedback(run_id)
        metrics = _derive_run_metrics(run, events)
        tool_calls = _events_by_type(events, "tool_call")
        tool_results = _events_by_type(events, "tool_result")
        decisions = _events_by_type(events, "decision")
        approval_decisions = _events_by_type(events, "approval_decision")
        approval_resumes = _events_by_type(events, "approval_resume")
        approval_resumed_tool_results = _events_by_type(events, "approval_resumed_tool_result")
        recovery_events = _decision_events_by_action(events, {"recover", "handoff"})
        return {
            "run": {**run, "metrics": metrics, "event_count": len(events)},
            "events": events,
            "summary": {
                "status": run.get("status"),
                "latest_status": _latest_decision_status(events),
                "event_count": len(events),
                "tool_call_count": len(tool_calls),
                "tool_result_count": len(tool_results),
                "decision_count": len(decisions),
                "approval_count": len(approval_decisions),
                "approval_resume_count": len(approval_resumes),
                "recovery_count": len(recovery_events),
            },
            "tool_calls": tool_calls,
            "tool_results": tool_results,
            "tool_trajectory": _build_tool_trajectory(tool_calls, tool_results),
            "decision_events": decisions,
            "approval_decisions": approval_decisions,
            "approval_resumes": approval_resumes,
            "approval_resumed_tool_results": approval_resumed_tool_results,
            "recovery_events": recovery_events,
            "knowledge_citations": _extract_knowledge_citations(events),
            "final_report": run.get("final_report"),
            "feedback": feedback,
            "metrics": metrics,
        }

    def get_agent_decision_state(self, run_id: str) -> dict[str, Any] | None:
        run = self._agent_run_repository.get_run(run_id)
        if run is None:
            return None
        events = self._agent_run_repository.list_events(run_id)
        return {
            "run_id": run_id,
            "decisions": _events_by_type(events, "decision"),
            "approval_decisions": _events_by_type(events, "approval_decision"),
            "approval_resume": _events_by_type(events, "approval_resume"),
            "recovery_events": _decision_events_by_action(events, {"recover", "handoff"}),
            "latest_status": _latest_decision_status(events),
        }

    def list_agent_approvals(self, *, limit: int = 50) -> list[dict[str, Any]]:
        self.expire_pending_agent_approvals(limit=limit)
        approvals: list[dict[str, Any]] = []
        for run in self._agent_run_repository.list_runs(limit=limit):
            events = self._agent_run_repository.list_events(str(run["run_id"]))
            decisions = _approval_decisions_by_tool(events)
            resumes = _approval_resume_by_tool(events)
            resume_results = _approval_resume_results_by_tool(events)
            for event in events:
                if event.get("type") != "tool_result":
                    continue
                payload = event.get("payload")
                if not isinstance(payload, dict):
                    continue
                if payload.get("execution_status") != "approval_required":
                    continue
                tool_name = str(payload.get("tool_name") or "")
                decision = decisions.get(tool_name)
                resume = resumes.get(tool_name)
                resume_result = resume_results.get(tool_name)
                resume_status = (
                    "executed"
                    if resume_result
                    else resume.get("resume_status")
                    if resume
                    else decision.get("resume_status")
                    if decision
                    else None
                )
                approvals.append(
                    {
                        "run_id": run["run_id"],
                        "goal": run["goal"],
                        "tool_name": tool_name,
                        "arguments": payload.get("arguments") or {},
                        "policy": payload.get("policy") or {},
                        "governance": payload.get("governance") or {},
                        "status": decision.get("decision", "pending") if decision else "pending",
                        "comment": decision.get("comment") if decision else None,
                        "created_at": event.get("created_at"),
                        "decided_at": decision.get("created_at") if decision else None,
                        "resume_status": resume_status,
                        "resume_reason": resume.get("reason")
                        if resume
                        else decision.get("reason")
                        if decision
                        else None,
                        "resume_checkpoint_status": resume.get("checkpoint_status")
                        if resume
                        else None,
                        "resume_execution_status": resume_result.get("status")
                        if resume_result
                        else None,
                        "resumed_at": resume_result.get("created_at")
                        if resume_result
                        else resume.get("created_at")
                        if resume
                        else None,
                    }
                )
        return approvals

    def decide_agent_approval(
        self,
        run_id: str,
        *,
        tool_name: str,
        decision: str,
        comment: str | None = None,
        actor: str | None = None,
    ) -> dict[str, Any] | None:
        if self._agent_run_repository.get_run(run_id) is None:
            return None
        if decision not in {"approved", "rejected"}:
            raise ValueError("decision must be approved or rejected")
        self._expire_pending_agent_approvals_for_run(run_id)
        existing_decision = _approval_decisions_by_tool(
            self._agent_run_repository.list_events(run_id)
        ).get(tool_name)
        if existing_decision:
            existing_status = str(existing_decision.get("decision") or "")
            if existing_status == "expired":
                raise ValueError("approval_expired")
            raise ValueError("approval_already_decided")

        payload: dict[str, Any] = {
            "tool_name": tool_name,
            "decision": decision,
            "comment": comment,
            "actor": actor,
            "resume_status": "pending_resume_enqueue" if decision == "approved" else "not_resumed",
            "reason": _resume_status_reason(
                "pending_resume_enqueue" if decision == "approved" else "not_resumed"
            ),
        }
        self._agent_run_repository.append_event(
            run_id,
            event_type="approval_decision",
            stage="approval",
            message=f"Tool approval {decision}: {tool_name}",
            payload=payload,
        )
        if decision == "approved":
            resume_status = _enqueue_approval_resume_task(
                run_id=run_id,
                tool_name=tool_name,
                decision=decision,
                actor=actor,
            )
            resume_payload = {
                "tool_name": tool_name,
                "decision": decision,
                "actor": actor,
                "resume_status": resume_status,
                "reason": _resume_status_reason(resume_status),
                "checkpoint_ns": "agent-v2",
                "checkpoint_status": "not_checked",
                "safety": {
                    "regenerate_high_risk_action": False,
                    "execute_without_checkpoint": False,
                },
            }
            self._agent_run_repository.append_event(
                run_id,
                event_type="approval_resume",
                stage="approval",
                message=f"Approval resume dispatch {resume_status}: {tool_name}",
                payload=resume_payload,
            )
            payload = resume_payload
        elif decision == "rejected":
            self._mark_run_handoff(
                run_id,
                tool_name=tool_name,
                reason="approval_rejected",
                message="Tool approval was rejected; run requires manual handoff.",
            )
        return payload

    def expire_pending_agent_approvals(self, *, limit: int = 50) -> list[dict[str, Any]]:
        """Expire old pending approval requests and move their runs to handoff."""
        expired: list[dict[str, Any]] = []
        for run in self._agent_run_repository.list_runs(limit=limit):
            expired.extend(self._expire_pending_agent_approvals_for_run(str(run["run_id"])))
        return expired

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

    def _enrich_run_with_metrics(self, run: dict[str, Any]) -> dict[str, Any]:
        events = self._agent_run_repository.list_events(str(run["run_id"]))
        metrics = _derive_run_metrics(run, events)
        return {
            **run,
            "runtime_version": metrics["runtime_version"],
            "trace_id": metrics["trace_id"],
            "approval_state": metrics["approval_state"],
            "metrics": metrics,
        }

    def _expire_pending_agent_approvals_for_run(self, run_id: str) -> list[dict[str, Any]]:
        run = self._agent_run_repository.get_run(run_id)
        if run is None:
            return []
        events = self._agent_run_repository.list_events(run_id)
        decisions = _approval_decisions_by_tool(events)
        now = datetime.now(UTC)
        expired: list[dict[str, Any]] = []
        for event in events:
            if event.get("type") != "tool_result":
                continue
            payload = event.get("payload")
            if not isinstance(payload, dict):
                continue
            if payload.get("execution_status") != "approval_required":
                continue
            tool_name = str(payload.get("tool_name") or "")
            if not tool_name or tool_name in decisions:
                continue
            created_at = event.get("created_at")
            if not _approval_is_expired(created_at, now=now):
                continue

            decision_payload = {
                "tool_name": tool_name,
                "decision": "expired",
                "comment": "Approval request expired before an explicit decision.",
                "actor": "system",
                "resume_status": "not_resumed",
                "reason": _resume_status_reason("expired"),
                "expires_at": _approval_expires_at(created_at),
            }
            self._agent_run_repository.append_event(
                run_id,
                event_type="approval_decision",
                stage="approval",
                message=f"Tool approval expired: {tool_name}",
                payload=decision_payload,
            )
            self._mark_run_handoff(
                run_id,
                tool_name=tool_name,
                reason="approval_expired",
                message="Tool approval expired before a decision; run requires manual handoff.",
            )
            expired.append(
                {
                    "run_id": run_id,
                    "tool_name": tool_name,
                    "decision": "expired",
                    "expires_at": decision_payload["expires_at"],
                }
            )
        return expired

    def _mark_run_handoff(
        self,
        run_id: str,
        *,
        tool_name: str,
        reason: str,
        message: str,
    ) -> None:
        final_report = (
            "## Handoff Required\n\n"
            f"- Tool: {tool_name}\n"
            f"- Reason: {reason}\n"
            f"- Detail: {message}\n"
            "- No high-risk tool action was executed after the approval boundary."
        )
        self._agent_run_repository.append_event(
            run_id,
            event_type="decision",
            stage="handoff",
            message=message,
            payload={
                "decision": {
                    "action_type": "handoff",
                    "reason": reason,
                    "selected_tool": tool_name,
                },
                "state_status": "handoff_required",
            },
        )
        self._agent_run_repository.append_event(
            run_id,
            event_type="handoff",
            stage="handoff",
            message=message,
            payload={
                "tool_name": tool_name,
                "reason": reason,
                "final_report": final_report,
            },
        )
        self._agent_run_repository.update_run(
            run_id,
            status="handoff_required",
            final_report=final_report,
            error_message=reason,
        )


def _events_by_type(events: list[dict[str, Any]], event_type: str) -> list[dict[str, Any]]:
    return [event for event in events if event.get("type") == event_type]


def _tool_schema(tool: Any) -> dict[str, Any] | None:
    args_schema = getattr(tool, "args_schema", None)
    if args_schema is None:
        return None
    if isinstance(args_schema, dict):
        return args_schema
    if hasattr(args_schema, "model_json_schema"):
        schema = args_schema.model_json_schema()
        return schema if isinstance(schema, dict) else None
    if hasattr(args_schema, "schema"):
        schema = args_schema.schema()
        return schema if isinstance(schema, dict) else None
    return None


def _approval_decisions_by_tool(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    decisions: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.get("type") != "approval_decision":
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        tool_name = payload.get("tool_name")
        if not tool_name:
            continue
        decisions[str(tool_name)] = {
            **payload,
            "created_at": event.get("created_at"),
        }
    return decisions


def _approval_resume_by_tool(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    resumes: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.get("type") != "approval_resume":
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        tool_name = payload.get("tool_name")
        if not tool_name:
            continue
        resumes[str(tool_name)] = {
            **payload,
            "created_at": event.get("created_at"),
        }
    return resumes


def _approval_resume_results_by_tool(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.get("type") != "approval_resumed_tool_result":
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        tool_name = payload.get("tool_name")
        if not tool_name:
            continue
        results[str(tool_name)] = {
            **payload,
            "created_at": event.get("created_at"),
        }
    return results


def _decision_events_by_action(
    events: list[dict[str, Any]],
    actions: set[str],
) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    for event in events:
        if event.get("type") != "decision":
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        decision = payload.get("decision")
        if not isinstance(decision, dict):
            continue
        action_type = str(decision.get("action_type") or "")
        if action_type in actions:
            matched.append(
                {
                    **event,
                    "payload": {
                        **payload,
                        "decision": decision,
                    },
                }
            )
    return matched


def _latest_decision_status(events: list[dict[str, Any]]) -> str:
    for event in reversed(events):
        if event.get("type") == "approval_resume":
            payload = event.get("payload")
            if isinstance(payload, dict):
                return str(payload.get("resume_status") or "approval_resume")
        if event.get("type") == "decision":
            payload = event.get("payload")
            if isinstance(payload, dict):
                return str(payload.get("state_status") or "decision_recorded")
    return "not_started"


def _build_tool_trajectory(
    tool_calls: list[dict[str, Any]],
    tool_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    trajectories: list[dict[str, Any]] = []
    pending_results: dict[str, list[dict[str, Any]]] = {}
    for result in tool_results:
        payload = result.get("payload")
        if not isinstance(payload, dict):
            continue
        tool_name = str(payload.get("tool_name") or payload.get("tool") or "")
        if not tool_name:
            continue
        pending_results.setdefault(tool_name, []).append(result)

    for tool_call in tool_calls:
        payload = tool_call.get("payload")
        if not isinstance(payload, dict):
            continue
        tool_name = str(payload.get("tool_name") or payload.get("tool") or "")
        if not tool_name:
            continue
        matched_result: dict[str, Any] | None = None
        if pending_results.get(tool_name):
            matched_result = pending_results[tool_name].pop(0)
        trajectories.append(
            {
                "tool_name": tool_name,
                "call": tool_call,
                "result": matched_result,
                "approval_state": payload.get("approval_state"),
                "policy": payload.get("policy"),
                "execution_status": payload.get("execution_status"),
            }
        )

    for tool_name, remaining_results in pending_results.items():
        for result in remaining_results:
            trajectories.append(
                {
                    "tool_name": tool_name,
                    "call": None,
                    "result": result,
                    "approval_state": None,
                    "policy": None,
                    "execution_status": None,
                }
            )

    return trajectories


def _enqueue_approval_resume_task(
    *,
    run_id: str,
    tool_name: str,
    decision: str,
    actor: str | None,
) -> str:
    if config.task_queue_backend != "redis":
        return "deferred_until_resume_worker_enabled"
    payload = {
        "run_id": run_id,
        "tool_name": tool_name,
        "decision": decision,
        "actor": actor,
        "checkpoint_ns": "agent-v2",
    }
    try:
        redis_manager.enqueue_json(config.agent_resume_queue_name, payload)
    except Exception:
        return "enqueue_failed"
    return "queued"


def _resume_status_reason(resume_status: str) -> str:
    reasons = {
        "queued": "Approved action was queued for checkpoint resume.",
        "enqueue_failed": "Approval was audited, but resume queue enqueue failed.",
        "deferred_until_resume_worker_enabled": (
            "Approval was audited; checkpoint resume worker is not enabled in this mode."
        ),
        "pending_resume_enqueue": "Approval was audited before resume dispatch.",
        "not_resumed": "Approval decision was audited without executing the action.",
        "expired": "Approval request expired before an explicit decision.",
    }
    return reasons.get(resume_status, "Approval decision was audited.")


def _approval_expires_at(created_at: Any) -> str | None:
    if not isinstance(created_at, datetime):
        return None
    aware_dt: datetime = _ensure_aware_utc(created_at)
    expires_at = aware_dt + timedelta(seconds=config.agent_approval_timeout_seconds)
    return expires_at.isoformat()


def _approval_is_expired(created_at: Any, *, now: datetime) -> bool:
    if not isinstance(created_at, datetime):
        return False
    aware_dt: datetime = _ensure_aware_utc(created_at)
    now = _ensure_aware_utc(now)
    expires_at = aware_dt + timedelta(seconds=config.agent_approval_timeout_seconds)
    return expires_at <= now


def _ensure_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _derive_run_metrics(run: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    run_started = next((event for event in events if event.get("type") == "run_started"), None)
    run_started_payload = run_started.get("payload") if run_started else {}
    if not isinstance(run_started_payload, dict):
        run_started_payload = {}

    decision_events = _events_by_type(events, "decision")
    tool_results = _events_by_type(events, "tool_result")
    approval_states = [
        _payload_value(event, "approval_state")
        for event in tool_results
        if _payload_value(event, "approval_state") is not None
    ]
    approval_state = "required" if "required" in approval_states else "not_required"
    error_type = None
    if run.get("status") == "failed":
        error_event = next((event for event in events if event.get("type") == "error"), None)
        error_type = _payload_value(error_event, "error_type") if error_event else None

    created_at = run.get("created_at")
    updated_at = run.get("updated_at")
    latency_ms = _latency_ms(created_at, updated_at)
    step_count = len(
        [
            event
            for event in events
            if event.get("type") in {"hypothesis", "decision", "tool_call", "tool_result"}
        ]
    )
    tool_call_count = len(_events_by_type(events, "tool_call"))
    retrieval_count = len(_events_by_type(events, "knowledge_context"))
    error_count = len(_events_by_type(events, "error"))
    recovery_count = len(_decision_events_by_action(events, {"recover"}))
    handoff_count = len(_decision_events_by_action(events, {"handoff"}))
    decision_count = len(decision_events)
    approval_count = len(_events_by_type(events, "approval_decision"))
    resume_count = len(_events_by_type(events, "approval_resume"))
    cost_estimate_usd = _estimate_run_cost(
        tool_call_count=tool_call_count, retrieval_count=retrieval_count
    )

    persisted_step_count = _persisted_int(run.get("step_count"))
    persisted_tool_call_count = _persisted_int(run.get("tool_call_count"))
    persisted_retrieval_count = _persisted_int(run.get("retrieval_count"))

    return {
        "runtime_version": run.get("runtime_version") or "native-agent-dev",
        "trace_id": run.get("trace_id") or str(run.get("run_id")),
        "model_name": run.get("model_name") or "deterministic-native-agent",
        "steps": persisted_step_count if persisted_step_count is not None else step_count,
        "step_count": persisted_step_count if persisted_step_count is not None else step_count,
        "tool_calls": persisted_tool_call_count
        if persisted_tool_call_count is not None
        else tool_call_count,
        "tool_call_count": persisted_tool_call_count
        if persisted_tool_call_count is not None
        else tool_call_count,
        "latency_ms": _persisted_int(run.get("latency_ms"))
        if _persisted_int(run.get("latency_ms")) is not None
        else latency_ms,
        "error_type": run.get("error_type") or error_type,
        "error_count": error_count,
        "approval_state": run.get("approval_state") or approval_state,
        "retrieval_count": persisted_retrieval_count
        if persisted_retrieval_count is not None
        else retrieval_count,
        "decision_count": decision_count,
        "approval_count": approval_count,
        "resume_count": resume_count,
        "recovery_count": recovery_count,
        "handoff_count": handoff_count,
        "token_usage": run.get("token_usage"),
        "cost_estimate": cost_estimate_usd,
        "cost_estimate_usd": cost_estimate_usd,
        "cost_estimate_source": "heuristic",
        "runtime_safety": run_started_payload.get("runtime_safety"),
        "event_counts": _count_event_types(events),
    }


def _payload_value(event: dict[str, Any] | None, key: str) -> Any:
    if event is None:
        return None
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return None
    return payload.get(key)


def _latency_ms(created_at: Any, updated_at: Any) -> int | None:
    if created_at is None or updated_at is None:
        return None
    try:
        return int((updated_at - created_at).total_seconds() * 1000)
    except AttributeError:
        return None


def _persisted_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _extract_knowledge_citations(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    for event in events:
        if event.get("type") != "knowledge_context":
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        knowledge_bases = payload.get("knowledge_bases")
        if not isinstance(knowledge_bases, list):
            continue
        for item in knowledge_bases:
            if isinstance(item, dict):
                citations.append(item)
    return citations


def _count_event_types(events: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        event_type = str(event.get("type") or "unknown")
        counts[event_type] = counts.get(event_type, 0) + 1
    return counts


def _estimate_run_cost(*, tool_call_count: int, retrieval_count: int) -> float:
    """Return a lightweight heuristic cost estimate for UI and replay summaries."""

    return round(tool_call_count * 0.01 + retrieval_count * 0.002, 4)
