"""应用依赖容器。

集中管理核心基础设施依赖，避免在模块导入阶段初始化外部资源。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger

from app.config import config
from app.infrastructure import checkpoint_saver
from app.infrastructure.knowledge import (
    DashScopeEmbeddings,
    DocumentSplitterService,
    VectorIndexService,
    VectorSearchService,
    VectorStoreManager,
)
from app.persistence import (
    agent_feedback_repository,
    agent_run_repository,
    aiops_run_repository,
    chat_tool_event_repository,
    conversation_repository,
    scene_repository,
    tool_policy_repository,
    workspace_repository,
)

if TYPE_CHECKING:
    from app.agent_runtime import AgentRuntime, ToolCatalog, ToolExecutor
    from app.application.aiops_application_service import AIOpsApplicationService
    from app.application.chat_application_service import ChatApplicationService
    from app.application.native_agent_application_service import NativeAgentApplicationService
    from app.services.rag_agent_service import RagAgentService


@dataclass
class ServiceHealth:
    """核心依赖健康状态。"""

    status: str
    message: str


class AppContainer:
    """集中管理应用级依赖。"""

    def __init__(self) -> None:
        self._embedding_service: DashScopeEmbeddings | None = None
        self._vector_store_manager: VectorStoreManager | None = None
        self._vector_search_service: VectorSearchService | None = None
        self._document_splitter_service: DocumentSplitterService | None = None
        self._vector_index_service: VectorIndexService | None = None
        self._rag_agent_service: RagAgentService | None = None
        self._tool_catalog: ToolCatalog | None = None
        self._tool_executor: ToolExecutor | None = None
        self._agent_runtime: AgentRuntime | None = None
        self._chat_application_service: ChatApplicationService | None = None
        self._aiops_application_service: AIOpsApplicationService | None = None
        self._native_agent_application_service: NativeAgentApplicationService | None = None

    def initialize_required_services(self) -> None:
        """初始化启动所需的核心依赖。"""
        _ = self.get_vector_store_manager()

    def get_embedding_service(self) -> DashScopeEmbeddings:
        """获取嵌入服务。"""
        if self._embedding_service is None:
            logger.info("初始化 DashScope Embeddings 服务...")
            self._embedding_service = DashScopeEmbeddings(
                api_key=config.dashscope_api_key,
                model=config.dashscope_embedding_model,
                dimensions=1024,
            )
        return self._embedding_service

    def get_vector_store_manager(self) -> VectorStoreManager:
        """获取向量存储管理器。"""
        if self._vector_store_manager is None:
            logger.info("初始化 VectorStore 管理器...")
            self._vector_store_manager = VectorStoreManager(
                embedding_service=self.get_embedding_service(),
            )
        return self._vector_store_manager

    def get_vector_search_service(self) -> VectorSearchService:
        """获取向量检索服务。"""
        if self._vector_search_service is None:
            self._vector_search_service = VectorSearchService(
                embedding_service=self.get_embedding_service(),
            )
        return self._vector_search_service

    def get_document_splitter_service(self) -> DocumentSplitterService:
        """获取文档分割服务。"""
        if self._document_splitter_service is None:
            self._document_splitter_service = DocumentSplitterService()
        return self._document_splitter_service

    def get_vector_index_service(self) -> VectorIndexService:
        """获取向量索引服务。"""
        if self._vector_index_service is None:
            self._vector_index_service = VectorIndexService(
                document_splitter_service=self.get_document_splitter_service(),
                vector_store_manager=self.get_vector_store_manager(),
            )
        return self._vector_index_service

    def get_rag_agent_service(self) -> RagAgentService:
        """获取 RAG Agent 运行时服务。"""
        if self._rag_agent_service is None:
            logger.info("初始化 RAG Agent 服务...")
            from app.services.rag_agent_service import RagAgentService

            self._rag_agent_service = RagAgentService(
                streaming=True,
                checkpointer=checkpoint_saver,
            )
        return self._rag_agent_service

    def get_tool_catalog(self) -> ToolCatalog:
        """获取原生 Agent 工具目录。"""
        if self._tool_catalog is None:
            from app.agent_runtime import ToolCatalog

            self._tool_catalog = ToolCatalog()
        return self._tool_catalog

    def get_tool_executor(self) -> ToolExecutor:
        """获取原生 Agent 工具执行器。"""
        if self._tool_executor is None:
            from app.agent_runtime import ToolExecutor, ToolPolicyRepositoryAdapter

            self._tool_executor = ToolExecutor(
                policy_store=ToolPolicyRepositoryAdapter(tool_policy_repository)
            )
        return self._tool_executor

    def get_agent_runtime(self) -> AgentRuntime:
        """获取原生 SRE Agent Runtime。"""
        if self._agent_runtime is None:
            from app.agent_runtime import AgentRuntime

            self._agent_runtime = AgentRuntime(
                tool_catalog=self.get_tool_catalog(),
                tool_executor=self.get_tool_executor(),
            )
        return self._agent_runtime

    def get_chat_application_service(self) -> ChatApplicationService:
        """获取聊天应用服务。"""
        if self._chat_application_service is None:
            from app.application.chat_application_service import ChatApplicationService

            self._chat_application_service = ChatApplicationService(
                rag_agent_service=self.get_rag_agent_service(),
                conversation_repository=conversation_repository,
                chat_tool_event_repository=chat_tool_event_repository,
            )
        return self._chat_application_service

    def get_aiops_application_service(self) -> AIOpsApplicationService:
        """获取 AIOps 应用服务。"""
        if self._aiops_application_service is None:
            from app.application.aiops_application_service import AIOpsApplicationService

            self._aiops_application_service = AIOpsApplicationService(
                agent_runtime=self.get_agent_runtime(),
                aiops_run_repository=aiops_run_repository,
                conversation_repository=conversation_repository,
                workspace_repository=workspace_repository,
                scene_repository=scene_repository,
            )
        return self._aiops_application_service

    def get_native_agent_application_service(self) -> NativeAgentApplicationService:
        """获取原生 Agent 应用服务。"""
        if self._native_agent_application_service is None:
            from app.application.native_agent_application_service import (
                NativeAgentApplicationService,
            )

            self._native_agent_application_service = NativeAgentApplicationService(
                agent_runtime=self.get_agent_runtime(),
                tool_catalog=self.get_tool_catalog(),
                workspace_repository=workspace_repository,
                scene_repository=scene_repository,
                tool_policy_repository=tool_policy_repository,
                agent_run_repository=agent_run_repository,
                agent_feedback_repository=agent_feedback_repository,
            )
        return self._native_agent_application_service

    def get_service_health(self) -> dict[str, ServiceHealth]:
        """返回核心依赖的健康摘要。"""
        embedding_ready = self._embedding_service is not None
        vector_store_ready = (
            self._vector_store_manager is not None and self._vector_store_manager.is_initialized
        )
        rag_ready = self._rag_agent_service is not None
        aiops_ready = self._aiops_application_service is not None
        checkpoint_ready = checkpoint_saver is not None

        return {
            "embedding": ServiceHealth(
                status="ready" if embedding_ready else "not_initialized",
                message="Embedding 服务已初始化" if embedding_ready else "Embedding 服务尚未初始化",
            ),
            "vector_store": ServiceHealth(
                status="ready" if vector_store_ready else "not_initialized",
                message="VectorStore 已初始化" if vector_store_ready else "VectorStore 尚未初始化",
            ),
            "rag_agent": ServiceHealth(
                status="ready" if rag_ready else "not_initialized",
                message="RAG Agent 已初始化" if rag_ready else "RAG Agent 尚未初始化",
            ),
            "aiops": ServiceHealth(
                status="ready" if aiops_ready else "not_initialized",
                message="AIOps 应用服务已初始化" if aiops_ready else "AIOps 应用服务尚未初始化",
            ),
            "checkpoint": ServiceHealth(
                status="ready" if checkpoint_ready else "not_initialized",
                message="Checkpoint 存储已初始化"
                if checkpoint_ready
                else "Checkpoint 存储尚未初始化",
            ),
        }

    def reset(self) -> None:
        """重置容器中的运行时依赖引用。"""
        self._agent_runtime = None
        self._tool_executor = None
        self._tool_catalog = None
        self._rag_agent_service = None
        self._aiops_application_service = None
        self._chat_application_service = None
        self._native_agent_application_service = None
        self._vector_index_service = None
        self._document_splitter_service = None
        self._vector_search_service = None
        self._vector_store_manager = None
        self._embedding_service = None

    async def shutdown(self) -> None:
        """按生命周期关闭运行时依赖。"""
        if self._rag_agent_service is not None:
            await self._rag_agent_service.cleanup()
        self.reset()


service_container = AppContainer()
