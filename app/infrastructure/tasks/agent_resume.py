"""Redis-backed approval resume worker."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from loguru import logger

from app.core.config import AppSettings
from app.infrastructure import redis_manager

AgentResumeTaskProcessor = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


async def _default_agent_resume_task_processor(payload: dict[str, Any]) -> dict[str, Any]:
    from app.api.providers import get_agent_resume_service

    return await get_agent_resume_service().process_resume_task(payload)


class AgentResumeDispatcher:
    """Consume approved action resume tasks from Redis."""

    def __init__(
        self,
        settings: AppSettings | None = None,
        *,
        resume_task_processor: AgentResumeTaskProcessor | None = None,
    ) -> None:
        self._settings = settings or AppSettings.from_env()
        self._resume_task_processor = resume_task_processor or _default_agent_resume_task_processor
        self._worker_task: asyncio.Task[None] | None = None
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        if self._settings.task_queue_backend != "redis":
            logger.info("Agent resume dispatcher idle because Redis queue backend is disabled")
            return
        redis_manager.initialize()
        self._worker_task = asyncio.create_task(
            self._worker_loop(),
            name="agent-resume-worker",
        )

    async def shutdown(self) -> None:
        if not self._started:
            return
        self._started = False
        if self._worker_task is not None:
            await self._worker_task
        self._worker_task = None

    async def _worker_loop(self) -> None:
        while self._started:
            payload = await asyncio.to_thread(
                redis_manager.dequeue_json,
                self._settings.agent_resume_queue_name,
                1,
            )
            if payload is None:
                continue
            result = await self._resume_task_processor(payload)
            logger.info(f"Agent resume task processed: {result}")

    @property
    def is_started(self) -> bool:
        return self._started


_agent_resume_dispatcher_instance: AgentResumeDispatcher | None = None


def _get_agent_resume_dispatcher() -> AgentResumeDispatcher:
    global _agent_resume_dispatcher_instance
    if _agent_resume_dispatcher_instance is None:
        _agent_resume_dispatcher_instance = AgentResumeDispatcher()
    return _agent_resume_dispatcher_instance


def __getattr__(name: str) -> AgentResumeDispatcher:
    if name == "agent_resume_dispatcher":
        return _get_agent_resume_dispatcher()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
