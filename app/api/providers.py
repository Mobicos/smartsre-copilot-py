"""FastAPI composition root and dependency providers."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property, lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from app.core.config import AppSettings
from app.infrastructure import checkpoint_saver
from app.infrastructure.knowledge import (
    DashScopeEmbeddings,
    DocumentSplitterService,
    VectorIndexService,
    VectorSearchService,
    VectorStoreManager,
)
from app.platform.persistence import (
    agent_feedback_repository,
    agent_run_repository,
    aiops_run_repository,
    chat_tool_event_repository,
    conversation_repository,
    indexing_task_repository,
    scene_repository,
    tool_policy_repository,
    workspace_repository,
)

if TYPE_CHECKING:
    from app.agent_runtime import AgentRuntime, ToolCatalog, ToolExecutor
    from app.application.agent_resume_service import AgentResumeService
    from app.application.aiops_application_service import AIOpsApplicationService
    from app.application.api_contract_service import ApiContractService
    from app.application.chat import RagAgentService
    from app.application.chat_application_service import ChatApplicationService
    from app.application.indexing import IndexingTaskService
    from app.application.native_agent_application_service import NativeAgentApplicationService
    from app.application.scenario_regression_service import ScenarioRegressionService
    from app.infrastructure.object_storage import ObjectStoragePort


@dataclass
class ServiceHealth:
    """Core dependency health status."""

    status: str
    message: str
    detail: dict[str, Any] | None = None


class RuntimeContainer:
    """Native Agent dependency graph."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        scene_store: Any = scene_repository,
        run_store: Any = agent_run_repository,
        policy_store: Any = tool_policy_repository,
    ) -> None:
        self._settings = settings
        self.scene_store = scene_store
        self.run_store = run_store
        self.policy_store = policy_store

    @cached_property
    def tool_catalog(self) -> ToolCatalog:
        from app.agent_runtime import ToolCatalog

        return ToolCatalog()

    @cached_property
    def tool_executor(self) -> ToolExecutor:
        from app.agent_runtime import ToolExecutor, ToolPolicyRepositoryAdapter

        return ToolExecutor(policy_store=ToolPolicyRepositoryAdapter(self.policy_store))

    @cached_property
    def decision_runtime(self) -> Any:
        from app.agent_runtime import (
            AgentDecisionRuntime,
            DeterministicDecisionProvider,
            LangChainQwenDecisionInvoker,
            QwenDecisionProvider,
        )

        provider_name = self._settings.agent_decision_provider.strip().lower()
        provider: Any
        if provider_name == "qwen":
            from app.core.llm_factory import llm_factory

            provider = QwenDecisionProvider(
                LangChainQwenDecisionInvoker(
                    llm_factory.create_chat_model(
                        model=self._settings.dashscope_model,
                        temperature=0,
                        streaming=False,
                    )
                )
            )
        else:
            provider = DeterministicDecisionProvider()

        return AgentDecisionRuntime(provider=provider, checkpoint_saver=checkpoint_saver)

    @cached_property
    def agent_runtime(self) -> AgentRuntime:
        from app.agent_runtime import AgentRuntime

        return AgentRuntime(
            settings=self._settings,
            tool_catalog=self.tool_catalog,
            tool_executor=self.tool_executor,
            scene_store=self.scene_store,
            run_store=self.run_store,
            policy_store=self.policy_store,
            decision_runtime=self.decision_runtime,
        )

    def reset_for_testing(self) -> None:
        """Clear cached runtime services without mutating repository singletons."""
        for name in ("tool_catalog", "tool_executor", "decision_runtime", "agent_runtime"):
            self.__dict__.pop(name, None)


