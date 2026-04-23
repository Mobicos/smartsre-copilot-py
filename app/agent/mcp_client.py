"""MCP 客户端管理。"""

import asyncio
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.interceptors import MCPToolCallRequest
from loguru import logger
from mcp.types import CallToolResult, TextContent

from app.config import config

# 全局 MCP 客户端（延迟初始化）
_mcp_client: MultiServerMCPClient | None = None
_mcp_tools_cache: dict[tuple[tuple[str, str, str], ...], list[Any]] = {}


async def retry_interceptor(
    request: MCPToolCallRequest,
    handler,
    max_retries: int = 3,
    delay: float = 1.0,
):
    """MCP 工具调用重试拦截器

    当工具调用失败时，使用指数退避策略自动重试。
    如果所有重试都失败，返回包含错误信息的结果而不是抛出异常。

    MCPToolCallRequest 结构：
    - name: str - 工具名称
    - args: dict[str, Any] - 工具参数
    - server_name: str - 服务器名称

    Args:
        request: MCP 工具调用请求
        handler: 实际的工具调用处理器
        max_retries: 最大重试次数（默认3次）
        delay: 初始延迟时间（秒，默认1秒）

    Returns:
        CallToolResult: 工具调用结果或错误信息
    """
    last_error = None

    for attempt in range(max_retries):
        try:
            logger.info(
                f"调用 MCP 工具: {request.name} "
                f"(服务器: {request.server_name}, 第 {attempt + 1}/{max_retries} 次尝试)"
            )
            result = await handler(request)
            logger.info(f"MCP 工具 {request.name} 调用成功")
            return result

        except Exception as e:
            last_error = e
            logger.warning(
                f"MCP 工具 {request.name} 调用失败 (第 {attempt + 1}/{max_retries} 次): {str(e)}"
            )

            # 如果不是最后一次尝试，等待后重试
            if attempt < max_retries - 1:
                wait_time = delay * (2**attempt)  # 指数退避
                logger.info(f"等待 {wait_time:.1f} 秒后重试...")
                await asyncio.sleep(wait_time)

    # 所有重试都失败，返回错误结果而不是抛出异常
    error_msg = f"工具 {request.name} 在 {max_retries} 次重试后仍然失败: {str(last_error)}"
    logger.error(error_msg)
    return CallToolResult(content=[TextContent(type="text", text=error_msg)], isError=True)


# 使用配置文件中定义的完整 MCP 服务器配置
DEFAULT_MCP_SERVERS = config.mcp_servers


def _normalize_servers(
    servers: dict[str, dict[str, str]],
) -> dict[str, dict[str, str]]:
    """规范化并去重 MCP 服务配置。"""
    normalized: dict[str, dict[str, str]] = {}
    seen_targets: set[tuple[str, str]] = set()

    for server_name, server_config in servers.items():
        transport = server_config.get("transport", "").strip()
        url = server_config.get("url", "").strip()
        if not transport or not url:
            logger.warning(f"跳过无效 MCP 配置: {server_name}")
            continue

        target = (transport, url)
        if target in seen_targets:
            logger.warning(
                f"MCP 服务 {server_name} 与已有配置重复，已跳过重复加载: {transport} {url}"
            )
            continue

        seen_targets.add(target)
        normalized[server_name] = {
            "transport": transport,
            "url": url,
        }

    return normalized


def _servers_signature(
    servers: dict[str, dict[str, str]],
) -> tuple[tuple[str, str, str], ...]:
    """构建可缓存的服务签名。"""
    return tuple(
        (name, cfg["transport"], cfg["url"])
        for name, cfg in sorted(servers.items(), key=lambda item: item[0])
    )


def _summarize_exception(error: BaseException) -> str:
    """提取更易读的异常摘要。"""
    if error.__cause__ is not None:
        return _summarize_exception(error.__cause__)
    return str(error)


