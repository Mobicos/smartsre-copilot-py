"""腾讯云 CLS (Cloud Log Service) MCP Server

本地实现的 CLS 日志服务 MCP Server，提供日志查询、检索和分析功能。
"""

import logging
import random
from datetime import datetime
from typing import Any

from fastmcp import FastMCP

from mcp_servers.common import log_tool_call

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("CLS_MCP_Server")

mcp = FastMCP("CLS")


@mcp.tool()
@log_tool_call
def get_current_timestamp() -> int:
    """获取当前时间戳（以毫秒为单位）。

    此工具用于获取标准的毫秒时间戳，可用于：
    1. 作为 search_log 的 end_time 参数（查询到现在）
    2. 计算历史时间点作为 start_time 参数

    Returns:
        int: 当前时间戳（毫秒），例如: 1708012345000

    使用示例:
        # 获取当前时间
        current = get_current_timestamp()

        # 计算15分钟前的时间
        fifteen_min_ago = current - (15 * 60 * 1000)

        # 计算1小时前的时间
        one_hour_ago = current - (60 * 60 * 1000)

        # 用于搜索最近15分钟的日志
        search_log(
            topic_id="topic-001",
            start_time=fifteen_min_ago,
            end_time=current
        )
    """
    return int(datetime.now().timestamp() * 1000)


@mcp.tool()
@log_tool_call
def get_region_code_by_name(region_name: str) -> dict[str, Any]:
    """根据地区名称搜索对应的地区参数。

    Args:
        region_name: 地区名称（如：北京、上海、广州等）

    Returns:
        Dict: 包含地区代码和相关信息的字典
            - region_code: 地区代码
            - region_name: 地区名称
            - available: 是否可用
    """
    # 模拟地区映射表（实际应该从配置或数据库读取）
    region_mapping = {
        "北京": {"region_code": "ap-beijing", "region_name": "北京", "available": True},
        "上海": {"region_code": "ap-shanghai", "region_name": "上海", "available": True},
        "广州": {"region_code": "ap-guangzhou", "region_name": "广州", "available": True},
    }

    result = region_mapping.get(region_name)
    if result:
        return result
    else:
        return {
            "region_code": None,
            "region_name": region_name,
            "available": False,
            "error": f"未找到地区: {region_name}",
        }


@mcp.tool()
@log_tool_call
def get_topic_info_by_name(topic_name: str, region_code: str | None = None) -> dict[str, Any]:
    """根据主题名称搜索相关的主题信息。

    Args:
        topic_name: 主题名称
        region_code: 地区代码（可选）

    Returns:
        Dict: 包含主题信息的字典
            - topic_id: 主题ID
            - topic_name: 主题名称
            - region_code: 所属地区
            - create_time: 创建时间
            - log_count: 日志数量
    """
    mock_topics = [
        {
            "topic_id": "topic-001",
            "topic_name": "数据同步服务日志",
            "service_name": "data-sync-service",
            "region_code": "ap-beijing",
            "create_time": "2024-01-01 10:00:00",
            "log_count": 0,
            "description": "服务应用日志",
        },
        {
            "topic_id": "topic-002",
            "topic_name": "数据同步服务错误日志",
            "service_name": "data-sync-service",
            "region_code": "ap-beijing",
            "create_time": "2024-01-01 10:00:00",
            "log_count": 0,
            "description": "数据同步服务的错误日志，包含异常堆栈",
        },
        {
            "topic_id": "topic-003",
            "topic_name": "API网关服务日志",
            "service_name": "api-gateway-service",
            "region_code": "ap-shanghai",
            "create_time": "2024-01-01 10:00:00",
            "log_count": 0,
            "description": "API网关服务日志，包含HTTP请求和响应状态",
        },
    ]

    # 根据名称和地区筛选
    for topic in mock_topics:
        if topic["topic_name"] == topic_name:
            if region_code is None or topic["region_code"] == region_code:
                return topic

    return {
        "topic_id": None,
        "topic_name": topic_name,
        "region_code": region_code,
        "error": f"未找到主题: {topic_name}",
    }