class AppContainer:
    """Application composition root for API, runtime, and infrastructure services."""

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
        self.runtime = RuntimeContainer(settings=settings)

    @cached_property
    def embedding_service(self) -> DashScopeEmbeddings:
        logger.info("Initializing DashScope Embeddings service...")
        return DashScopeEmbeddings(
            api_key=self._settings.dashscope_api_key,
            model=self._settings.dashscope_embedding_model,
            dimensions=1024,
        )

    @cached_property
    def vector_store_manager(self) -> VectorStoreManager:
        logger.info("Initializing VectorStore manager...")
        return VectorStoreManager(embedding_service=self.embedding_service)

    @cached_property
    def vector_search_service(self) -> VectorSearchService:
        return VectorSearchService(embedding_service=self.embedding_service)

    @cached_property
    def document_splitter_service(self) -> DocumentSplitterService:
        return DocumentSplitterService()

    @cached_property
    def object_storage(self) -> ObjectStoragePort:
        from app.infrastructure.object_storage import (
            LocalObjectStorageAdapter,
            MinioObjectStorageAdapter,
        )

        backend = self._settings.object_storage_backend.strip().lower()
        if backend == "minio":
            return MinioObjectStorageAdapter(
                endpoint=self._settings.minio_endpoint,
                access_key=self._settings.minio_access_key,
                secret_key=self._settings.minio_secret_key,
                bucket=self._settings.minio_bucket,
                secure=self._settings.minio_secure,
                local_cache_root=Path(self._settings.object_storage_local_cache_path),
            )
        return LocalObjectStorageAdapter(root=Path(self._settings.object_storage_local_path))

    @cached_property
    def vector_index_service(self) -> VectorIndexService:
        return VectorIndexService(
            document_splitter_service=self.document_splitter_service,
            vector_store_manager=self.vector_store_manager,
            object_storage=self.object_storage,
        )

    @cached_property
    def rag_agent_service(self) -> RagAgentService:
        logger.info("Initializing RAG Agent service...")
        from app.application.chat import RagAgentService

        return RagAgentService(
            settings=self._settings,
            streaming=True,
            checkpointer=checkpoint_saver,
        )

    @cached_property
    def indexing_task_service(self) -> IndexingTaskService:
        from app.application.indexing import IndexingTaskService

        return IndexingTaskService(
            repository=indexing_task_repository,
            vector_indexer_provider=lambda: self.vector_index_service,
            max_retries_provider=lambda: self._settings.indexing_task_max_retries,
            object_storage=self.object_storage,
        )

    @cached_property
    def api_contract_service(self) -> ApiContractService:
        from app.application.api_contract_service import ApiContractService

        return ApiContractService()

    @cached_property
    def chat_application_service(self) -> ChatApplicationService:
        from app.application.chat_application_service import ChatApplicationService

        return ChatApplicationService(
            rag_agent_service=self.rag_agent_service,
            conversation_repository=conversation_repository,
            chat_tool_event_repository=chat_tool_event_repository,
        )

    @cached_property
    def aiops_application_service(self) -> AIOpsApplicationService:
        from app.application.aiops_application_service import AIOpsApplicationService

        return AIOpsApplicationService(
            agent_runtime=self.runtime.agent_runtime,
            aiops_run_repository=aiops_run_repository,
            conversation_repository=conversation_repository,
            workspace_repository=workspace_repository,
            scene_repository=scene_repository,
        )

    @cached_property
    def agent_resume_service(self) -> AgentResumeService:
        from app.application.agent_resume_service import AgentResumeService

        return AgentResumeService(
            agent_run_repository=agent_run_repository,
            tool_catalog=self.runtime.tool_catalog,
            tool_executor=self.runtime.tool_executor,
        )

    @cached_property
    def scenario_regression_service(self) -> ScenarioRegressionService:
        from app.application.scenario_regression_service import ScenarioRegressionService

        return ScenarioRegressionService(agent_run_repository=agent_run_repository)

    @cached_property
    def native_agent_application_service(self) -> NativeAgentApplicationService:
        from app.application.native_agent_application_service import (
            NativeAgentApplicationService,
        )

        return NativeAgentApplicationService(
            agent_runtime=self.runtime.agent_runtime,
            tool_catalog=self.runtime.tool_catalog,
            workspace_repository=workspace_repository,
            scene_repository=scene_repository,
            tool_policy_repository=tool_policy_repository,
            agent_run_repository=agent_run_repository,
            agent_feedback_repository=agent_feedback_repository,
        )

    def has(self, dependency_name: str) -> bool:
        """Return whether a cached dependency has been initialized."""
        return dependency_name in self.__dict__

    async def shutdown(self) -> None:
        """Release resources owned by cached services."""
        if self.has("rag_agent_service"):
            await self.rag_agent_service.cleanup()

        if self._settings.vector_store_backend.strip().lower() == "milvus":
            from app.core.milvus_client import milvus_manager

            milvus_manager.close()

        self.reset_for_testing()

    def reset_for_testing(self) -> None:
        """Clear cached services and runtime state."""
        self.runtime.reset_for_testing()
        for name in (
            "embedding_service",
            "vector_store_manager",
            "vector_search_service",
            "document_splitter_service",
            "object_storage",
            "vector_index_service",
            "rag_agent_service",
            "indexing_task_service",
            "api_contract_service",
            "chat_application_service",
            "aiops_application_service",
            "agent_resume_service",
            "scenario_regression_service",
            "native_agent_application_service",
        ):
            self.__dict__.pop(name, None)


@lru_cache(maxsize=1)
def get_app_container(settings: AppSettings | None = None) -> AppContainer:
    """Return the process-level application container.

    Args:
        settings: AppSettings instance. If None, loads from environment via
            `AppSettings.from_env()`. Cached per unique settings instance.
    """
    if settings is None:
        settings = AppSettings.from_env()
    return AppContainer(settings=settings)


