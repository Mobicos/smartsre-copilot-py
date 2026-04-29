from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agent_runtime import ToolExecutor, ToolPolicyRepositoryAdapter
from app.platform.persistence import tool_policy_repository
from app.security.auth import Principal


class AsyncTool:
    name = "SearchLog"
    description = "Search logs"

    async def ainvoke(self, args):
        return {"ok": True, "args": args}


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
    assert failure.status == "error"
    assert "boom" in str(failure.error)
