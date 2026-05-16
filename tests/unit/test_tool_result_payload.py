from __future__ import annotations

from types import SimpleNamespace

from app.agent_runtime.state import ToolAction, ToolPolicySnapshot


def test_tool_result_payload_includes_latency_ms_when_available():
    action = ToolAction(
        tool_name="SearchLog",
        arguments={"query": "error"},
        policy_snapshot=ToolPolicySnapshot(tool_name="SearchLog"),
    )
    result = SimpleNamespace(
        tool_name="SearchLog",
        status="success",
        arguments={"query": "error"},
        output="log evidence",
        error=None,
        latency_ms=17,
    )

    payload = action.result_event_payload(result)

    assert payload["latency_ms"] == 17
