"""Composition-root checks for Native Agent dependency injection."""

from app.api.providers import get_agent_runtime
from app.platform.persistence import (
    agent_run_repository,
    scene_repository,
    tool_policy_repository,
)


def test_agent_runtime_is_composed_with_explicit_stores():
    get_agent_runtime.cache_clear()
    runtime = get_agent_runtime()

    assert runtime._scene_store is scene_repository
    assert runtime._run_store is agent_run_repository
    assert runtime._policy_store is tool_policy_repository

    get_agent_runtime.cache_clear()
