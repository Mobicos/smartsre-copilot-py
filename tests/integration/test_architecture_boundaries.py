from __future__ import annotations

from pathlib import Path


def test_native_agent_runtime_has_dedicated_platform_package():
    from app.agent_runtime import AgentRuntime, ToolCatalog, ToolExecutor
    from app.agent_runtime.runtime import AgentRuntime as RuntimeFromModule
    from app.agent_runtime.tool_catalog import ToolCatalog as CatalogFromModule
    from app.agent_runtime.tool_executor import ToolExecutor as ExecutorFromModule

    assert AgentRuntime is RuntimeFromModule
    assert ToolCatalog is CatalogFromModule
    assert ToolExecutor is ExecutorFromModule


def test_legacy_agent_packages_are_not_kept_as_source_boundaries():
    assert not Path("app/agent").exists()
    assert not Path("app/legacy").exists()
    assert not Path("app/persistence").exists()
    assert not Path("app/tools").exists()


def test_tooling_infrastructure_owns_tool_registry_and_mcp_client():
    from app.infrastructure.tools import ToolRegistry, mcp_client, tool_registry
    from app.infrastructure.tools.registry import ToolRegistry as RegistryFromModule

    assert ToolRegistry is RegistryFromModule
    assert tool_registry.__class__ is ToolRegistry
    assert mcp_client.__name__ == "app.infrastructure.tools.mcp_client"


def test_native_agent_schemas_live_in_domain_package():
    from app.domains.native_agent import AgentRunCreateRequest, WorkspaceCreateRequest
    from app.domains.native_agent.schemas import (
        AgentRunCreateRequest as RunRequestFromModule,
        WorkspaceCreateRequest as WorkspaceRequestFromModule,
    )

    assert AgentRunCreateRequest is RunRequestFromModule
    assert WorkspaceCreateRequest is WorkspaceRequestFromModule


def test_chat_and_aiops_schemas_live_in_domain_packages():
    from app.domains.aiops import AIOpsRequest
    from app.domains.aiops.schemas import AIOpsRequest as AIOpsRequestFromModule
    from app.domains.chat import ApiResponse, ChatRequest, ClearRequest, SessionInfoResponse
    from app.domains.chat.schemas import (
        ApiResponse as ApiResponseFromModule,
        ChatRequest as ChatRequestFromModule,
        ClearRequest as ClearRequestFromModule,
        SessionInfoResponse as SessionInfoResponseFromModule,
    )

    assert ChatRequest is ChatRequestFromModule
    assert ClearRequest is ClearRequestFromModule
    assert ApiResponse is ApiResponseFromModule
    assert SessionInfoResponse is SessionInfoResponseFromModule
    assert AIOpsRequest is AIOpsRequestFromModule


def test_chat_rag_runtime_lives_under_chat_application_package():
    from app.application.chat import RagAgentService
    from app.application.chat.rag_agent_service import RagAgentService as RagAgentServiceFromModule

    assert RagAgentService is RagAgentServiceFromModule


def test_knowledge_infrastructure_lives_under_infrastructure_package():
    from app.infrastructure.knowledge import (
        DashScopeEmbeddings,
        DocumentSplitterService,
        VectorIndexService,
        VectorSearchService,
        VectorStoreManager,
    )
    from app.infrastructure.knowledge.vector_embedding_service import (
        DashScopeEmbeddings as EmbeddingsFromModule,
    )

    assert DashScopeEmbeddings is EmbeddingsFromModule
    assert DocumentSplitterService.__name__ == "DocumentSplitterService"
    assert VectorIndexService.__name__ == "VectorIndexService"
    assert VectorSearchService.__name__ == "VectorSearchService"
    assert VectorStoreManager.__name__ == "VectorStoreManager"


def test_indexing_task_orchestration_has_explicit_application_and_infrastructure_layers():
    from app.api.providers import get_indexing_task_service
    from app.application.indexing import IndexingTaskService
    from app.infrastructure.tasks import LocalTaskDispatcher, task_dispatcher

    assert get_indexing_task_service().__class__ is IndexingTaskService
    assert task_dispatcher.__class__ is LocalTaskDispatcher


def test_indexing_task_application_service_does_not_import_global_container():
    source = Path("app/application/indexing/service.py").read_text(encoding="utf-8")

    assert "app.core.container" not in source
    assert "service_container" not in source
    assert "app.api.providers" not in source


def test_native_agent_repositories_live_in_platform_persistence_package():
    from app.platform.persistence.repositories.native_agent import (
        AgentRunRepository,
        WorkspaceRepository,
        agent_run_repository,
        workspace_repository,
    )

    assert WorkspaceRepository.__name__ == "WorkspaceRepository"
    assert AgentRunRepository.__name__ == "AgentRunRepository"
    assert workspace_repository.__class__ is WorkspaceRepository
    assert agent_run_repository.__class__ is AgentRunRepository


def test_conversation_repositories_live_in_platform_persistence_package():
    from app.platform.persistence.repositories.conversation import (
        ChatToolEventRepository,
        ConversationRepository,
        chat_tool_event_repository,
        conversation_repository,
    )

    assert ConversationRepository.__name__ == "ConversationRepository"
    assert ChatToolEventRepository.__name__ == "ChatToolEventRepository"
    assert conversation_repository.__class__ is ConversationRepository
    assert chat_tool_event_repository.__class__ is ChatToolEventRepository


def test_aiops_repositories_live_in_platform_persistence_package():
    from app.platform.persistence.repositories.aiops import (
        AIOpsRunRepository,
        aiops_run_repository,
    )

    assert AIOpsRunRepository.__name__ == "AIOpsRunRepository"
    assert aiops_run_repository.__class__ is AIOpsRunRepository


def test_indexing_repositories_live_in_platform_persistence_package():
    from app.platform.persistence.repositories.indexing import (
        IndexingTaskRepository,
        indexing_task_repository,
    )

    assert IndexingTaskRepository.__name__ == "IndexingTaskRepository"
    assert indexing_task_repository.__class__ is IndexingTaskRepository


def test_audit_repositories_live_in_platform_persistence_package():
    from app.platform.persistence.repositories.audit import (
        AuditLogRepository,
        audit_log_repository,
    )

    assert AuditLogRepository.__name__ == "AuditLogRepository"
    assert audit_log_repository.__class__ is AuditLogRepository


def test_api_routes_live_in_routes_package():
    from app.api.routes import aiops, chat, file, health, native_agent

    assert health.router is not None
    assert chat.router is not None
    assert file.router is not None
    assert aiops.router is not None
    assert native_agent.router is not None


def test_native_agent_has_application_service_boundary():
    from app.api.providers import get_native_agent_application_service
    from app.application.native_agent_application_service import NativeAgentApplicationService

    assert get_native_agent_application_service().__class__ is NativeAgentApplicationService
