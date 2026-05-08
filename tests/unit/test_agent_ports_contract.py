"""Contract checks between Agent runtime ports and persistence adapters."""

from app.agent_runtime.ports import AgentRunStore, SceneStore, ToolPolicyStore
from app.platform.persistence.repositories.native_agent import (
    AgentRunRepository,
    SceneRepository,
    ToolPolicyRepository,
)


def test_native_agent_repositories_satisfy_runtime_ports():
    assert isinstance(SceneRepository(), SceneStore)
    assert isinstance(AgentRunRepository(), AgentRunStore)
    assert isinstance(ToolPolicyRepository(), ToolPolicyStore)