async def get_mcp_client(
    servers: dict[str, dict[str, str]] | None = None,
    tool_interceptors: list | None = None,
    force_new: bool = False,
) -> MultiServerMCPClient:
    """
    获取或初始化 MCP 客户端（不带重试拦截器）

    这是一个单例模式，确保整个应用只有一个 MCP 客户端实例（除非 force_new=True）

    从 langchain-mcp-adapters 0.1.0 开始，MultiServerMCPClient 不再支持作为上下文管理器使用。
    直接创建实例即可使用。

    Args:
        servers: MCP 服务器配置，默认使用 DEFAULT_MCP_SERVERS
        tool_interceptors: 自定义工具拦截器列表
        force_new: 是否强制创建新实例（用于特殊场景，如需要不同配置）

    Returns:
        MultiServerMCPClient: MCP 客户端实例
    """
    global _mcp_client

    normalized_servers = _normalize_servers(servers or DEFAULT_MCP_SERVERS)
    if not normalized_servers:
        raise RuntimeError("没有可用的 MCP 服务配置")

    # 如果请求新实例，直接创建并返回（不缓存）
    if force_new:
        logger.info("创建新的 MCP 客户端实例（非单例）")
        client = _create_mcp_client(normalized_servers, tool_interceptors)
        # 不再需要 __aenter__()，直接返回即可
        return client

    # 单例模式：如果已存在，直接返回
    if _mcp_client is None:
        logger.info("初始化全局 MCP 客户端...")
        _mcp_client = _create_mcp_client(normalized_servers, tool_interceptors)
        # 不再需要 __aenter__()，直接使用即可
        logger.info("全局 MCP 客户端初始化完成")

    return _mcp_client


async def get_mcp_client_with_retry(
    servers: dict[str, dict[str, str]] | None = None,
    tool_interceptors: list | None = None,
    force_new: bool = False,
) -> MultiServerMCPClient:
    """
    获取或初始化带重试功能的 MCP 客户端

    这是一个单例模式，确保整个应用只有一个 MCP 客户端实例（除非 force_new=True）
    重试拦截器会自动添加到拦截器列表的开头

    Args:
        servers: MCP 服务器配置，默认使用 DEFAULT_MCP_SERVERS
        tool_interceptors: 自定义工具拦截器列表（会在重试拦截器之后添加）
        force_new: 是否强制创建新实例（用于特殊场景，如需要不同配置）

    Returns:
        MultiServerMCPClient: 带重试功能的 MCP 客户端实例
    """
    # 构建拦截器列表：重试拦截器在最前面
    interceptors = [retry_interceptor]
    if tool_interceptors:
        interceptors.extend(tool_interceptors)

    return await get_mcp_client(
        servers=servers, tool_interceptors=interceptors, force_new=force_new
    )


def _create_mcp_client(
    servers: dict[str, dict[str, str]], tool_interceptors: list | None = None
) -> MultiServerMCPClient:
    """
    创建 MCP 客户端实例

    Args:
        servers: MCP 服务器配置
        tool_interceptors: 工具拦截器列表

    Returns:
        MultiServerMCPClient: 未初始化的客户端实例
    """
    # MultiServerMCPClient 的第一个参数直接接收 servers 配置字典
    # 格式: {server_name: {"transport": "...", "url": "..."}}
    kwargs: dict[str, Any] = {}

    if tool_interceptors:
        kwargs["tool_interceptors"] = tool_interceptors

    # 第一个参数是 servers 配置，直接传递
    return MultiServerMCPClient(servers, **kwargs)


async def get_mcp_tools_with_fallback(
    servers: dict[str, dict[str, str]] | None = None,
    tool_interceptors: list | None = None,
    force_refresh: bool = False,
) -> list[Any]:
    """按服务逐个加载 MCP 工具，单个服务失败时自动降级。"""
    normalized_servers = _normalize_servers(servers or DEFAULT_MCP_SERVERS)
    if not normalized_servers:
        logger.info("未配置可用的 MCP 服务，跳过 MCP 工具加载")
        return []

    cache_key = _servers_signature(normalized_servers)
    if not force_refresh and cache_key in _mcp_tools_cache:
        return _mcp_tools_cache[cache_key]

    loaded_tools: list[Any] = []
    for server_name, server_config in normalized_servers.items():
        try:
            client = await get_mcp_client_with_retry(
                servers={server_name: server_config},
                tool_interceptors=tool_interceptors,
                force_new=True,
            )
            tools = await client.get_tools()
            logger.info(f"MCP 服务 {server_name} 成功加载 {len(tools)} 个工具")
            loaded_tools.extend(tools)
        except Exception as exc:
            logger.warning(
                f"MCP 服务 {server_name} 不可用，已降级跳过: {_summarize_exception(exc)}"
            )

    _mcp_tools_cache[cache_key] = loaded_tools
    return loaded_tools
