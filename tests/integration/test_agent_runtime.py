from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.agent_runtime import (
    AgentPlanner,
    AgentRuntime,
    AgentRuntimeEvent,
    EvidenceItem,
    Hypothesis,
    KnowledgeContextProvider,
    ReportSynthesizer,
    ToolAction,
    ToolPolicyGate,
    ToolPolicySnapshot,
)
from app.config import config
from app.platform.persistence import (
    agent_run_repository,
    knowledge_base_repository,
    scene_repository,
    tool_policy_repository,
    workspace_repository,
)
from app.security.auth import Principal


class StaticCatalog:
    def __init__(self, tools):
        self._tools = tools

    async def get_tools(self, scope: str, *, force_refresh: bool = False):
        return self._tools


class StaticExecutor:
    async def execute(self, tool, args, *, principal):
        return SimpleNamespace(
            tool_name=tool.name,
            status="success",
            output=f"{tool.name} evidence",
            error=None,
            arguments=args,
        )


class FailingExecutor:
    async def execute(self, tool, args, *, principal):
        raise RuntimeError("tool backend unavailable")


class PolicyAwareExecutor:
    async def execute(self, tool, args, *, principal):
        return SimpleNamespace(
            tool_name=tool.name,
            status=tool.status,
            output=None,
            error=getattr(tool, "error", None),
            arguments=args,
            policy=getattr(tool, "policy", None),
            decision=getattr(tool, "decision", "executed"),
            decision_reason=getattr(tool, "decision_reason", None),
            governance_payload=lambda: {
                "decision": getattr(tool, "decision", "executed"),
                "reason": getattr(tool, "decision_reason", None),
                "policy": getattr(tool, "policy", None),
            },
        )


class EmptyEvidenceExecutor:
    async def execute(self, tool, args, *, principal):
        return SimpleNamespace(
            tool_name=tool.name,
            status="success",
            output="",
            error=None,
            arguments=args,
        )


class SlowExecutor:
    def __init__(self, *, delay_seconds: float):
        self._delay_seconds = delay_seconds

    async def execute(self, tool, args, *, principal):
        await asyncio.sleep(self._delay_seconds)
        return SimpleNamespace(
            tool_name=tool.name,
            status="success",
            output=f"{tool.name} evidence",
            error=None,
            arguments=args,
        )


class CancellingExecutor:
    async def execute(self, tool, args, *, principal):
        raise asyncio.CancelledError


class MemorySceneStore:
    def __init__(self):
        self.scene = {
            "id": "scene-1",
            "workspace_id": "workspace-1",
            "tools": [],
        }

    def get_scene(self, scene_id: str):
        return self.scene if scene_id == self.scene["id"] else None


class MemoryRunStore:
    def __init__(self):
        self.events = []
        self.final_report = None
        self.status = None
        self.error_message = None
        self.metrics = {}
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
            "workspace_id": getattr(self, "workspace_id", "workspace-1"),
            "scene_id": getattr(self, "scene_id", "scene-1"),
            "session_id": getattr(self, "session_id", "session-1"),
            "status": self.status,
            "goal": getattr(self, "goal", "diagnose"),
            "final_report": self.final_report,
            "error_message": self.error_message,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def list_events(self, run_id):
        return list(self.events)


class MemoryPolicyStore:
    def __init__(self, policies=None):
        self._policies = policies or {}

    def get_policy(self, tool_name: str):
        return self._policies.get(tool_name)


