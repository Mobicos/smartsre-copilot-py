"""应用依赖容器。

集中管理核心基础设施依赖，避免在模块导入阶段初始化外部资源。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger

from app.config import config
from app.services.vector_embedding_service import DashScopeEmbeddings
from app.services.vector_search_service import VectorSearchService
from app.services.vector_store_manager import VectorStoreManager

if TYPE_CHECKING:
    from app.services.aiops_service import AIOpsService
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
        self._rag_agent_service: RagAgentService | None = None
        self._aiops_service: AIOpsService | None = None

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

    def get_rag_agent_service(self) -> "RagAgentService":
        """获取 RAG Agent 运行时服务。"""
        if self._rag_agent_service is None:
            logger.info("初始化 RAG Agent 服务...")
            from app.services.rag_agent_service import RagAgentService

            self._rag_agent_service = RagAgentService(streaming=True)
        return self._rag_agent_service

    def get_aiops_service(self) -> "AIOpsService":
        """获取 AIOps 工作流运行时服务。"""
        if self._aiops_service is None:
            logger.info("初始化 AIOps 服务...")
            from app.services.aiops_service import AIOpsService

            self._aiops_service = AIOpsService()
        return self._aiops_service

    def get_service_health(self) -> dict[str, ServiceHealth]:
        """返回核心依赖的健康摘要。"""
        embedding_ready = self._embedding_service is not None
        vector_store_ready = (
            self._vector_store_manager is not None and self._vector_store_manager.is_initialized
        )
        rag_ready = self._rag_agent_service is not None
        aiops_ready = self._aiops_service is not None

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
                message="AIOps 服务已初始化" if aiops_ready else "AIOps 服务尚未初始化",
            ),
        }

    def reset(self) -> None:
        """重置容器中的运行时依赖引用。"""
        self._aiops_service = None
        self._rag_agent_service = None
        self._vector_search_service = None
        self._vector_store_manager = None
        self._embedding_service = None

    async def shutdown(self) -> None:
        """按生命周期关闭运行时依赖。"""
        if self._rag_agent_service is not None:
            await self._rag_agent_service.cleanup()
        self.reset()


service_container = AppContainer()
