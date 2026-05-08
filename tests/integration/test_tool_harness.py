from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agent_runtime import ToolExecutor, ToolPolicyRepositoryAdapter, ToolSchema
from app.platform.persistence import tool_policy_repository
from app.security.auth import Principal


class AsyncTool:
    name = "SearchLog"
    description = "Search logs"

    async def ainvoke(self, args):
        return {"ok": True, "args": args}


class MemoryPolicyStore:
    def __init__(self, policies=None):
        self._policies = policies or {}

    def get_policy(self, tool_name: str):
        return self._policies.get(tool_name)


@pytest.mark.asyncio
async def test_tool_executor_skips_disabled_tool_without_invoking_it():
    tool_policy_repository.upsert_policy("SearchLog", enabled=False)
    executor = ToolExecutor(policy_store=ToolPolicyRepositoryAdapter(tool_policy_repository))

    result = await executor.execute(
        AsyncTool(),
        {"query": "error"},
        principal=Principal(role="admin", subject="pytest"),
    )

    assert result.status == "disabled"
    assert result.output is None
    assert result.governance_payload()["decision"] == "denied"
    assert result.governance_payload()["reason"] == "Tool is disabled by policy"


@pytest.mark.asyncio
async def test_tool_executor_returns_approval_required_without_invoking_tool():
    tool_policy_repository.upsert_policy("SearchLog", approval_required=True)
    executor = ToolExecutor(policy_store=ToolPolicyRepositoryAdapter(tool_policy_repository))

    result = await executor.execute(
        AsyncTool(),
        {"query": "error"},
        principal=Principal(role="admin", subject="pytest"),
    )

    assert result.status == "approval_required"
    assert result.output is None
    assert result.governance_payload()["decision"] == "approval_required"
    assert (
        result.governance_payload()["reason"] == "Tool requires explicit approval before execution"
    )


@pytest.mark.asyncio
async def test_tool_executor_normalizes_success_and_failure():
    executor = ToolExecutor(policy_store=ToolPolicyRepositoryAdapter(tool_policy_repository))

    success = await executor.execute(
        AsyncTool(),
        {"query": "error"},
        principal=Principal(role="admin", subject="pytest"),
    )

    class FailingTool:
        name = "GetMetrics"
        description = "Get metrics"

        async def ainvoke(self, args):
            raise RuntimeError("boom")

    failure = await executor.execute(
        FailingTool(),
        {},
        principal=SimpleNamespace(role="admin", subject="pytest"),
    )

    assert success.status == "success"
    assert success.output == {"ok": True, "args": {"query": "error"}}
    assert success.governance_payload()["decision"] == "executed"
    assert failure.status == "error"
    assert "boom" in str(failure.error)
    assert failure.governance_payload()["reason"] == "Tool execution allowed by policy but failed"


@pytest.mark.asyncio
async def test_tool_executor_denies_invalid_tool_arguments_before_invocation():
    class SchemaTool:
        name = "SearchLog"
        description = "Search logs"
        args_schema = {
            "type": "object",
            "required": ["query"],
            "properties": {"query": {"type": "string"}},
        }

        async def ainvoke(self, args):
            raise AssertionError("tool should not be invoked with invalid input")

    executor = ToolExecutor(policy_store=ToolPolicyRepositoryAdapter(tool_policy_repository))

    result = await executor.execute(
        SchemaTool(),
        {"query": 123},
        principal=Principal(role="admin", subject="pytest"),
    )

    assert result.status == "invalid_input"
    assert result.governance_payload()["decision"] == "denied"
    assert result.governance_payload()["reason"] == "Tool arguments failed schema validation"
    assert result.error == "Argument query must be string"


@pytest.mark.asyncio
async def test_tool_schema_destructive_side_effect_requires_approval_by_default():
    executor = ToolExecutor(policy_store=MemoryPolicyStore())
    tool = ToolSchema(
        name="RestartService",
        description="Restart a service",
        input_schema={
            "type": "object",
            "required": ["service"],
            "properties": {"service": {"type": "string"}},
        },
        side_effect="destructive",
        raw_tool=AsyncTool(),
    )

    result = await executor.execute(
        tool,
        {"service": "api"},
        principal=Principal(role="admin", subject="pytest"),
    )

    assert result.status == "approval_required"
    assert result.policy is not None
    assert result.policy["side_effect"] == "destructive"
    assert result.policy["approval_required"] is True


@pytest.mark.asyncio
async def test_tool_schema_change_side_effect_requires_approval_by_default():
    executor = ToolExecutor(policy_store=MemoryPolicyStore())
    tool = ToolSchema(
        name="ScaleDeployment",
        description="Scale a deployment",
        input_schema={
            "type": "object",
            "required": ["replicas"],
            "properties": {"replicas": {"type": "integer"}},
        },
        side_effect="change",
        raw_tool=AsyncTool(),
    )

    result = await executor.execute(
        tool,
        {"replicas": 3},
        principal=Principal(role="admin", subject="pytest"),
    )

    assert result.status == "approval_required"
    assert result.policy is not None
    assert result.policy["side_effect"] == "change"
    assert result.policy["approval_required"] is True


@pytest.mark.asyncio
async def test_tool_executor_rejects_invalid_output_schema_result():
    class InvalidOutputTool:
        name = "SearchLog"
        description = "Search logs"

        async def ainvoke(self, args):
            return {"summary": 404}

    tool = ToolSchema(
        name="SearchLog",
        description="Search logs",
        input_schema={
            "type": "object",
            "required": ["query"],
            "properties": {"query": {"type": "string"}},
        },
        output_schema={
            "type": "object",
            "required": ["summary"],
            "properties": {"summary": {"type": "string"}},
        },
        fallback_strategy="handoff",
        raw_tool=InvalidOutputTool(),
    )
    executor = ToolExecutor(policy_store=MemoryPolicyStore())

    result = await executor.execute(
        tool,
        {"query": "error"},
        principal=Principal(role="admin", subject="pytest"),
    )

    assert result.status == "invalid_output"
    assert result.error == "Argument summary must be string"
    assert result.policy is not None
    assert result.policy["fallback_strategy"] == "handoff"
    assert result.governance_payload()["reason"] == "Tool output failed schema validation"


@pytest.mark.asyncio
async def test_tool_executor_retries_standard_schema_tool_before_success():
    class FlakyTool:
        def __init__(self):
            self.calls = 0

        async def ainvoke(self, args):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("temporary failure")
            return {"ok": True}

    raw_tool = FlakyTool()
    tool = ToolSchema(
        name="SearchLog",
        description="Search logs",
        input_schema={
            "type": "object",
            "required": ["query"],
            "properties": {"query": {"type": "string"}},
        },
        retry_count=1,
        timeout_seconds=2,
        raw_tool=raw_tool,
    )
    executor = ToolExecutor(policy_store=MemoryPolicyStore())

    result = await executor.execute(
        tool,
        {"query": "error"},
        principal=Principal(role="admin", subject="pytest"),
    )

    assert result.status == "success"
    assert result.output == {"ok": True}
    assert raw_tool.calls == 2