def reset_container_for_testing() -> None:
    """Reset the process-level container for test isolation."""
    if get_app_container.cache_info().currsize:
        get_app_container().reset_for_testing()
    get_app_container.cache_clear()


def get_embedding_service() -> DashScopeEmbeddings:
    return get_app_container().embedding_service


def get_vector_store_manager() -> VectorStoreManager:
    return get_app_container().vector_store_manager


def get_vector_search_service() -> VectorSearchService:
    return get_app_container().vector_search_service


def get_document_splitter_service() -> DocumentSplitterService:
    return get_app_container().document_splitter_service


def get_object_storage() -> ObjectStoragePort:
    return get_app_container().object_storage


def get_vector_index_service() -> VectorIndexService:
    return get_app_container().vector_index_service


def get_rag_agent_service() -> RagAgentService:
    return get_app_container().rag_agent_service


def get_indexing_task_service() -> IndexingTaskService:
    return get_app_container().indexing_task_service


def get_api_contract_service() -> ApiContractService:
    return get_app_container().api_contract_service


def get_tool_catalog() -> ToolCatalog:
    return get_app_container().runtime.tool_catalog


def get_tool_executor() -> ToolExecutor:
    return get_app_container().runtime.tool_executor


def get_agent_runtime() -> AgentRuntime:
    return get_app_container().runtime.agent_runtime


def get_chat_application_service() -> ChatApplicationService:
    return get_app_container().chat_application_service


def get_aiops_application_service() -> AIOpsApplicationService:
    return get_app_container().aiops_application_service


def get_agent_resume_service() -> AgentResumeService:
    return get_app_container().agent_resume_service


def get_scenario_regression_service() -> ScenarioRegressionService:
    return get_app_container().scenario_regression_service


def get_native_agent_application_service() -> NativeAgentApplicationService:
    return get_app_container().native_agent_application_service


def initialize_services() -> None:
    """Initialize services required at application startup."""
    settings = get_app_container()._settings
    if not settings.dashscope_api_key.strip():
        logger.warning(
            "Skipping VectorStore startup initialization because DASHSCOPE_API_KEY is not configured"
        )
        return
    _ = get_app_container().vector_store_manager


async def shutdown_services() -> None:
    """Gracefully shut down runtime services and clear cached dependencies."""
    await get_app_container().shutdown()
    get_app_container.cache_clear()


def get_service_health() -> dict[str, ServiceHealth]:
    """Return a health summary of core dependencies."""
    container = get_app_container()
    settings = container._settings
    embedding_ready = container.has("embedding_service")
    vector_store_ready = (
        container.has("vector_store_manager") and container.vector_store_manager.is_initialized
    )
    object_storage_ready = container.has("object_storage")
    rag_ready = container.has("rag_agent_service")
    aiops_ready = container.has("aiops_application_service")
    checkpoint_ready = checkpoint_saver is not None
    decision_provider = settings.agent_decision_provider.strip().lower()
    dashscope_ready = bool(settings.dashscope_api_key.strip())
    decision_runtime_status = "ready"
    decision_runtime_message = "确定性决策运行时已配置"
    if decision_provider == "qwen":
        decision_runtime_status = "configured" if dashscope_ready else "degraded"
        decision_runtime_message = (
            "Qwen 决策运行时已配置"
            if dashscope_ready
            else "Qwen 决策运行时已选择但 DashScope API 密钥缺失"
        )

    return {
        "embedding": ServiceHealth(
            status="ready" if embedding_ready else "not_initialized",
            message=("嵌入服务已初始化" if embedding_ready else "嵌入服务尚未初始化"),
        ),
        "vector_store": ServiceHealth(
            status="ready" if vector_store_ready else "not_initialized",
            message=("向量存储已初始化" if vector_store_ready else "向量存储尚未初始化"),
        ),
        "object_storage": ServiceHealth(
            status="ready" if object_storage_ready else "configured",
            message=f"对象存储后端：{settings.object_storage_backend}",
        ),
        "decision_runtime": ServiceHealth(
            status=decision_runtime_status,
            message=decision_runtime_message,
            detail={
                "provider": decision_provider,
                "dashscope_configured": dashscope_ready,
            },
        ),
        "rag_agent": ServiceHealth(
            status="ready" if rag_ready else "not_initialized",
            message="RAG Agent 已初始化" if rag_ready else "RAG Agent 尚未初始化",
        ),
        "aiops": ServiceHealth(
            status="ready" if aiops_ready else "not_initialized",
            message=("AIOps 应用服务已初始化" if aiops_ready else "AIOps 应用服务尚未初始化"),
        ),
        "checkpoint": ServiceHealth(
            status="ready" if checkpoint_ready else "not_initialized",
            message=("检查点存储已初始化" if checkpoint_ready else "检查点存储尚未初始化"),
        ),
    }
