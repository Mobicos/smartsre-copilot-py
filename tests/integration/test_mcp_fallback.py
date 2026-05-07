from __future__ import annotations

import pytest

from app.infrastructure.tools import mcp_client


async def test_get_mcp_tools_with_fallback_returns_empty_for_missing_config():
    tools = await mcp_client.get_mcp_tools_with_fallback(servers={})

    assert tools == []


async def test_get_mcp_tools_with_fallback_degrades_when_server_fails(monkeypatch):
    async def raise_connection_error(*args, **kwargs):
        raise RuntimeError("server unavailable")

    servers = {"monitor": {"transport": "streamable-http", "url": "http://localhost:1/mcp"}}
    monkeypatch.setattr(mcp_client, "get_mcp_client_with_retry", raise_connection_error)
    mcp_client._mcp_tools_cache.clear()

    tools = await mcp_client.get_mcp_tools_with_fallback(servers=servers, force_refresh=True)

    assert tools == []


@pytest.mark.parametrize(
    "servers",
    [
        {"one": {"transport": "", "url": "http://localhost/mcp"}},
        {"one": {"transport": "streamable-http", "url": ""}},
    ],
)
def test_normalize_servers_drops_incomplete_entries(servers):
    assert mcp_client._normalize_servers(servers) == {}