def test_agent_runtime_core_components_shape_agent_loop():
    planner = AgentPlanner()
    knowledge_provider = KnowledgeContextProvider()
    policy_gate = ToolPolicyGate(
        policy_store=MemoryPolicyStore(
            {
                "SearchLog": {
                    "tool_name": "SearchLog",
                    "scope": "diagnosis",
                    "risk_level": "high",
                    "capability": "logs:read",
                    "enabled": True,
                    "approval_required": True,
                }
            }
        )
    )
    synthesizer = ReportSynthesizer()

    state = planner.create_initial_state("diagnose latency")
    knowledge_context = knowledge_provider.build_context(
        {
            "knowledge_bases": [
                {
                    "id": "kb-1",
                    "name": "Runbook",
                    "description": "CLB incident runbook",
                    "version": "development",
                }
            ]
        }
    )
    action = policy_gate.create_action("SearchLog", goal=state.goal)

    assert planner.select_tool_names({"tools": ["SearchLog"]}) == ["SearchLog"]
    assert (
        state.hypothesis.summary
        == "围绕目标“diagnose latency”优先验证告警、日志、指标和近期变更证据。"
    )
    assert knowledge_context.to_event_payload() == {
        "knowledge_bases": [
            {
                "id": "kb-1",
                "name": "Runbook",
                "description": "CLB incident runbook",
                "version": "development",
            }
        ],
        "summary": "已加载 1 个知识库: Runbook",
    }
    assert action.approval_state == "required"
    assert action.policy_snapshot.risk_level == "high"
    assert "No tool evidence was collected." in synthesizer.build_report(state)
    assert "External MCP tools are unavailable" in synthesizer.unavailable_report(state.goal)


def test_runtime_safety_config_prefers_env_then_scene_then_hardcoded(monkeypatch):
    monkeypatch.setattr(config, "agent_max_steps", 9)
    monkeypatch.setattr(config, "agent_step_timeout_seconds", 19.0)
    monkeypatch.setattr(config, "agent_total_timeout_seconds", 29.0)

    from app.agent_runtime.runtime import RuntimeSafetyConfig

    env_defaults = RuntimeSafetyConfig.from_scene({"agent_config": {}})
    overridden = RuntimeSafetyConfig.from_scene(
        {
            "agent_config": {
                "max_steps": 3,
                "tool_timeout_seconds": 7,
                "run_timeout_seconds": 11,
            }
        }
    )
    invalid = RuntimeSafetyConfig.from_scene(
        {
            "agent_config": {
                "max_steps": 0,
                "tool_timeout_seconds": "never",
                "run_timeout_seconds": -1,
            }
        }
    )

    assert env_defaults.to_dict() == {
        "max_steps": 9,
        "tool_timeout_seconds": 19.0,
        "run_timeout_seconds": 29.0,
    }
    assert overridden.to_dict() == {
        "max_steps": 3,
        "tool_timeout_seconds": 7.0,
        "run_timeout_seconds": 11.0,
    }
    assert invalid.to_dict() == env_defaults.to_dict()


def test_agent_runtime_state_objects_describe_reasoning_and_evidence():
    hypothesis = Hypothesis.from_goal("diagnose latency")
    action = ToolAction.from_tool_name(
        "SearchLog",
        goal="diagnose latency",
        policy={
            "tool_name": "SearchLog",
            "scope": "diagnosis",
            "risk_level": "high",
            "capability": "logs:read",
            "enabled": True,
            "approval_required": True,
        },
    )
    result = SimpleNamespace(
        tool_name="SearchLog",
        status="success",
        output="latency spike evidence",
        error=None,
        arguments=action.arguments,
    )
    evidence = EvidenceItem.from_tool_result(result)

    assert (
        hypothesis.summary == "围绕目标“diagnose latency”优先验证告警、日志、指标和近期变更证据。"
    )
    assert action.tool_name == "SearchLog"
    assert action.arguments == {"query": "diagnose latency", "keyword": "diagnose latency"}
    assert action.policy_snapshot == ToolPolicySnapshot(
        tool_name="SearchLog",
        scope="diagnosis",
        risk_level="high",
        capability="logs:read",
        enabled=True,
        approval_required=True,
    )
    assert action.approval_state == "required"
    assert action.execution_status == "pending"
    assert action.to_event_payload()["policy"]["risk_level"] == "high"
    assert action.mark_executed("success").execution_status == "success"
    assert evidence.to_report_line() == "SearchLog: latency spike evidence"


