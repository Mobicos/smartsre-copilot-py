"""Tool discovery for the Native Agent runtime."""

from __future__ import annotations

from typing import Any

from app.infrastructure.tools import ToolScope, tool_registry


class ToolCatalog:
    """Discover local and MCP tools through the existing registry."""

    async def get_tools(
        self,
        scope: ToolScope,
        *,
        force_refresh: bool = False,
    ) -> list[Any]:
        return await tool_registry.get_tools(scope, force_refresh=force_refresh)
