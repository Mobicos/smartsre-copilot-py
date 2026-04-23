"""Application logger configuration."""

import sys

from loguru import logger

from app.config import LOGS_DIR, config


def setup_logger() -> None:
    """Configure global Loguru sinks for console and file output."""
    logger.remove()
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    logger.add(
        sys.stdout,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | "
            "<cyan>{module}</cyan>.<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        level="DEBUG" if config.debug else "INFO",
        colorize=True,
        backtrace=True,
        diagnose=config.debug,
    )

    try:
        logger.add(
            str(LOGS_DIR / "app_{time:YYYY-MM-DD}.log"),
            rotation="00:00",
            retention="7 days",
            compression="zip",
            encoding="utf-8",
            backtrace=True,
            diagnose=True,
            level="INFO",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {module}.{function}:{line} | {message}",
            enqueue=True,
        )
    except OSError:
        # Fallback for restricted environments where multiprocessing queues are unavailable.
        logger.add(
            str(LOGS_DIR / "app_{time:YYYY-MM-DD}.log"),
            rotation="00:00",
            retention="7 days",
            compression="zip",
            encoding="utf-8",
            backtrace=True,
            diagnose=True,
            level="INFO",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {module}.{function}:{line} | {message}",
            enqueue=False,
        )


setup_logger()