@pytest.mark.asyncio
async def test_agent_runtime_accepts_injected_persistence_ports():
    run_store = MemoryRunStore()
    runtime = AgentRuntime(
        tool_catalog=StaticCatalog([]),
        tool_executor=StaticExecutor(),
        scene_store=MemorySceneStore(),
        run_store=run_store,
        policy_store=MemoryPolicyStore(),
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

    assert events[-1].run_id == "run-1"
    assert run_store.events[0]["type"] == "run_started"
    assert run_store.events[-1]["type"] == "final_report"
    assert "External MCP tools are unavailable" in str(run_store.final_report)
    assert run_store.metrics["runtime_version"] == "native-agent-dev"
    assert run_store.metrics["trace_id"] == "run-1"
    assert run_store.metrics["model_name"] == "deterministic-native-agent"
    assert run_store.metrics["step_count"] >= 1
    assert run_store.metrics["tool_call_count"] == 0
    assert run_store.metrics["approval_state"] == "not_required"
    assert run_store.metrics["retrieval_count"] == 0


@pytest.mark.asyncio
async def test_agent_runtime_marks_run_failed_and_records_error_event():
    run_store = MemoryRunStore()
    scene_store = MemorySceneStore()
    scene_store.scene["tools"] = ["SearchLog"]
    runtime = AgentRuntime(
        tool_catalog=StaticCatalog([SimpleNamespace(name="SearchLog", description="Search logs")]),
        tool_executor=FailingExecutor(),
        scene_store=scene_store,
        run_store=run_store,
        policy_store=MemoryPolicyStore(),
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

    assert events[-1].type == "error"
    assert events[-1].status == "failed"
    assert run_store.status == "failed"
    assert run_store.error_message == "RuntimeError: tool backend unavailable"
    assert run_store.events[-1]["type"] == "error"
    assert run_store.events[-1]["payload"] == {
        "error_type": "RuntimeError",
        "error_message": "tool backend unavailable",
        "runtime_safety": {
            "max_steps": 5,
            "tool_timeout_seconds": 30.0,
            "run_timeout_seconds": 120.0,
        },
    }
    assert run_store.metrics["error_type"] == "RuntimeError"
    assert run_store.metrics["tool_call_count"] == 1


@pytest.mark.asyncio
async def test_agent_runtime_applies_default_step_limit_and_records_skipped_tools():
    run_store = MemoryRunStore()
    scene_store = MemorySceneStore()
    scene_store.scene["tools"] = [f"Tool{i}" for i in range(6)]
    runtime = AgentRuntime(
        tool_catalog=StaticCatalog(
            [SimpleNamespace(name=f"Tool{i}", description=f"Tool {i}") for i in range(6)]
        ),
        tool_executor=StaticExecutor(),
        scene_store=scene_store,
        run_store=run_store,
        policy_store=MemoryPolicyStore(),
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

    tool_calls = [event for event in run_store.events if event["type"] == "tool_call"]
    limit_event = next(event for event in run_store.events if event["type"] == "limit_reached")

    assert events[-1].type == "complete"
    assert len(tool_calls) == 5
    assert limit_event["payload"] == {
        "max_steps": 5,
        "executed_tools": ["Tool0", "Tool1", "Tool2", "Tool3", "Tool4"],
        "skipped_tools": ["Tool5"],
    }
    assert "Execution Boundaries" in str(run_store.final_report)
    assert "Tool5" in str(run_store.final_report)


@pytest.mark.asyncio
async def test_agent_runtime_allows_scene_config_to_override_step_limit(monkeypatch):
    run_store = MemoryRunStore()
    scene_store = MemorySceneStore()
    scene_store.scene["tools"] = ["Tool0", "Tool1", "Tool2"]
    scene_store.scene["agent_config"] = {
        "max_steps": 2,
        "tool_timeout_seconds": 1,
        "run_timeout_seconds": 5,
    }
    monkeypatch.setattr(config, "agent_max_steps", 8)
    monkeypatch.setattr(config, "agent_step_timeout_seconds", 13.0)
    monkeypatch.setattr(config, "agent_total_timeout_seconds", 23.0)
    runtime = AgentRuntime(
        tool_catalog=StaticCatalog(
            [SimpleNamespace(name=f"Tool{i}", description=f"Tool {i}") for i in range(3)]
        ),
        tool_executor=StaticExecutor(),
        scene_store=scene_store,
        run_store=run_store,
        policy_store=MemoryPolicyStore(),
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

    run_started = run_store.events[0]
    limit_event = next(event for event in run_store.events if event["type"] == "limit_reached")

    assert events[-1].type == "complete"
    assert run_started["payload"]["runtime_safety"] == {
        "max_steps": 2,
        "tool_timeout_seconds": 1.0,
        "run_timeout_seconds": 5.0,
    }
    assert limit_event["payload"]["executed_tools"] == ["Tool0", "Tool1"]
    assert limit_event["payload"]["skipped_tools"] == ["Tool2"]


@pytest.mark.asyncio
async def test_agent_runtime_ignores_invalid_scene_safety_config_values():
    run_store = MemoryRunStore()
    scene_store = MemorySceneStore()
    scene_store.scene["agent_config"] = {
        "max_steps": 0,
        "tool_timeout_seconds": "never",
        "run_timeout_seconds": -1,
    }
    runtime = AgentRuntime(
        tool_catalog=StaticCatalog([]),
        tool_executor=StaticExecutor(),
        scene_store=scene_store,
        run_store=run_store,
        policy_store=MemoryPolicyStore(),
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

    assert events[-1].type == "complete"
    assert run_store.events[0]["payload"]["runtime_safety"] == {
        "max_steps": config.agent_max_steps,
        "tool_timeout_seconds": config.agent_step_timeout_seconds,
        "run_timeout_seconds": config.agent_total_timeout_seconds,
    }


@pytest.mark.asyncio
async def test_agent_runtime_records_tool_timeout_and_completes_run():
    run_store = MemoryRunStore()
    scene_store = MemorySceneStore()
    scene_store.scene["tools"] = ["SearchLog"]
    scene_store.scene["agent_config"] = {
        "tool_timeout_seconds": 0.001,
        "run_timeout_seconds": 1,
    }
    runtime = AgentRuntime(
        tool_catalog=StaticCatalog([SimpleNamespace(name="SearchLog", description="Search logs")]),
        tool_executor=SlowExecutor(delay_seconds=0.05),
        scene_store=scene_store,
        run_store=run_store,
        policy_store=MemoryPolicyStore(),
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

    tool_result = next(event for event in run_store.events if event["type"] == "tool_result")

    assert events[-1].type == "complete"
    assert run_store.status == "completed"
    assert tool_result["payload"]["execution_status"] == "timeout"
    assert tool_result["payload"]["error"] == "Tool execution timed out after 0.001 seconds"
    assert tool_result["payload"]["governance"] == {
        "decision": "timeout",
        "reason": "Tool execution exceeded timeout: 0.001 seconds",
        "policy": {
            "tool_name": "SearchLog",
            "scope": "diagnosis",
            "risk_level": "low",
            "capability": None,
            "enabled": True,
            "approval_required": False,
        },
    }


@pytest.mark.asyncio
async def test_agent_runtime_records_audit_friendly_tool_governance_payload():
    run_store = MemoryRunStore()
    scene_store = MemorySceneStore()
    scene_store.scene["tools"] = ["SearchLog"]
    policy = {
        "tool_name": "SearchLog",
        "scope": "diagnosis",
        "risk_level": "high",
        "capability": "logs:read",
        "enabled": True,
        "approval_required": True,
    }
    tool = SimpleNamespace(
        name="SearchLog",
        description="Search logs",
        status="approval_required",
        decision="approval_required",
        decision_reason="Tool requires explicit approval before execution",
        policy=policy,
    )
    runtime = AgentRuntime(
        tool_catalog=StaticCatalog([tool]),
        tool_executor=PolicyAwareExecutor(),
        scene_store=scene_store,
        run_store=run_store,
        policy_store=MemoryPolicyStore({"SearchLog": policy}),
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

    tool_result = next(event for event in run_store.events if event["type"] == "tool_result")

    assert events[-1].type == "complete"
    assert tool_result["payload"]["policy"] == policy
    assert tool_result["payload"]["governance"] == {
        "decision": "approval_required",
        "reason": "Tool requires explicit approval before execution",
        "policy": policy,
    }


@pytest.mark.asyncio
async def test_agent_runtime_marks_run_failed_when_run_timeout_is_exceeded():
    class SlowCatalog:
        def __init__(self, tools):
            self._tools = tools

        async def get_tools(self, scope: str, *, force_refresh: bool = False):
            await asyncio.sleep(0.05)
            return self._tools

    run_store = MemoryRunStore()
    scene_store = MemorySceneStore()
    scene_store.scene["tools"] = ["SearchLog"]
    scene_store.scene["agent_config"] = {
        "tool_timeout_seconds": 1,
        "run_timeout_seconds": 0.001,
    }
    runtime = AgentRuntime(
        tool_catalog=SlowCatalog([SimpleNamespace(name="SearchLog", description="Search logs")]),
        tool_executor=SlowExecutor(delay_seconds=0.05),
        scene_store=scene_store,
        run_store=run_store,
        policy_store=MemoryPolicyStore(),
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

    assert events[-1].type == "timeout"
    assert events[-1].status == "failed"
    assert run_store.status == "failed"
    assert run_store.events[-1]["type"] == "timeout"
    assert run_store.events[-1]["payload"]["error_type"] == "TimeoutError"
    assert run_store.events[-1]["payload"]["timeout_scope"] == "run"
    assert run_store.events[-1]["payload"]["runtime_safety"]["run_timeout_seconds"] == 0.001


@pytest.mark.asyncio
async def test_agent_runtime_records_cancellation_and_reraises():
    run_store = MemoryRunStore()
    scene_store = MemorySceneStore()
    scene_store.scene["tools"] = ["SearchLog"]
    runtime = AgentRuntime(
        tool_catalog=StaticCatalog([SimpleNamespace(name="SearchLog", description="Search logs")]),
        tool_executor=CancellingExecutor(),
        scene_store=scene_store,
        run_store=run_store,
        policy_store=MemoryPolicyStore(),
    )

    with pytest.raises(asyncio.CancelledError):
        async for _event in runtime.run(
            scene_id="scene-1",
            session_id="session-1",
            goal="diagnose current alerts",
            principal=Principal(role="admin", subject="pytest"),
        ):
            pass

    assert run_store.status == "cancelled"
    assert run_store.error_message == "Agent run cancelled"
    assert run_store.events[-1]["type"] == "cancelled"


@pytest.mark.asyncio
async def test_agent_runtime_reports_unavailable_external_tools_without_fabricating_names():
    workspace_id = workspace_repository.create_workspace(name="SRE")
    scene_id = scene_repository.create_scene(workspace_id, name="Default")
    runtime = AgentRuntime(tool_catalog=StaticCatalog([]), tool_executor=StaticExecutor())

    events = [
        event
        async for event in runtime.run(
            scene_id=scene_id,
            session_id="session-1",
            goal="diagnose current alerts",
            principal=Principal(role="admin", subject="pytest"),
        )
    ]

    assert isinstance(events[-1], AgentRuntimeEvent)
    assert events[-1].type == "complete"
    assert "External MCP tools are unavailable" in events[-1].final_report
    assert agent_run_repository.list_events(events[-1].run_id)[0]["type"] == "run_started"
    assert events[-1].to_dict()["type"] == "complete"


@pytest.mark.asyncio
async def test_agent_runtime_records_scene_knowledge_context_in_trajectory_and_report():
    workspace_id = workspace_repository.create_workspace(name="SRE")
    knowledge_base_id = knowledge_base_repository.create_knowledge_base(
        workspace_id,
        name="CLB Runbook",
        description="CLB incident response",
        version="development",
    )
    scene_id = scene_repository.create_scene(
        workspace_id,
        name="Default",
        knowledge_base_ids=[knowledge_base_id],
    )
    runtime = AgentRuntime(tool_catalog=StaticCatalog([]), tool_executor=StaticExecutor())

    events = [
        event
        async for event in runtime.run(
            scene_id=scene_id,
            session_id="session-1",
            goal="diagnose current alerts",
            principal=Principal(role="admin", subject="pytest"),
        )
    ]

    stored_events = agent_run_repository.list_events(events[-1].run_id)
    knowledge_event = next(event for event in stored_events if event["type"] == "knowledge_context")

    assert knowledge_event["payload"] == {
        "knowledge_bases": [
            {
                "id": knowledge_base_id,
                "name": "CLB Runbook",
                "description": "CLB incident response",
                "version": "development",
            }
        ],
        "summary": "已加载 1 个知识库: CLB Runbook",
    }
    assert "CLB Runbook" in events[-1].final_report


@pytest.mark.asyncio
async def test_agent_runtime_records_tool_trajectory_and_final_report():
    workspace_id = workspace_repository.create_workspace(name="SRE")
    scene_id = scene_repository.create_scene(
        workspace_id,
        name="CLB",
        tool_names=["SearchLog"],
    )
    tool = SimpleNamespace(name="SearchLog", description="Search logs")
    runtime = AgentRuntime(tool_catalog=StaticCatalog([tool]), tool_executor=StaticExecutor())

    events = [
        event
        async for event in runtime.run(
            scene_id=scene_id,
            session_id="session-1",
            goal="diagnose clb errors",
            principal=Principal(role="admin", subject="pytest"),
        )
    ]

    run_id = events[-1].run_id
    stored_events = agent_run_repository.list_events(run_id)

    event_types = [event["type"] for event in stored_events]
    assert event_types[0] == "run_started"
    assert "tool_call" in event_types
    assert "final_report" in event_types
    assert event_types[-1] == "final_report"
    assert events[-1].type == "complete"
    assert "SearchLog evidence" in events[-1].final_report


@pytest.mark.asyncio
async def test_agent_runtime_records_tool_governance_snapshot_in_trajectory():
    workspace_id = workspace_repository.create_workspace(name="SRE")
    scene_id = scene_repository.create_scene(
        workspace_id,
        name="CLB",
        tool_names=["SearchLog"],
    )
    tool_policy_repository.upsert_policy(
        "SearchLog",
        risk_level="high",
        capability="logs:read",
        approval_required=True,
    )
    tool = SimpleNamespace(name="SearchLog", description="Search logs")
    runtime = AgentRuntime(tool_catalog=StaticCatalog([tool]))

    events = [
        event
        async for event in runtime.run(
            scene_id=scene_id,
            session_id="session-1",
            goal="diagnose clb errors",
            principal=Principal(role="admin", subject="pytest"),
        )
    ]

    stored_events = agent_run_repository.list_events(events[-1].run_id)
    tool_call = next(event for event in stored_events if event["type"] == "tool_call")
    tool_result = next(event for event in stored_events if event["type"] == "tool_result")

    assert tool_call["payload"]["policy"] == {
        "tool_name": "SearchLog",
        "scope": "diagnosis",
        "risk_level": "high",
        "capability": "logs:read",
        "enabled": True,
        "approval_required": True,
    }
    assert tool_call["payload"]["approval_state"] == "required"
    assert tool_call["payload"]["execution_status"] == "pending"
    assert tool_result["payload"]["policy"]["tool_name"] == "SearchLog"
    assert tool_result["payload"]["approval_state"] == "required"
    assert tool_result["payload"]["execution_status"] == "approval_required"


@pytest.mark.asyncio
async def test_decision_runtime_records_observation_evidence_recovery_and_handoff():
    run_store = MemoryRunStore()
    scene_store = MemorySceneStore()
    scene_store.scene["tools"] = ["SearchLog"]
    scene_store.scene["agent_config"] = {
        "decision_runtime_enabled": True,
        "max_steps": 2,
    }
    runtime = AgentRuntime(
        tool_catalog=StaticCatalog([SimpleNamespace(name="SearchLog", description="Search logs")]),
        tool_executor=EmptyEvidenceExecutor(),
        scene_store=scene_store,
        run_store=run_store,
        policy_store=MemoryPolicyStore(),
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
    event_types = [event["type"] for event in run_store.events]

    assert events[-1].type in ("handoff", "complete")
    assert run_store.status in ("handoff_required", "completed")
    assert "run_started" in event_types
    assert "decision" in event_types
    assert "final_report" in event_types or "handoff" in event_types
