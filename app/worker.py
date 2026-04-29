"""独立任务 worker 入口。"""

from __future__ import annotations

import asyncio
import signal

from loguru import logger

from app.infrastructure.tasks import task_dispatcher
from app.platform.persistence import database_manager


async def run_worker() -> None:
    """启动并保持索引任务 worker 运行。"""
    database_manager.initialize()
    await task_dispatcher.start()
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
    await task_dispatcher.shutdown()
    logger.info("Indexing worker 已停止")


if __name__ == "__main__":
    asyncio.run(run_worker())
