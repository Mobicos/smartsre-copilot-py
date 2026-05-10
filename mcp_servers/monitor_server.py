"""智能运维监控 MCP Server

本地实现的监控服务 MCP Server，提供：
- 监控数据查询（CPU、内存、磁盘、网络等）
- 进程信息查询
- 历史工单查询
- 服务信息查询

用于支持运维 Agent 的故障排查场景。
"""

import logging
import random
from datetime import datetime, timedelta
from typing import Any

from fastmcp import FastMCP

from mcp_servers.common import log_tool_call, parse_time_or_default

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("Monitor_MCP_Server")

mcp = FastMCP("Monitor")

# Scenario definitions: (base, peak, jitter)
_SCENARIO_PROFILES: dict[str, dict[str, tuple[float, float, float]]] = {
    "healthy": {
        "cpu": (10.0, 30.0, 2.0),
        "memory": (30.0, 50.0, 1.0),
    },
    "degraded": {
        "cpu": (40.0, 70.0, 3.0),
        "memory": (50.0, 70.0, 2.0),
    },
    "critical": {
        "cpu": (10.0, 96.0, 2.0),
        "memory": (30.0, 85.0, 1.0),
    },
}


def _parse_interval(interval: str) -> int:
    if interval.endswith("h"):
        return int(interval[:-1]) * 60
    return int(interval.rstrip("m") or "1")


def _generate_metric_series(
    start_dt: datetime,
    end_dt: datetime,
    interval_minutes: int,
    base: float,
    peak: float,
    jitter: float,
) -> list[float]:
    """Generate a metric time series that rises from *base* toward *peak*."""
    values: list[float] = []
    current = start_dt
    idx = 0
    while current <= end_dt:
        if idx < 3:
            v = base + idx * (peak - base) * 0.02
        else:
            growth = (idx - 2) * (peak - base) / 12
            v = min(base + growth, peak)
        v = round(v + random.uniform(-jitter, jitter), 1)
        values.append(max(0, min(100, v)))
        current += timedelta(minutes=interval_minutes)
        idx += 1
    return values


# ============================================================
# 监控数据查询工具
# ============================================================


@mcp.tool()
@log_tool_call
def query_cpu_metrics(
    service_name: str,
    start_time: str | None = None,
    end_time: str | None = None,
    interval: str = "1m",
    scenario: str = "critical",
) -> dict[str, Any]:
    """查询服务的 CPU 使用率监控数据。

    Args:
        service_name: 服务名称（必填）
            示例: "data-sync-service"

        start_time: 开始时间（可选，字符串类型）
            格式: "YYYY-MM-DD HH:MM:SS"
            示例: "2026-02-14 10:00:00"
            默认值: 如果不传，默认为当前时间的1小时前

        end_time: 结束时间（可选，字符串类型）
            格式: "YYYY-MM-DD HH:MM:SS"
            示例: "2026-02-14 11:00:00"
            默认值: 如果不传，默认为当前时间

        interval: 数据聚合间隔（可选）
            可选值: "1m" (1分钟), "5m" (5分钟), "1h" (1小时)
            默认值: "1m"

        scenario: 数据场景（可选）
            可选值: "healthy", "degraded", "critical"
            默认值: "critical"
            - healthy:  CPU 10-30%，无告警
            - degraded: CPU 40-70%，warning 告警
            - critical: CPU 从 10% 飙升到 95%，严重告警

    Returns:
        Dict: CPU 监控数据，包含 data_points / statistics / alert_info
    """
    start_dt = parse_time_or_default(start_time, default_offset_hours=-1)
    end_dt = parse_time_or_default(end_time, default_offset_hours=0)
    interval_minutes = _parse_interval(interval)

    profile = _SCENARIO_PROFILES.get(scenario, _SCENARIO_PROFILES["critical"])["cpu"]
    values = _generate_metric_series(start_dt, end_dt, interval_minutes, *profile)

    current_time = start_dt
    data_points = []
    for v in values:
        data_points.append(
            {
                "timestamp": current_time.strftime("%H:%M"),
                "value": v,
                "process_id": "pid-12345",
            }
        )
        current_time += timedelta(minutes=interval_minutes)

    if not data_points:
        return {
            "service_name": service_name,
            "metric_name": "cpu_usage_percent",
            "interval": interval,
            "data_points": [],
            "statistics": {},
        }

    avg_value = round(sum(values) / len(values), 2)
    max_value = max(values)
    min_value = min(values)
    spike_detected = max_value > 80.0

    return {
        "service_name": service_name,
        "metric_name": "cpu_usage_percent",
        "interval": interval,
        "data_points": data_points,
        "statistics": {
            "avg": avg_value,
            "max": max_value,
            "min": min_value,
            "p95": round(
                sorted(values)[int(len(values) * 0.95)] if len(values) > 1 else max_value, 2
            ),
            "spike_detected": spike_detected,
        },
        "alert_info": {
            "triggered": spike_detected,
            "threshold": 80.0,
            "message": "CPU 使用率持续超过 80% 阈值" if spike_detected else "CPU 使用率正常",
        },
    }


