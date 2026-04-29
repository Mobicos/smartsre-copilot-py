from __future__ import annotations

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

    def create_run(self, *, workspace_id, scene_id, session_id, goal):
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

    def update_run(self, run_id, *, status, final_report=None):
        self.final_report = final_report


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
                    "version": "1.0.0",
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
                "version": "1.0.0",
            }
        ],
        "summary": "已加载 1 个知识库: Runbook",
    }
    assert action.approval_state == "required"
    assert action.policy_snapshot.risk_level == "high"
    assert "暂无工具证据" in synthesizer.build_report(state)
    assert "外部 MCP 工具不可用" in synthesizer.unavailable_report(state.goal)


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
    assert "外部 MCP 工具不可用" in str(run_store.final_report)


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
    assert "外部 MCP 工具不可用" in events[-1].final_report
    assert agent_run_repository.list_events(events[-1].run_id)[0]["type"] == "run_started"
    assert events[-1].to_dict()["type"] == "complete"


@pytest.mark.asyncio
async def test_agent_runtime_records_scene_knowledge_context_in_trajectory_and_report():
    workspace_id = workspace_repository.create_workspace(name="SRE")
    knowledge_base_id = knowledge_base_repository.create_knowledge_base(
        workspace_id,
        name="CLB Runbook",
        description="CLB incident response",
        version="1.2.0",
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
                "version": "1.2.0",
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

    assert [event["type"] for event in stored_events] == [
        "run_started",
        "hypothesis",
        "tool_call",
        "tool_result",
        "final_report",
    ]
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