@mcp.tool()
@log_tool_call
def search_topic_by_service_name(
    service_name: str, region_code: str | None = None, fuzzy: bool = True
) -> dict[str, Any]:
    """根据服务名称搜索相关的日志主题信息，支持模糊搜索。

    此工具用于根据服务名称查找对应的日志主题（topic），便于后续进行日志查询。

    Args:
        service_name: 服务名称（必填）
            示例: "data-sync-service", "sync", "data-sync"
            说明: 当 fuzzy=True 时，支持部分匹配

        region_code: 地区代码（可选）
            示例: "ap-beijing", "ap-shanghai"
            说明: 如果指定，只返回该地区的主题

        fuzzy: 是否启用模糊搜索（可选，默认 True）
            True: 部分匹配，例如 "sync" 可以匹配 "data-sync-service"
            False: 精确匹配，必须完全一致

    Returns:
        Dict: 搜索结果
            - total: 匹配到的主题数量
            - topics: 主题列表，每个主题包含:
                * topic_id: 主题ID（用于后续日志查询）
                * topic_name: 主题名称
                * service_name: 服务名称
                * region_code: 所属地区
                * create_time: 创建时间
                * log_count: 日志数量
                * description: 主题描述
            - query: 查询条件

    使用示例:
        # 示例1: 模糊搜索（推荐）
        search_topic_by_service_name(service_name="data-sync")
        # 可以匹配: "data-sync-service", "data-sync-worker" 等

        # 示例2: 精确搜索
        search_topic_by_service_name(
            service_name="data-sync-service",
            fuzzy=False
        )

        # 示例3: 指定地区搜索
        search_topic_by_service_name(
            service_name="sync",
            region_code="ap-beijing"
        )

        # 示例4: 查找后进行日志搜索的完整流程
        # 步骤1: 根据服务名查找 topic
        result = search_topic_by_service_name(service_name="data-sync-service")

        # 步骤2: 获取 topic_id
        topic_id = result["topics"][0]["topic_id"]  # "topic-001"

        # 步骤3: 使用 topic_id 查询日志
        current_ts = get_current_timestamp()
        start_ts = current_ts - (15 * 60 * 1000)
        search_log(
            topic_id=topic_id,
            start_time=start_ts,
            end_time=current_ts
        )
    """
    # Mock 主题数据（实际应该从配置或数据库读取）
    mock_topics = [
        {
            "topic_id": "topic-001",
            "topic_name": "数据同步服务日志",
            "service_name": "data-sync-service",
            "region_code": "ap-beijing",
            "create_time": "2024-01-01 10:00:00",
            "log_count": 0,
            "description": "数据同步服务的应用日志，包含同步任务执行情况",
        },
        {
            "topic_id": "topic-002",
            "topic_name": "数据同步服务错误日志",
            "service_name": "data-sync-service",
            "region_code": "ap-beijing",
            "create_time": "2024-01-01 10:00:00",
            "log_count": 0,
            "description": "数据同步服务的错误日志",
        },
        {
            "topic_id": "topic-003",
            "topic_name": "API网关服务日志",
            "service_name": "api-gateway-service",
            "region_code": "ap-shanghai",
            "create_time": "2024-01-01 10:00:00",
            "log_count": 0,
            "description": "API网关服务日志",
        },
    ]

    matched_topics = []

    # 搜索逻辑
    for topic in mock_topics:
        # 地区筛选
        if region_code and topic["region_code"] != region_code:
            continue

        # 服务名称匹配
        topic_service_name = topic.get("service_name", "")

        if fuzzy:
            # 模糊匹配：服务名包含查询字符串，或查询字符串包含服务名
            if (
                service_name.lower() in topic_service_name.lower()
                or topic_service_name.lower() in service_name.lower()
            ):
                matched_topics.append(topic)
        else:
            # 精确匹配
            if topic_service_name == service_name:
                matched_topics.append(topic)

    return {
        "total": len(matched_topics),
        "topics": matched_topics,
        "query": {"service_name": service_name, "region_code": region_code, "fuzzy": fuzzy},
        "message": f"找到 {len(matched_topics)} 个匹配的日志主题"
        if matched_topics
        else f"未找到服务 '{service_name}' 的日志主题",
    }


