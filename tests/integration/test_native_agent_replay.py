from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.application.native_agent_application_service import (
    NativeAgentApplicationService,
    _derive_run_metrics,
)
from app.config import config


class DummyRuntime:
    pass


class DummyCatalog:
    async def get_tools(self, scope: str, *, force_refresh: bool = False):
        return []


class DummyWorkspaceRepository:
    def create_workspace(self, *, name, description):
        return "workspace-1"

    def get_workspace(self, workspace_id):
        return {"id": workspace_id, "name": "Workspace"}

    def list_workspaces(self):
        return []


class DummySceneRepository:
    def create_scene(
        self,
        workspace_id,
        *,
        name,
        description,
        knowledge_base_ids,
        tool_names,
        agent_config,
    ):
        return "scene-1"

    def get_scene(self, scene_id):
        return {"id": scene_id, "workspace_id": "workspace-1"}

    def list_scenes(self, workspace_id=None):
        return []


class DummyPolicyRepository:
    def get_policy(self, tool_name):
        return None

    def list_policies(self):
        return []

    def upsert_policy(self, tool_name, **kwargs):
        return {"tool_name": tool_name, **kwargs}


class DummyRunRepository:
    def __init__(self, run, events):
        self._run = run
        self._events = events
        self.updated_runs: list[dict[str, object]] = []

    def get_run(self, run_id):
        return self._run if run_id == self._run["run_id"] else None

    def list_events(self, run_id):
        return list(self._events) if run_id == self._run["run_id"] else []

    def list_runs(self, limit=50):
        return [self._run]

    def append_event(self, run_id, *, event_type, stage, message, payload=None):
        if run_id != self._run["run_id"]:
            return
        self._events.append(
            {
                "type": event_type,
                "stage": stage,
                "message": message,
                "payload": payload,
                "created_at": datetime.now(UTC),
            }
        )

    def update_run(self, run_id, *, status, final_report=None, error_message=None):
        if run_id != self._run["run_id"]:
            return
        self._run["status"] = status
        if final_report is not None:
            self._run["final_report"] = final_report
        if error_message is not None:
            self._run["error_message"] = error_message
        self.updated_runs.append(
            {
                "run_id": run_id,
                "status": status,
                "final_report": final_report,
                "error_message": error_message,
            }
        )


class DummyFeedbackRepository:
    def list_feedback(self, run_id):
        return [{"run_id": run_id, "rating": "helpful"}]


def build_service(run, events):
    run_repository = DummyRunRepository(run, events)
    return NativeAgentApplicationService(
        agent_runtime=DummyRuntime(),
        tool_catalog=DummyCatalog(),
        workspace_repository=DummyWorkspaceRepository(),
        scene_repository=DummySceneRepository(),
        tool_policy_repository=DummyPolicyRepository(),
        agent_run_repository=run_repository,
        agent_feedback_repository=DummyFeedbackRepository(),
    )


