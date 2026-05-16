from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agent_runtime.executor import AgentToolExecutor
from app.agent_runtime.runtime import AgentRuntime, RuntimeDeadline, RuntimeSafetyConfig
from app.agent_runtime.state import ToolAction, ToolPolicySnapshot
from app.agent_runtime.trace_collector import TraceCollector


class _Executor:
    async def execute(self, tool, args, *, principal):
        return SimpleNamespace(
            tool_name=tool.name,
            status="success",
            arguments=args,
            output="evidence",
            error=None,
        )


@pytest.mark.asyncio
async def test_runtime_records_tool_execution_latency_ms():
    runtime = object.__new__(AgentRuntime)
    runtime._trace_collector = TraceCollector("smartsre.tests")
    runtime._action_executor = AgentToolExecutor(tool_executor=_Executor())
    action = ToolAction(
        tool_name="SearchLog",
        arguments={"query": "error"},
        policy_snapshot=ToolPolicySnapshot(tool_name="SearchLog"),
    )

    result = await runtime.execute_tool_with_timeout(
        SimpleNamespace(name="SearchLog"),
        action,
        principal=object(),
        safety_config=RuntimeSafetyConfig(tool_timeout_seconds=30),
        deadline=RuntimeDeadline.start(30),
    )

    assert isinstance(result.latency_ms, int)
    assert result.latency_ms >= 0
