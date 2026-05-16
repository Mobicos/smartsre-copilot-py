from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from app.agent_runtime.decision import AgentDecision, AgentDecisionRuntime
from app.agent_runtime.runtime import AgentRuntime
from app.security.auth import Principal


class _RunStore:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.metrics: dict[str, Any] = {}
        self.status: str | None = None
        self.final_report: str | None = None
        self.created_at = datetime.now(UTC)
        self.updated_at = self.created_at

    def create_run(self, *, workspace_id, scene_id, session_id, goal):
        self.workspace_id = workspace_id
        self.scene_id = scene_id
        self.session_id = session_id
        self.goal = goal
        return "run-1"

    def append_event(self, run_id, *, event_type, stage, message, payload):
        self.events.append(
            {
                "run_id": run_id,
                "type": event_type,
                "stage": stage,
                "message": message,
                "payload": payload,
            }
        )

    def update_run(self, run_id, *, status, final_report=None, error_message=None):
        self.status = status
        self.final_report = final_report
        self.error_message = error_message
        self.updated_at = datetime.now(UTC)

    def update_run_metrics(self, run_id, **metrics):
        self.metrics = metrics

    def get_run(self, run_id):
        return {
            "run_id": run_id,
            "workspace_id": self.workspace_id,
            "scene_id": self.scene_id,
            "session_id": self.session_id,
            "status": self.status,
            "goal": self.goal,
            "final_report": self.final_report,
            "error_message": getattr(self, "error_message", None),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def list_events(self, run_id):
        return list(self.events)


class _SceneStore:
    scene = {
        "id": "scene-1",
        "workspace_id": "workspace-1",
        "tools": ["SearchLog"],
        "agent_config": {
            "decision_runtime_enabled": True,
            "bounded_react_loop_enabled": True,
            "max_steps": 1,
        },
    }

    def get_scene(self, scene_id: str):
        return self.scene if scene_id == "scene-1" else None


class _PolicyStore:
    def get_policy(self, tool_name: str):
        return None


class _ToolCatalog:
    async def get_tools(self, scope: str, *, force_refresh: bool = False):
        return [SimpleNamespace(name="SearchLog", description="Search logs")]


class _ToolExecutor:
    async def execute(self, tool, args, *, principal):
        return SimpleNamespace(
            tool_name=tool.name,
            status="success",
            arguments=args,
            output="log evidence",
            error=None,
        )


class _MetricsProvider:
    provider_name = "qwen"

    def decide(self, state):
        return AgentDecision(
            action_type="call_tool",
            selected_tool="SearchLog",
            tool_arguments={"query": state.goal.goal},
            reasoning_summary="Use logs to collect first evidence.",
        )

    def get_token_usage(self):
        return {
            "prompt_tokens": 12,
            "completion_tokens": 8,
            "total": 20,
            "source": "provider_usage",
        }

    def get_cost_estimate(self):
        return {"currency": "USD", "total_cost": 0.0012, "source": "provider_usage"}


class _BoundedOnlyDecisionRuntime(AgentDecisionRuntime):
    def run_graph_once(self, state):
        raise AssertionError("bounded loop path must not call run_graph_once")

    def decide_once(self, state):
        raise AssertionError("bounded loop path must not call decide_once directly")


@pytest.mark.asyncio
async def test_runtime_can_persist_bounded_loop_step_metrics():
    run_store = _RunStore()
    decision_runtime = _BoundedOnlyDecisionRuntime(provider=_MetricsProvider())  # type: ignore[arg-type]
    runtime = AgentRuntime(
        tool_catalog=_ToolCatalog(),
        tool_executor=_ToolExecutor(),
        scene_store=_SceneStore(),
        run_store=run_store,  # type: ignore[arg-type]
        policy_store=_PolicyStore(),  # type: ignore[arg-type]
        decision_runtime=decision_runtime,
    )

    events = [
        event
        async for event in runtime.run(
            scene_id="scene-1",
            session_id="session-1",
            goal="diagnose current alerts",
            principal=Principal(role="admin", subject="pytest"),
        )
    ]
    decision_event = next(event for event in run_store.events if event["type"] == "decision")

    assert events[-1].type == "complete"
    assert decision_event["payload"]["step_index"] == 0
    assert decision_event["payload"]["token_usage"] == {
        "prompt_tokens": 12,
        "completion_tokens": 8,
        "total": 20,
        "source": "provider_usage",
    }
    assert decision_event["payload"]["cost_estimate"] == {
        "currency": "USD",
        "total_cost": 0.0012,
        "source": "provider_usage",
    }
    assert run_store.metrics["token_usage"]["source"] == "provider_usage"
    assert run_store.metrics["cost_estimate"]["source"] == "provider_usage"
