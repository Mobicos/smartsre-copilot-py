"""Composition-root checks for Native Agent dependency injection."""

from app.api.providers import RuntimeContainer, get_agent_runtime, reset_container_for_testing
from app.config import config
from app.platform.persistence import (
    agent_run_repository,
    scene_repository,
    tool_policy_repository,
)


def test_agent_runtime_is_composed_with_explicit_stores():
    reset_container_for_testing()
    runtime = get_agent_runtime()

    assert runtime._scene_store is scene_repository
    assert runtime._run_store is agent_run_repository
    assert runtime._policy_store is tool_policy_repository

    reset_container_for_testing()


def test_runtime_container_reset_rebuilds_runtime_dependency_graph():
    container = RuntimeContainer()
    first_runtime = container.agent_runtime

    container.reset_for_testing()

    assert container.agent_runtime is not first_runtime


def test_initialize_services_skips_vector_store_without_dashscope_key(monkeypatch):
    from app.api import providers

    class FakeContainer:
        @property
        def vector_store_manager(self):
            raise AssertionError("vector store should not initialize without DashScope key")

    original_key = config.dashscope_api_key
    config.dashscope_api_key = ""
    monkeypatch.setattr(providers, "get_app_container", lambda: FakeContainer())
    try:
        providers.initialize_services()
    finally:
        config.dashscope_api_key = original_key
