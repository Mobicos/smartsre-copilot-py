"""Shared utilities for MCP servers."""

from __future__ import annotations

import functools
import json
import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


def log_tool_call(func: F) -> F:
    """Decorator: log tool calls including method name, parameters, and result status."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        logger = logging.getLogger(func.__module__)
        method_name = func.__name__

        logger.info("=" * 80)
        logger.info(f"调用方法: {method_name}")

        if kwargs:
            try:
                params_str = json.dumps(kwargs, ensure_ascii=False, indent=2)
            except (TypeError, ValueError):
                params_str = str(kwargs)
            logger.info(f"参数信息:\n{params_str}")
        else:
            logger.info("参数信息: 无")

        try:
            result = func(*args, **kwargs)
            logger.info("返回状态: SUCCESS")

            if isinstance(result, dict):
                summary = {
                    k: v
                    if not isinstance(v, (list, dict))
                    else f"<{type(v).__name__} with {len(v)} items>"
                    for k, v in list(result.items())[:5]
                }
                logger.info(f"返回结果摘要: {json.dumps(summary, ensure_ascii=False)}")
            else:
                logger.info(f"返回结果: {result}")

            logger.info("=" * 80)
            return result

        except Exception as e:
            logger.error("返回状态: ERROR")
            logger.error(f"错误信息: {str(e)}")
            logger.error("=" * 80)
            raise

    return wrapper  # type: ignore[return-value]


def parse_time_or_default(time_str: str | None, default_offset_hours: int = 0) -> datetime:
    """Parse a time string or return a default time.

    Args:
        time_str: Time string in ``YYYY-MM-DD HH:MM:SS`` format.
        default_offset_hours: Hour offset from now when *time_str* is ``None``.
    """
    if time_str:
        try:
            return datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    return datetime.now() + timedelta(hours=default_offset_hours)


def generate_time_series(
    base_time: datetime, minutes_offset: int, format_str: str = "%Y-%m-%d %H:%M:%S"
) -> str:
    """Return a formatted time string offset from *base_time*."""
    result_time = base_time + timedelta(minutes=minutes_offset)
    return result_time.strftime(format_str)
