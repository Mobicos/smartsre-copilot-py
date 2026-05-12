"""任务调度器抽象与本地/分离式 worker 实现。"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from loguru import logger

from app.core.config import AppSettings
from app.infrastructure import redis_manager
from app.platform.persistence.repositories.indexing import indexing_task_repository

IndexingTaskProcessor = Callable[[str, str], str]


def _default_indexing_task_processor(task_id: str, file_path: str) -> str:
    from app.api.providers import get_indexing_task_service

    return get_indexing_task_service().process_task(task_id, file_path)


class LocalTaskDispatcher:
    """基于数据库队列的任务调度器。

    在 `embedded` 模式下，主服务内启动一个 worker。
    在 `detached` 模式下，主服务只负责入队，独立 worker 进程负责消费。
    """

    def __init__(
        self,
        settings: AppSettings | None = None,
        *,
        indexing_task_processor: IndexingTaskProcessor | None = None,
    ) -> None:
        self._settings = settings or AppSettings.from_env()
        self._wake_event = asyncio.Event()
        self._worker_task: asyncio.Task[None] | None = None
        self._started = False
        self._indexing_task_processor = indexing_task_processor or _default_indexing_task_processor

    async def start(self) -> None:
        """启动任务调度器并恢复未完成任务。"""
        if self._started:
            return

        self._started = True
        requeued = indexing_task_repository.requeue_stale_processing_tasks(
            self._settings.task_requeue_timeout_seconds
        )
        if requeued:
            logger.warning(f"已重新入队 {requeued} 个超时 processing 任务")

        if self._settings.task_queue_backend == "redis":
            redis_manager.initialize()
            self._republish_queued_tasks_to_redis()

        self._worker_task = asyncio.create_task(self._worker_loop(), name="indexing-task-worker")
        self._wake_event.set()

    async def shutdown(self) -> None:
        """停止任务调度器。"""
        if not self._started:
            return

        self._started = False
        self._wake_event.set()
        if self._worker_task is not None:
            await self._worker_task
        self._worker_task = None

    async def enqueue_indexing_task(self, task_id: str, file_path: str) -> None:
        """通知调度器有新任务入队。"""
        logger.info(f"索引任务已入队: {task_id}, file={file_path}")
        if self._settings.task_queue_backend == "redis":
            redis_manager.enqueue_json(
                self._settings.redis_task_queue_name,
                {"task_id": task_id, "file_path": file_path},
            )
            return

        if self._started:
            self._wake_event.set()

    async def _worker_loop(self) -> None:
        """持续消费索引任务。"""
        if self._settings.task_queue_backend == "redis":
            await self._redis_worker_loop()
            return

        poll_interval = max(self._settings.task_poll_interval_ms, 100) / 1000
        while self._started:
            task = indexing_task_repository.claim_next_queued_task()
            if task is not None:
                result = self._indexing_task_processor(task["task_id"], task["file_path"])
                if result == "queued":
                    self._wake_event.set()
                continue

            self._wake_event.clear()
            try:
                await asyncio.wait_for(self._wake_event.wait(), timeout=poll_interval)
            except TimeoutError:
                continue

    async def _redis_worker_loop(self) -> None:
        """消费 Redis 队列任务。"""
        while self._started:
            payload = await asyncio.to_thread(
                redis_manager.dequeue_json,
                self._settings.redis_task_queue_name,
                1,
            )
            if payload is None:
                continue

            task_id = payload.get("task_id")
            file_path = payload.get("file_path")
            if not task_id or not file_path:
                logger.warning(f"跳过无效 Redis 任务载荷: {payload}")
                continue

            claimed = indexing_task_repository.claim_task(task_id)
            if claimed is None:
                logger.info(f"任务已被其他 worker 处理或状态已变化，跳过: {task_id}")
                continue

            result = self._indexing_task_processor(task_id, file_path)
            if result == "queued":
                redis_manager.enqueue_json(
                    self._settings.redis_task_queue_name,
                    {"task_id": task_id, "file_path": file_path},
                )

    def _republish_queued_tasks_to_redis(self) -> None:
        """启动时将排队任务重新推入 Redis。"""
        queued_tasks = indexing_task_repository.list_tasks_by_status(["queued"])
        for task in queued_tasks:
            redis_manager.enqueue_json(
                self._settings.redis_task_queue_name,
                {"task_id": task["task_id"], "file_path": task["file_path"]},
            )

    @property
    def is_started(self) -> bool:
        """当前调度器是否已启动。"""
        return self._started


def _get_task_dispatcher() -> LocalTaskDispatcher:
    """Return the lazily-initialized module-level dispatcher."""
    global _task_dispatcher_instance
    if _task_dispatcher_instance is None:
        _task_dispatcher_instance = LocalTaskDispatcher()
    return _task_dispatcher_instance


_task_dispatcher_instance: LocalTaskDispatcher | None = None


def __getattr__(name: str) -> LocalTaskDispatcher:
    if name == "task_dispatcher":
        return _get_task_dispatcher()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
