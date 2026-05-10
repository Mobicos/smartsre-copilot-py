"""Agent scenario regression tests.

Golden-path and failure scenarios that exercise the Native Agent runtime
against persisted state, validating the end-to-end governance pipeline.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.agent_runtime import AgentRuntime
from app.application.scenario_regression_service import (
    ScenarioRegressionService,
)
from app.platform.persistence import (
    agent_run_repository,
    knowledge_base_repository,
    scene_repository,
    tool_policy_repository,
    workspace_repository,
)
from app.security.auth import Principal

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Mock tools and executors
# ---------------------------------------------------------------------------


class StaticCatalog:
    def __init__(self, tools):
        self._tools = tools

    async def get_tools(self, scope: str, *, force_refresh: bool = False):
        return self._tools


_TOOL_EVIDENCE_TEMPLATES: dict[str, str] = {
    "SearchLog": (
        "Found {count} error log entries in the last 15 minutes: "
        "'{sample_error}' — pattern indicates {diagnosis}."
    ),
    "SearchMetric": (
        "Metric query returned: p99 latency={p99}ms, error_rate={err}% — {diagnosis}."
    ),
    "RestartService": "Service restart command dispatched successfully — pod is rolling.",
    "get_current_time": "Current server time: 2026-05-09T10:32:00Z.",
}

_EVIDENCE_BY_TOOL: dict[str, dict[str, str]] = {
    "SearchLog": {
        "count": "127",
        "sample_error": "Connection refused to upstream:5432",
        "diagnosis": "upstream dependency connection exhaustion",
    },
    "SearchMetric": {
        "p99": "2340",
        "err": "12.7",
        "diagnosis": "elevated latency with elevated error rate suggesting downstream failure",
    },
}


class SuccessExecutor:
    async def execute(self, tool, args, *, principal):
        template = _TOOL_EVIDENCE_TEMPLATES.get(tool.name)
        if template:
            params = _EVIDENCE_BY_TOOL.get(tool.name, {})
            try:
                output = template.format(**params)
            except KeyError:
                output = f"Evidence from {tool.name}: operation completed successfully."
        else:
            output = f"Evidence from {tool.name}: operation completed successfully."
        return SimpleNamespace(
            tool_name=tool.name,
            status="success",
            output=output,
            error=None,
            arguments=args,
        )


class ApprovalRequiredExecutor:
    async def execute(self, tool, args, *, principal):
        return SimpleNamespace(
            tool_name=tool.name,
            status="approval_required",
            output=None,
            error=None,
            arguments=args,
            policy={
                "tool_name": tool.name,
                "risk_level": "high",
                "approval_required": True,
            },
            decision="approval_required",
            decision_reason="Tool requires explicit approval before execution",
            governance_payload=lambda: {
                "decision": "approval_required",
                "reason": "Tool requires explicit approval before execution",
                "policy": {"tool_name": tool.name, "risk_level": "high"},
            },
        )


class FailingExecutor:
    async def execute(self, tool, args, *, principal):
        raise RuntimeError("backend connection refused")


# ---------------------------------------------------------------------------
# Golden-path scenarios
# ---------------------------------------------------------------------------


async def _run_agent(*, tools, executor, scene_id, goal):
    runtime = AgentRuntime(
        tool_catalog=StaticCatalog(tools),
        tool_executor=executor,
        scene_store=scene_repository,
        run_store=agent_run_repository,
        policy_store=tool_policy_repository,
    )
    events = []
    async for event in runtime.run(
        scene_id=scene_id,
        session_id="scenario-test",
        goal=goal,
        principal=Principal(role="admin", subject="scenario-test"),
    ):
        events.append(event)
    return events


async def test_golden_latency_diagnosis():
    """P0: Diagnose latency with tool evidence and final report."""
    workspace_id = workspace_repository.create_workspace(name="SRE-Scenario")
    scene_id = scene_repository.create_scene(
        workspace_id,
        name="Latency",
        tool_names=["SearchLog", "SearchMetric"],
    )
    tools = [
        SimpleNamespace(name="SearchLog", description="Search logs"),
        SimpleNamespace(name="SearchMetric", description="Search metrics"),
    ]
    events = await _run_agent(
        tools=tools,
        executor=SuccessExecutor(),
        scene_id=scene_id,
        goal="Diagnose production latency spike on /api/orders",
    )

    last = events[-1]
    assert last.type == "complete"
    assert last.final_report is not None
    assert "latency" in last.final_report.lower() or "evidence" in last.final_report.lower()

    stored = agent_run_repository.list_events(last.run_id)
    types = [e["type"] for e in stored]
    assert "run_started" in types
    assert "hypothesis" in types
    assert "tool_call" in types
    assert "tool_result" in types
    assert "final_report" in types


async def test_golden_approval_required_high_risk():
    """P1: High-risk tool triggers approval_required status."""
    workspace_id = workspace_repository.create_workspace(name="SRE-Approval")
    scene_id = scene_repository.create_scene(
        workspace_id,
        name="Approval",
        tool_names=["RestartService"],
    )
    tool_policy_repository.upsert_policy(
        "RestartService",
        risk_level="critical",
        approval_required=True,
    )
    tools = [SimpleNamespace(name="RestartService", description="Restart a service")]

    events = await _run_agent(
        tools=tools,
        executor=ApprovalRequiredExecutor(),
        scene_id=scene_id,
        goal="Restart the order-service to resolve latency",
    )

    last = events[-1]
    stored = agent_run_repository.list_events(last.run_id)
    tool_results = [e for e in stored if e["type"] == "tool_result"]

    assert any(r["payload"].get("execution_status") == "approval_required" for r in tool_results)
    assert any(r["payload"].get("approval_state") == "required" for r in tool_results)


async def test_golden_knowledge_context_in_report():
    """P1: Knowledge context appears in the final report."""
    workspace_id = workspace_repository.create_workspace(name="SRE-KB")
    kb_id = knowledge_base_repository.create_knowledge_base(
        workspace_id,
        name="CLB Runbook",
        description="CLB incident response procedures",
        version="development",
    )
    scene_id = scene_repository.create_scene(
        workspace_id,
        name="KB-Scene",
        knowledge_base_ids=[kb_id],
    )
    events = await _run_agent(
        tools=[],
        executor=SuccessExecutor(),
        scene_id=scene_id,
        goal="Diagnose CLB 502 errors",
    )

    last = events[-1]
    stored = agent_run_repository.list_events(last.run_id)
    kb_events = [e for e in stored if e["type"] == "knowledge_context"]

    assert len(kb_events) > 0
    assert "CLB Runbook" in str(kb_events[0]["payload"])


async def test_golden_step_limit_enforced():
    """P0: Runtime enforces max_steps and records skipped tools."""
    workspace_id = workspace_repository.create_workspace(name="SRE-Limit")
    scene_id = scene_repository.create_scene(
        workspace_id,
        name="Limit-Scene",
        tool_names=["ToolA", "ToolB", "ToolC"],
        agent_config={"max_steps": 2},
    )
    tools = [
        SimpleNamespace(name="ToolA", description="Tool A"),
        SimpleNamespace(name="ToolB", description="Tool B"),
        SimpleNamespace(name="ToolC", description="Tool C"),
    ]

    events = await _run_agent(
        tools=tools,
        executor=SuccessExecutor(),
        scene_id=scene_id,
        goal="Run with step limit",
    )

    last = events[-1]
    stored = agent_run_repository.list_events(last.run_id)
    limit_events = [e for e in stored if e["type"] == "limit_reached"]

    assert len(limit_events) > 0
    assert len(limit_events[0]["payload"]["executed_tools"]) <= 2


async def test_golden_cpu_high():
    """P0: CPU saturation diagnosis with evidence and tool calls."""
    workspace_id = workspace_repository.create_workspace(name="SRE-CPU")
    scene_id = scene_repository.create_scene(
        workspace_id,
        name="CPU-High",
        tool_names=["SearchMetric", "SearchLog"],
    )
    tools = [
        SimpleNamespace(name="SearchMetric", description="Search metrics"),
        SimpleNamespace(name="SearchLog", description="Search logs"),
    ]
    events = await _run_agent(
        tools=tools,
        executor=SuccessExecutor(),
        scene_id=scene_id,
        goal="Diagnose CPU saturation on production hosts and identify the root-cause process",
    )

    last = events[-1]
    assert last.type == "complete"
    assert last.final_report is not None

    stored = agent_run_repository.list_events(last.run_id)
    types = [e["type"] for e in stored]
    assert "run_started" in types
    assert "tool_result" in types
    assert "final_report" in types


async def test_golden_http_5xx_spike():
    """P0: HTTP 5xx spike diagnosis with tool evidence."""
    workspace_id = workspace_repository.create_workspace(name="SRE-5XX")
    scene_id = scene_repository.create_scene(
        workspace_id,
        name="HTTP-5XX",
        tool_names=["SearchLog", "SearchMetric"],
    )
    tools = [
        SimpleNamespace(name="SearchLog", description="Search logs"),
        SimpleNamespace(name="SearchMetric", description="Search metrics"),
    ]
    events = await _run_agent(
        tools=tools,
        executor=SuccessExecutor(),
        scene_id=scene_id,
        goal="Diagnose a sudden increase in HTTP 5xx responses across the API gateway",
    )

    last = events[-1]
    assert last.type == "complete"
    assert last.final_report is not None

    stored = agent_run_repository.list_events(last.run_id)
    types = [e["type"] for e in stored]
    assert "run_started" in types
    assert "tool_result" in types
    assert "final_report" in types


async def test_golden_slow_response():
    """P0: Slow response time diagnosis with evidence."""
    workspace_id = workspace_repository.create_workspace(name="SRE-Slow")
    scene_id = scene_repository.create_scene(
        workspace_id,
        name="Slow-Response",
        tool_names=["SearchMetric", "SearchLog"],
    )
    tools = [
        SimpleNamespace(name="SearchMetric", description="Search metrics"),
        SimpleNamespace(name="SearchLog", description="Search logs"),
    ]
    events = await _run_agent(
        tools=tools,
        executor=SuccessExecutor(),
        scene_id=scene_id,
        goal="Diagnose elevated p99 response latency on the checkout service",
    )

    last = events[-1]
    assert last.type == "complete"
    assert last.final_report is not None

    stored = agent_run_repository.list_events(last.run_id)
    types = [e["type"] for e in stored]
    assert "run_started" in types
    assert "tool_result" in types
    assert "final_report" in types


async def test_golden_disk_full():
    """P1: Disk full incident diagnosis with tool evidence."""
    workspace_id = workspace_repository.create_workspace(name="SRE-Disk")
    scene_id = scene_repository.create_scene(
        workspace_id,
        name="Disk-Full",
        tool_names=["SearchMetric", "SearchLog"],
    )
    tools = [
        SimpleNamespace(name="SearchMetric", description="Search metrics"),
        SimpleNamespace(name="SearchLog", description="Search logs"),
    ]
    events = await _run_agent(
        tools=tools,
        executor=SuccessExecutor(),
        scene_id=scene_id,
        goal="Diagnose disk space exhaustion on database nodes",
    )

    last = events[-1]
    assert last.type == "complete"
    assert last.final_report is not None

    stored = agent_run_repository.list_events(last.run_id)
    types = [e["type"] for e in stored]
    assert "run_started" in types
    assert "tool_result" in types
    assert "final_report" in types


async def test_golden_dependency_failure():
    """P1: External dependency failure diagnosis with tool evidence."""
    workspace_id = workspace_repository.create_workspace(name="SRE-Dep")
    scene_id = scene_repository.create_scene(
        workspace_id,
        name="Dependency-Failure",
        tool_names=["SearchLog", "SearchMetric"],
    )
    tools = [
        SimpleNamespace(name="SearchLog", description="Search logs"),
        SimpleNamespace(name="SearchMetric", description="Search metrics"),
    ]
    events = await _run_agent(
        tools=tools,
        executor=SuccessExecutor(),
        scene_id=scene_id,
        goal="Diagnose upstream dependency failure causing cascading errors in the payment service",
    )

    last = events[-1]
    assert last.type == "complete"
    assert last.final_report is not None

    stored = agent_run_repository.list_events(last.run_id)
    types = [e["type"] for e in stored]
    assert "run_started" in types
    assert "tool_result" in types
    assert "final_report" in types


# ---------------------------------------------------------------------------
# Failure scenarios
# ---------------------------------------------------------------------------


async def test_failure_tool_execution_error():
    """Tool failure is recorded and run status is failed."""
    workspace_id = workspace_repository.create_workspace(name="SRE-Fail")
    scene_id = scene_repository.create_scene(
        workspace_id,
        name="Fail-Scene",
        tool_names=["BrokenTool"],
    )
    tools = [SimpleNamespace(name="BrokenTool", description="Broken")]

    events = await _run_agent(
        tools=tools,
        executor=FailingExecutor(),
        scene_id=scene_id,
        goal="Test failure handling",
    )

    last = events[-1]
    assert last.type == "error"
    assert last.status == "failed"

    stored = agent_run_repository.list_events(last.run_id)
    error_events = [e for e in stored if e["type"] == "error"]
    assert len(error_events) > 0


async def test_failure_empty_tool_catalog():
    """Empty catalog produces a report noting no tools were available."""
    workspace_id = workspace_repository.create_workspace(name="SRE-Empty")
    scene_id = scene_repository.create_scene(workspace_id, name="Empty-Scene")

    events = await _run_agent(
        tools=[],
        executor=SuccessExecutor(),
        scene_id=scene_id,
        goal="Diagnose with no tools",
    )

    last = events[-1]
    assert last.type == "complete"
    assert "External MCP tools are unavailable" in last.final_report


async def test_failure_governance_denied_disabled_tool():
    """Disabled tool results in denied governance decision."""
    workspace_id = workspace_repository.create_workspace(name="SRE-Denied")
    scene_id = scene_repository.create_scene(
        workspace_id,
        name="Denied-Scene",
        tool_names=["DisabledTool"],
    )
    tool_policy_repository.upsert_policy("DisabledTool", enabled=False)
    tools = [SimpleNamespace(name="DisabledTool", description="Disabled")]

    runtime = AgentRuntime(
        tool_catalog=StaticCatalog(tools),
        tool_executor=_DisabledToolExecutor(),
        scene_store=scene_repository,
        run_store=agent_run_repository,
        policy_store=tool_policy_repository,
    )
    events = []
    async for event in runtime.run(
        scene_id=scene_id,
        session_id="scenario-test",
        goal="Test disabled tool",
        principal=Principal(role="admin", subject="scenario-test"),
    ):
        events.append(event)

    last = events[-1]
    stored = agent_run_repository.list_events(last.run_id)
    tool_results = [e for e in stored if e["type"] == "tool_result"]

    assert any(r["payload"].get("execution_status") == "disabled" for r in tool_results)


class _DisabledToolExecutor:
    async def execute(self, tool, args, *, principal):
        return SimpleNamespace(
            tool_name=tool.name,
            status="disabled",
            output=None,
            error="Tool is disabled by policy",
            arguments=args,
            policy={"enabled": False},
            decision="denied",
            decision_reason="Tool is disabled by policy",
            governance_payload=lambda: {
                "decision": "denied",
                "reason": "Tool is disabled by policy",
                "policy": {"enabled": False},
            },
        )


async def test_failure_run_timeout():
    """Run timeout is recorded when total timeout is exceeded."""
    workspace_id = workspace_repository.create_workspace(name="SRE-Timeout")
    scene_id = scene_repository.create_scene(
        workspace_id,
        name="Timeout-Scene",
        tool_names=["SlowTool"],
        agent_config={"tool_timeout_seconds": 0.001, "run_timeout_seconds": 0.001},
    )

    class _SlowCatalog:
        async def get_tools(self, scope, *, force_refresh=False):
            await asyncio.sleep(0.05)
            return [SimpleNamespace(name="SlowTool", description="Slow")]

    runtime = AgentRuntime(
        tool_catalog=_SlowCatalog(),
        tool_executor=SuccessExecutor(),
        scene_store=scene_repository,
        run_store=agent_run_repository,
        policy_store=tool_policy_repository,
    )
    events = []
    async for event in runtime.run(
        scene_id=scene_id,
        session_id="scenario-test",
        goal="Test timeout",
        principal=Principal(role="admin", subject="scenario-test"),
    ):
        events.append(event)

    last = events[-1]
    assert last.type == "timeout"
    assert last.status == "failed"


class _ForbiddenToolExecutor:
    """Executor that denies tools based on capability mismatch."""

    async def execute(self, tool, args, *, principal):
        return SimpleNamespace(
            tool_name=tool.name,
            status="denied",
            output=None,
            error="Principal lacks required capability",
            arguments=args,
            policy={"capability": "admin:write"},
            decision="denied",
            decision_reason="Principal lacks required capability: admin:write",
            governance_payload=lambda: {
                "decision": "denied",
                "reason": "Principal lacks required capability: admin:write",
                "policy": {"capability": "admin:write"},
            },
        )


async def test_failure_forbidden_tool():
    """Forbidden tool (capability mismatch) results in denied governance decision."""
    workspace_id = workspace_repository.create_workspace(name="SRE-Forbidden")
    scene_id = scene_repository.create_scene(
        workspace_id,
        name="Forbidden-Scene",
        tool_names=["DangerousAction"],
    )
    tools = [SimpleNamespace(name="DangerousAction", description="Admin-only action")]

    runtime = AgentRuntime(
        tool_catalog=StaticCatalog(tools),
        tool_executor=_ForbiddenToolExecutor(),
        scene_store=scene_repository,
        run_store=agent_run_repository,
        policy_store=tool_policy_repository,
    )
    events = []
    async for event in runtime.run(
        scene_id=scene_id,
        session_id="scenario-test",
        goal="Test forbidden tool",
        principal=Principal(role="viewer", subject="scenario-test"),
    ):
        events.append(event)

    last = events[-1]
    stored = agent_run_repository.list_events(last.run_id)
    tool_results = [e for e in stored if e["type"] == "tool_result"]

    assert any(r["payload"].get("execution_status") == "denied" for r in tool_results)


async def test_failure_empty_knowledge():
    """Empty knowledge base produces a report noting no knowledge context."""
    workspace_id = workspace_repository.create_workspace(name="SRE-EmptyKB")
    kb_id = knowledge_base_repository.create_knowledge_base(
        workspace_id,
        name="Empty-KB",
        description="Empty knowledge base with no documents",
        version="development",
    )
    scene_id = scene_repository.create_scene(
        workspace_id,
        name="EmptyKB-Scene",
        knowledge_base_ids=[kb_id],
    )
    events = await _run_agent(
        tools=[],
        executor=SuccessExecutor(),
        scene_id=scene_id,
        goal="Diagnose issue with empty knowledge base",
    )

    last = events[-1]
    assert last.type == "complete"
    assert last.final_report is not None
    # Report should acknowledge lack of knowledge context
    stored = agent_run_repository.list_events(last.run_id)
    kb_events = [e for e in stored if e["type"] == "knowledge_context"]
    # With empty KB, either no kb events or events noting empty content
    report_lower = last.final_report.lower()
    assert (
        len(kb_events) == 0
        or "no" in report_lower
        or "empty" in report_lower
        or "unavailable" in report_lower
    )


# ---------------------------------------------------------------------------
# ScenarioRegressionService evaluation tests
# ---------------------------------------------------------------------------


async def test_scenario_regression_service_evaluates_completed_run():
    """ScenarioRegressionService correctly evaluates a completed run."""
    workspace_id = workspace_repository.create_workspace(name="SRE-Eval")
    scene_id = scene_repository.create_scene(
        workspace_id,
        name="Eval-Scene",
        tool_names=["SearchLog"],
    )
    tools = [SimpleNamespace(name="SearchLog", description="Search logs")]

    events = await _run_agent(
        tools=tools,
        executor=SuccessExecutor(),
        scene_id=scene_id,
        goal="Diagnose latency spike with evidence and tool calls",
    )

    run_id = events[-1].run_id
    service = ScenarioRegressionService(agent_run_repository=agent_run_repository)

    result = service.evaluate_run(
        scenario_id="agent-runtime-safety-boundary",
        run_id=run_id,
    )

    assert result is not None
    assert result["status"] == "passed"
    assert result["score"] > 0.5
    assert result["run_id"] == run_id
