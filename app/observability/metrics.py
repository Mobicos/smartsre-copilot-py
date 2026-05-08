"""Prometheus metrics rendering without an external runtime dependency."""

from __future__ import annotations

from collections import defaultdict
from threading import Lock

from loguru import logger
from sqlalchemy import text

from app.config import config
from app.platform.persistence.database import get_engine

_http_lock = Lock()
_http_requests: defaultdict[tuple[str, str, str], int] = defaultdict(int)
_http_duration_seconds_sum: defaultdict[tuple[str, str, str], float] = defaultdict(float)


def observe_http_request(
    *,
    method: str,
    path: str,
    status_code: int,
    duration_seconds: float,
) -> None:
    """Record one HTTP request for the in-process Prometheus scrape."""
    key = (method.upper(), _normalize_path(path), str(status_code))
    with _http_lock:
        _http_requests[key] += 1
        _http_duration_seconds_sum[key] += max(duration_seconds, 0.0)


def render_prometheus_metrics() -> str:
    """Return Prometheus text exposition format for service and product metrics."""
    lines: list[str] = [
        "# HELP smartsre_service_info SmartSRE service metadata.",
        "# TYPE smartsre_service_info gauge",
        _sample(
            "smartsre_service_info",
            {"service": config.app_name, "version": config.app_version},
            1,
        ),
        "# HELP smartsre_http_requests_total Total HTTP requests handled by FastAPI.",
        "# TYPE smartsre_http_requests_total counter",
    ]

    with _http_lock:
        request_items = sorted(_http_requests.items())
        duration_items = sorted(_http_duration_seconds_sum.items())

    for (method, path, status), count in request_items:
        lines.append(
            _sample(
                "smartsre_http_requests_total",
                {"method": method, "path": path, "status": status},
                count,
            )
        )

    lines.extend(
        [
            "# HELP smartsre_http_request_duration_seconds HTTP request latency.",
            "# TYPE smartsre_http_request_duration_seconds summary",
        ]
    )
    for (method, path, status), total_seconds in duration_items:
        labels = {"method": method, "path": path, "status": status}
        lines.append(_sample("smartsre_http_request_duration_seconds_sum", labels, total_seconds))
        lines.append(
            _sample(
                "smartsre_http_request_duration_seconds_count",
                labels,
                _http_requests[(method, path, status)],
            )
        )

    try:
        lines.extend(_database_metrics())
    except Exception as exc:
        logger.warning(f"Prometheus database metrics scrape failed: {exc}")
        lines.extend(
            [
                "# HELP smartsre_metrics_scrape_errors_total Metrics scrape errors.",
                "# TYPE smartsre_metrics_scrape_errors_total counter",
                _sample(
                    "smartsre_metrics_scrape_errors_total",
                    {"component": "database"},
                    1,
                ),
            ]
        )

    return "\n".join(lines) + "\n"


def _database_metrics() -> list[str]:
    lines = [
        "# HELP smartsre_agent_runs_total Native Agent runs grouped by status.",
        "# TYPE smartsre_agent_runs_total gauge",
    ]
    engine = get_engine()
    with engine.connect() as connection:
        for row in connection.execute(
            text("SELECT status, COUNT(*) AS count FROM agent_runs GROUP BY status")
        ):
            lines.append(_sample("smartsre_agent_runs_total", {"status": str(row[0])}, row[1]))

        event_counts = {
            str(row[0]): int(row[1])
            for row in connection.execute(
                text("SELECT event_type, COUNT(*) AS count FROM agent_events GROUP BY event_type")
            )
        }
        lines.extend(
            [
                "# HELP smartsre_agent_tool_calls_total Native Agent tool call events.",
                "# TYPE smartsre_agent_tool_calls_total gauge",
                _sample("smartsre_agent_tool_calls_total", {}, event_counts.get("tool_call", 0)),
                "# HELP smartsre_agent_approvals_total Native Agent approval events.",
                "# TYPE smartsre_agent_approvals_total gauge",
                _sample(
                    "smartsre_agent_approvals_total",
                    {"state": "required"},
                    event_counts.get("approval_required", 0),
                ),
                _sample(
                    "smartsre_agent_approvals_total",
                    {"state": "resumed"},
                    event_counts.get("approval_resume", 0),
                ),
                "# HELP smartsre_agent_handoffs_total Native Agent handoff events.",
                "# TYPE smartsre_agent_handoffs_total gauge",
                _sample("smartsre_agent_handoffs_total", {}, event_counts.get("handoff", 0)),
                "# HELP smartsre_indexing_tasks_total Indexing tasks grouped by status.",
                "# TYPE smartsre_indexing_tasks_total gauge",
            ]
        )

        for row in connection.execute(
            text("SELECT status, COUNT(*) AS count FROM indexing_tasks GROUP BY status")
        ):
            lines.append(_sample("smartsre_indexing_tasks_total", {"status": str(row[0])}, row[1]))

    return lines


def _sample(name: str, labels: dict[str, str], value: int | float) -> str:
    if labels:
        label_text = ",".join(
            f'{key}="{_escape_label_value(label_value)}"'
            for key, label_value in sorted(labels.items())
        )
        return f"{name}{{{label_text}}} {_format_value(value)}"
    return f"{name} {_format_value(value)}"


def _escape_label_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _format_value(value: int | float | str) -> str:
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.6f}".rstrip("0").rstrip(".") or "0"
    return str(value)


def _normalize_path(path: str) -> str:
    return path or "unknown"