@mcp.tool()
@log_tool_call
def search_log(
    topic_id: str, start_time: int, end_time: int, query: str | None = None, limit: int = 100
) -> dict[str, Any]:
    """基于提供的查询参数搜索日志。

    Args:
        topic_id: 主题ID（必填）
            示例: "topic-001"

        start_time: 开始时间戳，单位为毫秒（必填，int类型）
            重要: 必须传递整数类型的毫秒时间戳
            获取方式:
            1. 使用 get_current_timestamp() 工具获取当前时间戳
            2. 计算历史时间: current_timestamp - (分钟数 * 60 * 1000)
            示例:
            - 当前时间: 1708012345000
            - 15分钟前: 1708012345000 - (15 * 60 * 1000) = 1708011445000
            - 1小时前: 1708012345000 - (60 * 60 * 1000) = 1708008745000

        end_time: 结束时间戳，单位为毫秒（必填，int类型）
            重要: 必须传递整数类型的毫秒时间戳
            通常使用 get_current_timestamp() 工具获取当前时间作为结束时间
            示例: 1708012345000

        query: 查询语句（可选，CLS 查询语法）
            示例: "level:ERROR" 或 "message:异常"

        limit: 返回结果数量限制（默认100，可选）

    Returns:
        Dict: 搜索结果
            - topic_id: 主题ID
            - start_time: 开始时间戳
            - end_time: 结束时间戳
            - query: 查询语句
            - limit: 结果限制
            - total: 实际返回的日志条数
            - logs: 日志列表，每条日志包含:
                * timestamp: 日志时间（格式: YYYY-MM-DD HH:MM:SS）
                * level: 日志级别
                * message: 日志内容
            - took_ms: 查询耗时（毫秒）
            - message: 查询状态消息

    使用示例:
        # 步骤1: 获取当前时间戳
        current_ts = get_current_timestamp()  # 返回: 1708012345000

        # 步骤2: 计算开始时间（15分钟前）
        start_ts = current_ts - (15 * 60 * 1000)  # 1708011445000

        # 步骤3: 搜索日志
        search_log(
            topic_id="topic-001",
            start_time=start_ts,     # int类型: 1708011445000
            end_time=current_ts,     # int类型: 1708012345000
            limit=100
        )
    """
    query_start = datetime.now()

    topic_handlers = {
        "topic-001": _generate_app_logs,
        "topic-002": _generate_error_logs,
        "topic-003": _generate_gateway_logs,
    }

    handler = topic_handlers.get(topic_id)
    if handler is None:
        return {
            "topic_id": topic_id,
            "start_time": start_time,
            "end_time": end_time,
            "query": query,
            "limit": limit,
            "total": 0,
            "logs": [],
            "took_ms": 0,
            "error": f"主题不存在: {topic_id}",
            "message": f"错误: 未找到主题 {topic_id}，请检查 topic_id 是否正确",
        }

    logs = handler(start_time, end_time, limit, query)
    took_ms = int((datetime.now() - query_start).total_seconds() * 1000) + random.randint(5, 30)

    return {
        "topic_id": topic_id,
        "start_time": start_time,
        "end_time": end_time,
        "query": query,
        "limit": limit,
        "total": len(logs),
        "logs": logs,
        "took_ms": took_ms,
        "message": f"成功查询 {len(logs)} 条日志",
    }


def _ms_to_str(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000).strftime("%Y-%m-%d %H:%M:%S")


