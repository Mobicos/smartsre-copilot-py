"""Application logger configuration."""

from __future__ import annotations

import re
import sys
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from loguru import Record

from app.config import LOGS_DIR, config

_SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(api[_-]?key[=:\s]+)\S+", re.IGNORECASE), r"\1***REDACTED***"),
    (re.compile(r"(password[=:\s]+)\S+", re.IGNORECASE), r"\1***REDACTED***"),
    (re.compile(r"(secret[=:\s]+)\S+", re.IGNORECASE), r"\1***REDACTED***"),
    (re.compile(r"(token[=:\s]+)\S+", re.IGNORECASE), r"\1***REDACTED***"),
    (re.compile(r"(postgresql(\+\w+)?://[^:]+:)[^@]+(@)", re.IGNORECASE), r"\1***\3"),
    (re.compile(r"(redis://[^:]*:)[^@]+(@)", re.IGNORECASE), r"\1***\2"),
]


def _redact_secrets(text: str) -> str:
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _patch_record(record: Record) -> None:
    record["extra"].setdefault("request_id", "-")
    record["message"] = _redact_secrets(record["message"])


def _human_format(record: Record) -> str:
    request_id = record["extra"].get("request_id", "-")
    return (
        f"<green>{record['time']:%Y-%m-%d %H:%M:%S}</green> | "
        f"<level>{record['level'].name:<8}</level> | "
        f"<cyan>request_id={request_id}</cyan> | "
        f"<cyan>{record['module']}</cyan>.<cyan>{record['function']}</cyan>:<cyan>{record['line']}</cyan> | "
        f"<level>{record['message']}</level>\n"
    )


def setup_logger() -> None:
    """Configure global Loguru sinks for console and file output."""
    logger.configure(patcher=_patch_record)
    logger.remove()
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    sink_level = "DEBUG" if config.debug else "INFO"
    use_json = config.is_production

    logger.add(
        sys.stdout,
        level=sink_level,
        colorize=not use_json,
        format="{message}" if use_json else _human_format,
        serialize=use_json,
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
            diagnose=config.debug,
            level=sink_level,
            format="{message}" if use_json else _human_format,
            serialize=use_json,
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
            diagnose=config.debug,
            level=sink_level,
            format="{message}" if use_json else _human_format,
            serialize=use_json,
            enqueue=False,
        )
