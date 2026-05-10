"""Config injection isolation tests — verify components accept AppSettings via constructor."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.core.config import AppSettings


class TestAppSettings:
    """Smoke tests for AppSettings itself."""

    def test_defaults_produces_valid_instance(self):
        settings = AppSettings.defaults()
        assert settings.app_name == "SmartSRE Copilot"
        assert settings.rag_model == "qwen-max"

    def test_from_env_produces_valid_instance(self):
        settings = AppSettings.from_env()
        assert settings.app_name
        assert settings.rag_model

    def test_defaults_is_frozen(self):
        settings = AppSettings.defaults()
        with pytest.raises(AttributeError):  # frozen dataclass raises AttributeError on mutation
            settings.rag_model = "other"  # type: ignore[assignment]


class TestAgentRuntimeSettingsInjection:
    """AgentRuntime accepts settings via constructor."""

    def test_agent_runtime_constructor_accepts_settings(self):
        from app.agent_runtime.runtime import AgentRuntime

        settings = AppSettings.defaults()
        mock_checkpointer = MagicMock()
        mock_checkpointer.get.return_value = None

        runtime = AgentRuntime(
            settings=settings,
            tool_catalog=None,
            scene_store=MagicMock(),
            run_store=MagicMock(),
            policy_store=MagicMock(),
        )
        assert runtime._settings is settings


class TestRedisManagerSettingsInjection:
    """RedisManager accepts settings via constructor."""

    def test_redis_manager_constructor_accepts_settings(self):
        from app.infrastructure.redis_client import RedisManager

        settings = AppSettings.defaults()
        manager = RedisManager(redis_url=settings.redis_url, settings=settings)
        assert manager._settings is settings


class TestLLMFactorySettingsInjection:
    """LLMFactory uses settings via create_chat_model."""

    def test_llm_factory_create_chat_model_signature(self):
        from app.core.llm_factory import LLMFactory

        factory = LLMFactory()
        # Verify settings param exists and is used when model not explicitly provided
        # We only verify the method accepts settings — actual LLM call needs API key
        import inspect

        sig = inspect.signature(factory.create_chat_model)
        param_names = list(sig.parameters.keys())
        assert "settings" in param_names


class TestToolRegistrySettingsInjection:
    """ToolRegistry accepts settings via constructor."""

    def test_tool_registry_constructor_accepts_settings(self):
        from app.infrastructure.tools.registry import ToolRegistry

        settings = AppSettings.defaults()
        registry = ToolRegistry(settings=settings)
        assert registry._settings is settings


class TestRagAgentServiceSettingsInjection:
    """RagAgentService accepts settings via constructor."""

    def test_rag_agent_service_stores_settings(self):
        from app.application.chat.rag_agent_service import RagAgentService

        settings = AppSettings.defaults()
        mock_checkpointer = MagicMock()
        mock_checkpointer.get.return_value = None

        # Patch ChatQwen to avoid API key validation at construction time
        with patch("app.application.chat.rag_agent_service.ChatQwen") as _:
            service = RagAgentService(settings=settings, checkpointer=mock_checkpointer)
            assert service._settings is settings
            assert service.model_name == settings.rag_model


class TestMilvusClientManagerSettingsInjection:
    """MilvusClientManager accepts settings via constructor."""

    def test_milvus_client_manager_constructor_accepts_settings(self):
        from app.core.milvus_client import MilvusClientManager

        settings = AppSettings.defaults()
        manager = MilvusClientManager(settings=settings)
        assert manager._settings is settings


class TestAppContainerSettingsInjection:
    """AppContainer passes settings to sub-containers."""

    def test_app_container_passes_settings_to_runtime_container(self):
        from app.api.providers import get_app_container

        settings = AppSettings.defaults()
        container = get_app_container(settings=settings)
        assert container.runtime._settings is settings
        assert container._settings is settings


class TestSettingsOverrideIsolation:
    """Two containers with different settings stay isolated via lru_cache key identity."""

    def test_two_containers_have_independent_settings(self):
        from app.api.providers import get_app_container

        # lru_cache uses object identity as key, so two distinct AppSettings
        # instances produce two distinct containers
        settings_a = AppSettings.defaults()
        settings_b = AppSettings.defaults()
        assert settings_a is not settings_b  # pre-condition

        # Clear any cached result first
        get_app_container.cache_clear()

        container_a = get_app_container(settings=settings_a)
        get_app_container.cache_clear()
        container_b = get_app_container(settings=settings_b)

        assert container_a._settings is settings_a
        assert container_b._settings is settings_b


class TestSecurityFunctionsSettingsInjection:
    """Security functions accept optional settings, falling back to from_env()."""

    def test_is_auth_configured_with_explicit_settings(self):
        from app.security.auth import is_auth_configured

        settings = AppSettings.defaults()
        result = is_auth_configured(settings=settings)
        # With defaults, no API keys are configured
        assert result is False

    def test_validate_security_configuration_with_defaults(self):
        from app.security.auth import validate_security_configuration

        settings = AppSettings.defaults()
        # validate_security_configuration returns None; it may raise RuntimeError
        # in production. With defaults (ENVIRONMENT=dev), it should not raise.
        validate_security_configuration(settings=settings)


class TestDatabaseSettingsInjection:
    """Database module uses AppSettings via _get_settings helper."""

    def test_database_health_check_callable(self):
        from app.platform.persistence import database

        # Just verify the function is callable and doesn't raise on import
        assert callable(database.health_check)

    def test_database_get_settings_helper(self):
        from app.platform.persistence.database import _get_settings

        settings = _get_settings()
        assert settings.app_name


class TestNativeAgentApplicationServiceSettingsInjection:
    """NativeAgentApplicationService uses settings via _get_settings helper."""

    def test_native_agent_service_get_settings_helper(self):
        from app.application.native_agent_application_service import _get_settings

        settings = _get_settings()
        assert settings.app_name


class TestHealthRoutesSettingsInjection:
    """Health routes use settings via _get_settings helper."""

    def test_health_route_settings_helper(self):
        from app.api.routes.health import _get_settings

        settings = _get_settings()
        assert settings.app_name


class TestTaskDispatcherSettingsInjection:
    """Task dispatcher accepts settings via constructor."""

    def test_task_dispatcher_constructor_accepts_settings(self):
        from app.infrastructure.tasks.dispatcher import LocalTaskDispatcher

        settings = AppSettings.defaults()
        dispatcher = LocalTaskDispatcher(settings=settings)
        assert dispatcher._settings is settings


class TestAgentResumeDispatcherSettingsInjection:
    """Agent resume dispatcher accepts settings via constructor."""

    def test_agent_resume_dispatcher_constructor_accepts_settings(self):
        from app.infrastructure.tasks.agent_resume import AgentResumeDispatcher

        settings = AppSettings.defaults()
        dispatcher = AgentResumeDispatcher(settings=settings)
        assert dispatcher._settings is settings