@mcp.tool()
@log_tool_call
def query_memory_metrics(
    service_name: str,
    start_time: str | None = None,
    end_time: str | None = None,
    interval: str = "1m",
    scenario: str = "critical",
) -> dict[str, Any]:
    """查询服务的内存使用监控数据。

    Args:
        service_name: 服务名称（必填）
            示例: "data-sync-service"

        start_time: 开始时间（可选，字符串类型）
            格式: "YYYY-MM-DD HH:MM:SS"
            示例: "2026-02-14 10:00:00"
            默认值: 如果不传，默认为当前时间的1小时前

        end_time: 结束时间（可选，字符串类型）
            格式: "YYYY-MM-DD HH:MM:SS"
            示例: "2026-02-14 11:00:00"
            默认值: 如果不传，默认为当前时间

        interval: 数据聚合间隔（可选）
            可选值: "1m" (1分钟), "5m" (5分钟), "1h" (1小时)
            默认值: "1m"

        scenario: 数据场景（可选）
            可选值: "healthy", "degraded", "critical"
            默认值: "critical"
            - healthy:  内存 30-50%，无告警
            - degraded: 内存 50-70%，warning 告警
            - critical: 内存从 30% 飙升到 85%，严重告警

    Returns:
        Dict: 内存监控数据，包含 data_points / statistics / alert_info
    """
    start_dt = parse_time_or_default(start_time, default_offset_hours=-1)
    end_dt = parse_time_or_default(end_time, default_offset_hours=0)
    interval_minutes = _parse_interval(interval)

    profile = _SCENARIO_PROFILES.get(scenario, _SCENARIO_PROFILES["critical"])["memory"]
    values = _generate_metric_series(start_dt, end_dt, interval_minutes, *profile)

    total_gb = 8.0
    current_time = start_dt
    data_points = []
    for v in values:
        data_points.append(
            {
                "timestamp": current_time.strftime("%H:%M"),
                "value": v,
                "used_gb": round((v / 100.0) * total_gb, 2),
                "total_gb": total_gb,
            }
        )
        current_time += timedelta(minutes=interval_minutes)

    if not data_points:
        return {
            "service_name": service_name,
            "metric_name": "memory_usage_percent",
            "interval": interval,
            "data_points": [],
            "statistics": {},
        }

    avg_value = round(sum(values) / len(values), 2)
    max_value = max(values)
    min_value = min(values)
    memory_pressure = max_value > 70.0

    return {
        "service_name": service_name,
        "metric_name": "memory_usage_percent",
        "interval": interval,
        "data_points": data_points,
        "statistics": {
            "avg": avg_value,
            "max": max_value,
            "min": min_value,
            "p95": round(
                sorted(values)[int(len(values) * 0.95)] if len(values) > 1 else max_value, 2
            ),
            "memory_pressure": memory_pressure,
        },
        "alert_info": {
            "triggered": memory_pressure,
            "threshold": 70.0,
            "message": "内存使用率超过 70% 阈值，存在内存压力"
            if memory_pressure
            else "内存使用率正常",
        },
    }


if __name__ == "__main__":
    # 使用 streamable-http 模式，运行在 8004 端口
    mcp.run(transport="streamable-http", host="127.0.0.1", port=8004, path="/mcp")