def test_run_replay_exposes_trajectory_summary_and_metrics():
    created_at = datetime(2026, 5, 7, 8, 0, tzinfo=UTC)
    updated_at = created_at + timedelta(seconds=12)
    run = {
        "run_id": "run-1",
        "goal": "diagnose latency spike",
        "status": "failed",
        "created_at": created_at,
        "updated_at": updated_at,
        "final_report": "Diagnosis complete.",
        "error_message": "tool timed out",
    }
    events = [
        {
            "type": "run_started",
            "message": "Run started",
            "created_at": created_at,
            "payload": {
                "runtime_safety": {"tool_timeout_seconds": 1.0, "run_timeout_seconds": 5.0}
            },
        },
        {
            "type": "hypothesis",
            "message": "Hypothesis formed",
            "created_at": created_at + timedelta(seconds=1),
            "payload": {"summary": "check logs"},
        },
        {
            "type": "decision",
            "message": "Recover and retry",
            "created_at": created_at + timedelta(seconds=2),
            "payload": {
                "decision": {"action_type": "recover", "reason": "retry once"},
                "state_status": "decision_recorded",
            },
        },
        {
            "type": "tool_call",
            "message": "SearchLog",
            "created_at": created_at + timedelta(seconds=3),
            "payload": {
                "tool_name": "SearchLog",
                "approval_state": "required",
                "policy": {"approval_required": True},
                "execution_status": "approval_required",
                "message": "call search",
            },
        },
        {
            "type": "tool_result",
            "message": "Approval required",
            "created_at": created_at + timedelta(seconds=4),
            "payload": {
                "tool_name": "SearchLog",
                "approval_state": "required",
                "execution_status": "approval_required",
                "message": "blocked awaiting approval",
            },
        },
        {
            "type": "approval_decision",
            "message": "Approved",
            "created_at": created_at + timedelta(seconds=5),
            "payload": {
                "tool_name": "SearchLog",
                "decision": "approved",
                "resume_status": "pending_resume_enqueue",
                "reason": "queued for resume",
            },
        },
        {
            "type": "approval_resume",
            "message": "Resume queued",
            "created_at": created_at + timedelta(seconds=6),
            "payload": {
                "tool_name": "SearchLog",
                "resume_status": "queued",
                "reason": "queued for resume",
                "checkpoint_status": "not_checked",
            },
        },
        {
            "type": "approval_resumed_tool_result",
            "message": "Resumed tool result",
            "created_at": created_at + timedelta(seconds=7),
            "payload": {
                "tool_name": "SearchLog",
                "status": "success",
                "message": "resumed result",
            },
        },
        {
            "type": "knowledge_context",
            "message": "Knowledge loaded",
            "created_at": created_at + timedelta(seconds=8),
            "payload": {
                "knowledge_bases": [{"id": "kb-1", "name": "Runbook", "version": "development"}]
            },
        },
        {
            "type": "error",
            "message": "Timed out",
            "created_at": created_at + timedelta(seconds=9),
            "payload": {"error_type": "timeout", "message": "tool timed out"},
        },
    ]

    service = build_service(run, events)

    replay = service.get_agent_run_replay("run-1")
    assert replay is not None
    assert replay["summary"]["event_count"] == len(events)
    assert replay["summary"]["tool_call_count"] == 1
    assert replay["summary"]["recovery_count"] == 1
    assert replay["tool_trajectory"][0]["tool_name"] == "SearchLog"
    assert replay["tool_trajectory"][0]["call"]["payload"]["tool_name"] == "SearchLog"
    assert (
        replay["tool_trajectory"][0]["result"]["payload"]["execution_status"] == "approval_required"
    )
    assert replay["knowledge_citations"][0]["id"] == "kb-1"
    assert replay["approval_decisions"][0]["payload"]["decision"] == "approved"
    assert replay["approval_resumes"][0]["payload"]["resume_status"] == "queued"
    assert replay["approval_resumed_tool_results"][0]["payload"]["status"] == "success"
    assert replay["metrics"]["steps"] == 4
    assert replay["metrics"]["tool_calls"] == 1
    assert replay["metrics"]["retrieval_count"] == 1
    assert replay["metrics"]["decision_count"] == 1
    assert replay["metrics"]["approval_count"] == 1
    assert replay["metrics"]["resume_count"] == 1
    assert replay["metrics"]["recovery_count"] == 1
    assert replay["metrics"]["error_count"] == 1
    assert replay["metrics"]["error_type"] == "timeout"
    assert replay["metrics"]["cost_estimate_usd"] == 0.012
    assert replay["metrics"]["runtime_safety"] == {
        "tool_timeout_seconds": 1.0,
        "run_timeout_seconds": 5.0,
    }
    assert replay["metrics"]["event_counts"]["approval_resume"] == 1

    decision_state = service.get_agent_decision_state("run-1")
    assert decision_state is not None
    assert decision_state["latest_status"] == "queued"
    assert len(decision_state["recovery_events"]) == 1


def test_derive_run_metrics_tracks_handoffs_and_event_counts():
    run = {
        "run_id": "run-2",
        "status": "completed",
        "created_at": datetime(2026, 5, 7, 8, 0, tzinfo=UTC),
        "updated_at": datetime(2026, 5, 7, 8, 0, 1, tzinfo=UTC),
    }
    events = [
        {"type": "run_started", "payload": {}},
        {
            "type": "decision",
            "payload": {"decision": {"action_type": "handoff"}},
        },
        {"type": "tool_call", "payload": {"tool_name": "SearchLog"}},
        {"type": "tool_result", "payload": {"tool_name": "SearchLog"}},
    ]

    metrics = _derive_run_metrics(run, events)

    assert metrics["handoff_count"] == 1
    assert metrics["recovery_count"] == 0
    assert metrics["event_counts"]["decision"] == 1
    assert metrics["event_counts"]["tool_call"] == 1