def _generate_app_logs(start_time: int, end_time: int, limit: int, query: str | None) -> list[dict]:
    """topic-001: INFO-level application logs for data-sync-service."""
    info_messages = [
        "正在同步元数据……",
        "同步任务开始执行，批次号: batch-{batch}",
        "已同步 {n} 条记录到目标数据库",
        "心跳检测正常，延迟 {latency}ms",
        "消费 Kafka 消息: partition={p} offset={o}",
        "连接池状态: active={a} idle={i} pending=0",
        "缓存命中率 {rate}%，命中 {hits} 次",
        "定时任务 cron-sync 完成，耗时 {dur}s",
    ]
    logs: list[dict] = []
    current_ms = start_time
    step = max(60_000, (end_time - start_time) // max(limit, 1))
    while current_ms <= end_time and len(logs) < limit:
        msg = random.choice(info_messages).format(
            batch=random.randint(1000, 9999),
            n=random.randint(50, 5000),
            latency=random.randint(1, 50),
            p=random.randint(0, 7),
            o=random.randint(100000, 999999),
            a=random.randint(5, 20),
            i=random.randint(2, 10),
            rate=random.randint(85, 99),
            hits=random.randint(100, 5000),
            dur=random.randint(1, 30),
        )
        logs.append({"timestamp": _ms_to_str(current_ms), "level": "INFO", "message": msg})
        current_ms += step
    return logs


def _generate_error_logs(
    start_time: int, end_time: int, limit: int, query: str | None
) -> list[dict]:
    """topic-002: ERROR-level logs with stack traces for data-sync-service."""
    error_templates = [
        {
            "message": "数据库连接超时: Connection to db-master:5432 timed out after 30s",
            "stack": (
                "psycopg.OperationalError: connection timeout\n"
                "  at app.db.pool.get_connection(pool.py:128)\n"
                "  at app.sync.pipeline.execute(pipeline.py:67)\n"
                "  at app.sync.worker.run(worker.py:45)"
            ),
        },
        {
            "message": "Kafka consumer group rebalance detected, partition assignment changed",
            "stack": (
                "kafka.errors.CommitFailedError: Commit cannot be completed since the group has already rebalanced\n"
                "  at kafka.consumer.group.Consumer._commit_offsets(consumer.py:892)\n"
                "  at app.sync.kafka_handler.process_batch(handler.py:134)"
            ),
        },
        {
            "message": "序列化失败: 无法解析消息体，格式不符合预期 schema",
            "stack": (
                "json.JSONDecodeError: Expecting property name enclosed in double quotes: line 1 column 15 (char 14)\n"
                "  at json.decoder.raw_decode(decoder.py:355)\n"
                "  at app.sync.serializer.deserialize(serializer.py:89)\n"
                "  at app.sync.pipeline.process_message(pipeline.py:112)"
            ),
        },
        {
            "message": "目标数据库写入失败: duplicate key value violates unique constraint",
            "stack": (
                'psycopg.errors.UniqueViolation: duplicate key value violates unique constraint "records_pkey"\n'
                "  at app.db.writer.batch_insert(writer.py:203)\n"
                "  at app.sync.pipeline.flush_buffer(pipeline.py:178)"
            ),
        },
        {
            "message": "OOM 风险: 进程内存使用达到 92%，触发保护性拒绝",
            "stack": (
                "MemoryError: Process memory limit exceeded (rss=3.68GB limit=4.00GB)\n"
                "  at app.sync.buffer.acquire_buffer(buffer.py:56)\n"
                "  at app.sync.pipeline.accumulate(pipeline.py:95)"
            ),
        },
    ]
    logs: list[dict] = []
    current_ms = start_time
    step = max(120_000, (end_time - start_time) // max(limit, 1))
    while current_ms <= end_time and len(logs) < limit:
        tmpl = random.choice(error_templates)
        logs.append(
            {
                "timestamp": _ms_to_str(current_ms),
                "level": "ERROR",
                "message": tmpl["message"],
                "stack_trace": tmpl["stack"],
                "service": "data-sync-service",
                "instance": f"data-sync-{random.randint(1, 4):03d}",
            }
        )
        current_ms += step
    return logs


def _generate_gateway_logs(
    start_time: int, end_time: int, limit: int, query: str | None
) -> list[dict]:
    """topic-003: API gateway access logs with HTTP status codes."""
    endpoints = [
        ("GET", "/api/v1/users", [200, 200, 200, 404]),
        ("POST", "/api/v1/orders", [201, 201, 400, 500]),
        ("GET", "/api/v1/products/{id}", [200, 200, 404, 404]),
        ("PUT", "/api/v1/users/{id}/profile", [200, 200, 403, 422]),
        ("DELETE", "/api/v1/sessions/{id}", [204, 204, 401, 500]),
        ("GET", "/api/v1/health", [200, 200, 200, 200]),
    ]
    logs: list[dict] = []
    current_ms = start_time
    step = max(30_000, (end_time - start_time) // max(limit, 1))
    while current_ms <= end_time and len(logs) < limit:
        method, path = random.choice(endpoints)
        status = random.choice([200, 200, 200, 200, 201, 301, 400, 403, 404, 500, 502, 503])
        latency_ms = random.randint(2, 800) if status < 500 else random.randint(1000, 5000)
        logs.append(
            {
                "timestamp": _ms_to_str(current_ms),
                "level": "WARN" if status >= 400 else "INFO",
                "message": f"{method} {path} -> {status} ({latency_ms}ms)",
                "http_method": method,
                "path": path,
                "status_code": status,
                "latency_ms": latency_ms,
                "client_ip": f"10.0.{random.randint(1, 254)}.{random.randint(1, 254)}",
                "request_id": f"req-{random.randint(100000, 999999)}",
            }
        )
        current_ms += step
    return logs


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="127.0.0.1", port=8003, path="/mcp")
