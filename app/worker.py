"""独立任务 worker 入口。"""

from __future__ import annotations

import asyncio
import signal

from loguru import logger

from app.infrastructure.tasks import agent_resume_dispatcher, task_dispatcher
from app.utils.logger import setup_logger

setup_logger()


async def run_worker() -> None:
    """启动并保持索引任务 worker 运行。"""
    await task_dispatcher.start()  # type: ignore[attr-defined]
    await agent_resume_dispatcher.start()  # type: ignore[attr-defined]
    logger.info("Indexing worker 已启动，等待任务...")

    stop_event = asyncio.Event()

    def _stop() -> None:
        logger.info("收到停止信号，准备关闭 worker...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _stop)
        except NotImplementedError:
            signal.signal(sig, lambda *_args: _stop())

    await stop_event.wait()
    await agent_resume_dispatcher.shutdown()  # type: ignore[attr-defined]
    await task_dispatcher.shutdown()  # type: ignore[attr-defined]
    logger.info("Indexing worker 已停止")


if __name__ == "__main__":
    asyncio.run(run_worker())
