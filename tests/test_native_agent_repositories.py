from __future__ import annotations

from app.domains.native_agent import (
    AgentEvent,
    AgentRun,
    KnowledgeBase,
    Scene,
    ToolPolicy,
    Workspace,
)
from app.platform.persistence import (
    agent_feedback_repository,
    agent_run_repository,
    knowledge_base_repository,
    scene_repository,
    tool_policy_repository,
    workspace_repository,
)


def test_workspace_scene_and_knowledge_base_repositories_persist_product_closure():
    workspace_id = workspace_repository.create_workspace(
        name="SRE Team",
        description="Primary on-call workspace",
    )
    knowledge_base_id = knowledge_base_repository.create_knowledge_base(
        workspace_id,
        name="CLB Runbook",
        description="CLB troubleshooting notes",
        version="0.0.1",
    )
    scene_id = scene_repository.create_scene(
        workspace_id,
        name="CLB 日志分析",
        description="Analyze CLB error requests",
        knowledge_base_ids=[knowledge_base_id],
        tool_names=["SearchLog"],
        agent_config={"mode": "diagnosis"},
    )

    workspaces = workspace_repository.list_workspaces()
    scenes = scene_repository.list_scenes(workspace_id=workspace_id)
    scene = scene_repository.get_scene(scene_id)

    assert workspaces[0]["id"] == workspace_id
    assert scenes[0]["id"] == scene_id
    assert scene is not None
    assert scene["workspace_id"] == workspace_id
    assert scene["knowledge_bases"][0]["id"] == knowledge_base_id
    assert scene["tools"] == ["SearchLog"]
    assert scene["agent_config"] == {"mode": "diagnosis"}

    workspace_entity = Workspace.from_record(workspaces[0])
    knowledge_base_entity = KnowledgeBase.from_record(scene["knowledge_bases"][0])
    scene_entity = Scene.from_record(scene)

    assert workspace_entity.id == workspace_id
    assert knowledge_base_entity.name == "CLB Runbook"
    assert scene_entity.knowledge_bases[0].id == knowledge_base_id
    assert scene_entity.tool_names == ["SearchLog"]
    assert scene_entity.to_dict()["agent_config"] == {"mode": "diagnosis"}


def test_tool_policy_repository_upserts_and_lists_policy():
    policy = tool_policy_repository.upsert_policy(
        "SearchLog",
        scope="diagnosis",
        risk_level="low",
        capability="aiops:run",
        enabled=False,
        approval_required=True,
    )

    loaded = tool_policy_repository.get_policy("SearchLog")
    policies = tool_policy_repository.list_policies()

    assert loaded == policy
    assert policies[0]["tool_name"] == "SearchLog"
    assert policies[0]["enabled"] is False
    assert policies[0]["approval_required"] is True

    policy_entity = ToolPolicy.from_record(policy)

    assert policy_entity.tool_name == "SearchLog"
    assert policy_entity.requires_approval() is True
    assert policy_entity.to_dict()["enabled"] is False


def test_agent_run_repository_persists_ordered_trajectory_and_feedback():
    workspace_id = workspace_repository.create_workspace(name="SRE Team")
    scene_id = scene_repository.create_scene(workspace_id, name="Default Diagnosis")
    run_id = agent_run_repository.create_run(
        workspace_id=workspace_id,
        scene_id=scene_id,
        session_id="session-1",
        goal="diagnose alerts",
    )

    agent_run_repository.append_event(
        run_id,
        event_type="hypothesis",
        stage="reasoning",
        message="CPU saturation is possible",
        payload={"hypothesis": "cpu"},
    )
    agent_run_repository.append_event(
        run_id,
        event_type="tool_result",
        stage="tool",
        message="SearchLog completed",
        payload={"tool": "SearchLog"},
    )
    agent_run_repository.update_run(run_id, status="completed", final_report="root cause")
    agent_feedback_repository.create_feedback(run_id, rating="up", comment="useful")

    run = agent_run_repository.get_run(run_id)
    events = agent_run_repository.list_events(run_id)
    feedback = agent_feedback_repository.list_feedback(run_id)

    assert run is not None
    assert run["status"] == "completed"
    assert run["final_report"] == "root cause"
    assert [event["type"] for event in events] == ["hypothesis", "tool_result"]
    assert events[0]["payload"] == {"hypothesis": "cpu"}
    assert feedback[0]["rating"] == "up"

    run_entity = AgentRun.from_record(run)
    event_entity = AgentEvent.from_record(events[0])

    assert run_entity.id == run_id
    assert run_entity.is_completed() is True
    assert event_entity.type == "hypothesis"
    assert event_entity.payload == {"hypothesis": "cpu"}
