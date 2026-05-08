"""Contract checks between Agent runtime ports and persistence adapters."""

import inspect

from app.agent_runtime.ports import AgentRunStore, SceneStore, ToolPolicyStore
from app.platform.persistence.repositories.native_agent import (
    AgentRunRepository,
    SceneRepository,
    ToolPolicyRepository,
)
from app.platform.persistence.schema import REQUIRED_TABLES


def test_native_agent_repositories_satisfy_runtime_ports():
    assert isinstance(SceneRepository(), SceneStore)
    assert isinstance(AgentRunRepository(), AgentRunStore)
    assert isinstance(ToolPolicyRepository(), ToolPolicyStore)


def test_native_agent_repositories_explicitly_implement_runtime_ports():
    assert SceneStore in SceneRepository.__mro__
    assert AgentRunStore in AgentRunRepository.__mro__
    assert ToolPolicyStore in ToolPolicyRepository.__mro__


def test_runtime_port_method_signatures_are_visible_on_adapters():
    for method_name in ("create_run", "update_run", "append_event"):
        port_signature = inspect.signature(getattr(AgentRunStore, method_name))
        adapter_signature = inspect.signature(getattr(AgentRunRepository, method_name))
        assert list(adapter_signature.parameters)[: len(port_signature.parameters)] == list(
            port_signature.parameters
        )


def test_required_tables_are_discovered_from_metadata():
    assert "agent_runs" in REQUIRED_TABLES
    assert "agent_events" in REQUIRED_TABLES
    assert "tool_policies" in REQUIRED_TABLES
