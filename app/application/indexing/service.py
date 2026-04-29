"""索引任务应用服务。"""

from collections.abc import Callable
from typing import Any, Protocol

from loguru import logger


class IndexingTaskRepositoryPort(Protocol):
    """Persistence operations required by indexing task orchestration."""

    def find_active_task_by_file_path(self, file_path: str) -> dict[str, Any] | None: ...

    def create_task(self, filename: str, file_path: str, *, max_retries: int) -> str: ...

    def update_task(
        self,
        task_id: str,
        *,
        status: str,
        error_message: str | None = None,
    ) -> None: ...

    def mark_retry_or_failed(
        self, task_id: str, *, error_message: str
    ) -> dict[str, Any] | None: ...


class VectorIndexerPort(Protocol):
    """Vector indexing capability required by indexing task execution."""

    def index_single_file(self, file_path: str) -> None: ...


class IndexingTaskService:
    """管理索引任务的提交与执行。"""

    def __init__(
        self,
        *,
        repository: IndexingTaskRepositoryPort,
        vector_indexer_provider: Callable[[], VectorIndexerPort],
        max_retries_provider: Callable[[], int],
    ) -> None:
        self._repository = repository
        self._vector_indexer_provider = vector_indexer_provider
        self._max_retries_provider = max_retries_provider

    def submit_task(self, filename: str, file_path: str) -> str:
        """登记待执行的索引任务。"""
        existing_task = self._repository.find_active_task_by_file_path(file_path)
        if existing_task is not None:
            logger.info(
                f"复用现有活跃索引任务: {existing_task['task_id']}, 文件: {file_path}, 状态: {existing_task['status']}"
            )
            return str(existing_task["task_id"])

        task_id = self._repository.create_task(
            filename,
            file_path,
            max_retries=max(self._max_retries_provider(), 1),
        )
        logger.info(f"已提交索引任务: {task_id}, 文件: {file_path}")
        return task_id

    def process_task(self, task_id: str, file_path: str) -> str:
        """执行索引任务并更新状态。"""
        try:
            self._vector_indexer_provider().index_single_file(file_path)
            self._repository.update_task(task_id, status="completed")
            logger.info(f"索引任务执行完成: {task_id}")
            return "completed"
        except Exception as exc:
            task = self._repository.mark_retry_or_failed(
                task_id,
                error_message=str(exc),
            )
            if task is None:
                logger.error(f"索引任务执行失败且任务不存在: {task_id}, 错误: {exc}")
                return "missing"

            logger.error(
                f"索引任务执行失败: {task_id}, 状态: {task['status']}, "
                f"attempt={task['attempt_count']}/{task['max_retries']}, 错误: {exc}"
            )
            return str(task["status"])