def test_derive_run_metrics_prefers_persisted_agentops_columns():
    run = {
        "run_id": "run-metrics",
        "status": "completed",
        "created_at": datetime(2026, 5, 7, 8, 0, tzinfo=UTC),
        "updated_at": datetime(2026, 5, 7, 8, 0, 1, tzinfo=UTC),
        "runtime_version": "native-agent-dev",
        "trace_id": "trace-123",
        "model_name": "qwen-max",
        "step_count": 9,
        "tool_call_count": 4,
        "latency_ms": 321,
        "error_type": None,
        "approval_state": "required",
        "retrieval_count": 2,
        "token_usage": {"input": 10, "output": 20},
    }
    events = [
        {"type": "run_started", "payload": {}},
        {"type": "tool_call", "payload": {"tool_name": "SearchLog"}},
    ]

    metrics = _derive_run_metrics(run, events)

    assert metrics["runtime_version"] == "native-agent-dev"
    assert metrics["trace_id"] == "trace-123"
    assert metrics["model_name"] == "qwen-max"
    assert metrics["step_count"] == 9
    assert metrics["tool_call_count"] == 4
    assert metrics["latency_ms"] == 321
    assert metrics["approval_state"] == "required"
    assert metrics["retrieval_count"] == 2
    assert metrics["token_usage"] == {"input": 10, "output": 20}


def test_expired_pending_approval_moves_run_to_handoff():
    original_timeout = config.agent_approval_timeout_seconds
    config.agent_approval_timeout_seconds = 60
    try:
        created_at = datetime.now(UTC) - timedelta(minutes=5)
        run = {
            "run_id": "run-expired",
            "goal": "diagnose risky action",
            "status": "waiting_approval",
            "created_at": created_at,
            "updated_at": created_at,
            "final_report": None,
            "error_message": None,
        }
        events = [
            {
                "type": "tool_result",
                "stage": "tool",
                "message": "Approval required",
                "created_at": created_at,
                "payload": {
                    "tool_name": "RestartService",
                    "execution_status": "approval_required",
                    "approval_state": "required",
                    "arguments": {"service": "api"},
                },
            }
        ]
        service = build_service(run, events)

        expired = service.expire_pending_agent_approvals(limit=10)

        assert expired == [
            {
                "run_id": "run-expired",
                "tool_name": "RestartService",
                "decision": "expired",
                "expires_at": (created_at + timedelta(seconds=60)).isoformat(),
            }
        ]
        assert run["status"] == "handoff_required"
        assert run["error_message"] == "approval_expired"
        approval_decision = next(event for event in events if event["type"] == "approval_decision")
        assert approval_decision["payload"]["decision"] == "expired"
        assert approval_decision["payload"]["resume_status"] == "not_resumed"
        handoff = next(event for event in events if event["type"] == "handoff")
        assert handoff["payload"]["reason"] == "approval_expired"
    finally:
        config.agent_approval_timeout_seconds = original_timeout


def test_rejecting_approval_moves_run_to_handoff():
    created_at = datetime.now(UTC)
    run = {
        "run_id": "run-reject",
        "goal": "diagnose risky action",
        "status": "waiting_approval",
        "created_at": created_at,
        "updated_at": created_at,
        "final_report": None,
        "error_message": None,
    }
    events = [
        {
            "type": "tool_result",
            "stage": "tool",
            "message": "Approval required",
            "created_at": created_at,
            "payload": {
                "tool_name": "RestartService",
                "execution_status": "approval_required",
                "approval_state": "required",
            },
        }
    ]
    service = build_service(run, events)

    result = service.decide_agent_approval(
        "run-reject",
        tool_name="RestartService",
        decision="rejected",
        comment="too risky",
        actor="admin",
    )

    assert result is not None
    assert result["decision"] == "rejected"
    assert run["status"] == "handoff_required"
    assert run["error_message"] == "approval_rejected"
    handoff = next(event for event in events if event["type"] == "handoff")
    assert handoff["payload"]["reason"] == "approval_rejected"
