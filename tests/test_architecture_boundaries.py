from __future__ import annotations


def test_native_agent_runtime_has_dedicated_platform_package():
    from app.agent_runtime import AgentRuntime, ToolCatalog, ToolExecutor
    from app.agent_runtime.runtime import AgentRuntime as RuntimeFromModule
    from app.agent_runtime.tool_catalog import ToolCatalog as CatalogFromModule
    from app.agent_runtime.tool_executor import ToolExecutor as ExecutorFromModule

    assert AgentRuntime is RuntimeFromModule
    assert ToolCatalog is CatalogFromModule
    assert ToolExecutor is ExecutorFromModule


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
    from app.application.native_agent_application_service import NativeAgentApplicationService
    from app.core.container import service_container

    assert service_container.get_native_agent_application_service().__class__ is (
        NativeAgentApplicationService
    )
