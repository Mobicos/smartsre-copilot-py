"""Agent tool registry.

统一管理本地工具、MCP 工具及其组合策略，避免不同运行时各自拼装工具。
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any, Literal

from loguru import logger

from app.core.config import AppSettings
from app.infrastructure.tools.local import get_current_time, retrieve_knowledge
from app.infrastructure.tools.mcp_client import get_mcp_tools_with_fallback

ToolScope = Literal["chat", "diagnosis"]


class ToolRegistry:
    """按场景提供统一的工具集合。"""

    def __init__(self, settings: AppSettings | None = None) -> None:
        self._settings = settings or AppSettings.from_env()

    def get_local_tools(self, scope: ToolScope) -> list[Any]:
        """返回指定场景的本地工具。"""
        local_tools: dict[ToolScope, list[Any]] = {
            "chat": [retrieve_knowledge, get_current_time],
            "diagnosis": [get_current_time, retrieve_knowledge],
        }
        return list(local_tools[scope])

    async def get_tools(
        self,
        scope: ToolScope,
        *,
        include_mcp: bool = True,
        force_refresh: bool = False,
    ) -> list[Any]:
        """返回指定场景的工具集合。"""
        local_tools = self.get_local_tools(scope)
        mcp_tools = await self._load_mcp_tools(force_refresh=force_refresh) if include_mcp else []
        merged_tools = self._merge_tools(local_tools, mcp_tools)
        logger.info(
            "工具注册表返回工具集合: scope={}, 本地={}, MCP={}, 合并后={}",
            scope,
            len(local_tools),
            len(mcp_tools),
            len(merged_tools),
        )
        return merged_tools

    async def get_chat_tools(self, *, force_refresh: bool = False) -> list[Any]:
        """返回聊天运行时工具集合。"""
        return await self.get_tools("chat", force_refresh=force_refresh)

    async def get_diagnosis_tools(self, *, force_refresh: bool = False) -> list[Any]:
        """返回诊断运行时工具集合。"""
        return await self.get_tools("diagnosis", force_refresh=force_refresh)

    async def _load_mcp_tools(self, *, force_refresh: bool = False) -> list[Any]:
        """在超时保护下加载 MCP 工具。"""
        try:
            return await asyncio.wait_for(
                get_mcp_tools_with_fallback(force_refresh=force_refresh),
                timeout=self._settings.mcp_tools_load_timeout_seconds,
            )
        except TimeoutError:
            logger.warning(
                "MCP 工具加载超时，已降级跳过，timeout={}s",
                self._settings.mcp_tools_load_timeout_seconds,
            )
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning("MCP 工具加载失败，已降级跳过: {}", exc)
        return []

    def _merge_tools(self, *tool_groups: Sequence[Any]) -> list[Any]:
        """按工具名称去重并保持顺序。"""
        merged: list[Any] = []
        seen_tool_names: set[str] = set()

        for tools in tool_groups:
            for tool in tools:
                tool_name = self._tool_name(tool)
                if tool_name in seen_tool_names:
                    logger.warning("检测到重复工具 {}, 已跳过重复实例", tool_name)
                    continue
                seen_tool_names.add(tool_name)
                merged.append(tool)

        return merged

    @staticmethod
    def _tool_name(tool: Any) -> str:
        """提取工具名称。"""
        if hasattr(tool, "name"):
            return str(tool.name)
        return repr(tool)


_tool_registry_instance: ToolRegistry | None = None


def get_tool_registry(settings: AppSettings | None = None) -> ToolRegistry:
    global _tool_registry_instance
    if _tool_registry_instance is None:
        _tool_registry_instance = ToolRegistry(settings=settings)
    return _tool_registry_instance


def __getattr__(name: str) -> ToolRegistry:
    if name == "tool_registry":
        return get_tool_registry()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
