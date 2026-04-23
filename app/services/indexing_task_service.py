"""索引任务应用服务。"""

from loguru import logger

from app.config import config
from app.persistence import indexing_task_repository
from app.services.vector_index_service import vector_index_service


class IndexingTaskService:
    """管理索引任务的提交与执行。"""

    def submit_task(self, filename: str, file_path: str) -> str:
        """登记待执行的索引任务。"""
        existing_task = indexing_task_repository.find_active_task_by_file_path(file_path)
        if existing_task is not None:
            logger.info(
                f"复用现有活跃索引任务: {existing_task['task_id']}, 文件: {file_path}, 状态: {existing_task['status']}"
            )
            return str(existing_task["task_id"])

        task_id = indexing_task_repository.create_task(
            filename,
            file_path,
            max_retries=max(config.indexing_task_max_retries, 1),
        )
        logger.info(f"已提交索引任务: {task_id}, 文件: {file_path}")
        return task_id

    def process_task(self, task_id: str, file_path: str) -> str:
        """执行索引任务并更新状态。"""
        try:
            vector_index_service.index_single_file(file_path)
            indexing_task_repository.update_task(task_id, status="completed")
            logger.info(f"索引任务执行完成: {task_id}")
            return "completed"
        except Exception as exc:
            task = indexing_task_repository.mark_retry_or_failed(
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


indexing_task_service = IndexingTaskService()
