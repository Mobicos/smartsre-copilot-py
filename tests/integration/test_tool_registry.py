from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.infrastructure.tools import ToolRegistry


def test_tool_registry_returns_expected_local_tools_order():
    registry = ToolRegistry()

    local_tools = registry.get_local_tools("chat")

    assert [tool.name for tool in local_tools] == ["retrieve_knowledge", "get_current_time"]


@pytest.mark.asyncio
async def test_tool_registry_deduplicates_tools_by_name(monkeypatch: pytest.MonkeyPatch):
    registry = ToolRegistry()

    async def fake_load_mcp_tools(*, force_refresh: bool = False) -> list[object]:
        assert not force_refresh
        return [
            SimpleNamespace(name="retrieve_knowledge"),
            SimpleNamespace(name="SearchLog"),
        ]

    monkeypatch.setattr(registry, "_load_mcp_tools", fake_load_mcp_tools)

    tools = await registry.get_chat_tools()

    assert [tool.name for tool in tools] == [
        "retrieve_knowledge",
        "get_current_time",
        "SearchLog",
    ]


@pytest.mark.asyncio
async def test_tool_registry_falls_back_on_mcp_timeout(monkeypatch: pytest.MonkeyPatch):
    registry = ToolRegistry()

    async def fake_get_mcp_tools_with_fallback(*, force_refresh: bool = False) -> list[object]:
        assert not force_refresh
        raise TimeoutError("simulated timeout")

    monkeypatch.setattr(
        "app.infrastructure.tools.registry.get_mcp_tools_with_fallback",
        fake_get_mcp_tools_with_fallback,
    )

    tools = await registry.get_diagnosis_tools()

    assert [tool.name for tool in tools] == ["get_current_time", "retrieve_knowledge"]
