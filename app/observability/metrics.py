"""Prometheus metrics backed by the official client library."""

from __future__ import annotations

from collections.abc import Iterable

from loguru import logger
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from sqlalchemy import text

from app.platform.persistence.database import get_engine

METRICS_CONTENT_TYPE = CONTENT_TYPE_LATEST

_REGISTRY = CollectorRegistry(auto_describe=True)

_SERVICE_INFO = Gauge(
    "smartsre_service_info",
    "SmartSRE service metadata.",
    ("service", "version"),
    registry=_REGISTRY,
)
_HTTP_REQUESTS = Counter(
    "smartsre_http_requests_total",
    "Total HTTP requests handled by FastAPI.",
    ("method", "path", "status"),
    registry=_REGISTRY,
)
_HTTP_REQUEST_DURATION = Histogram(
    "smartsre_http_request_duration_seconds",
    "HTTP request latency.",
    ("method", "path", "status"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
    registry=_REGISTRY,
)
_AGENT_RUNS = Gauge(
    "smartsre_agent_runs",
    "Current Native Agent runs grouped by status.",
    ("status",),
    registry=_REGISTRY,
)
_AGENT_RUNS_LEGACY = Gauge(
    "smartsre_agent_runs_total",
    "Legacy alias for smartsre_agent_runs.",
    ("status",),
    registry=_REGISTRY,
)
_AGENT_TOOL_CALLS = Gauge(
    "smartsre_agent_tool_calls",
    "Current Native Agent tool call event count from storage.",
    registry=_REGISTRY,
)
_AGENT_TOOL_CALLS_LEGACY = Gauge(
    "smartsre_agent_tool_calls_total",
    "Legacy alias for smartsre_agent_tool_calls.",
    registry=_REGISTRY,
)
_AGENT_APPROVALS = Gauge(
    "smartsre_agent_approvals",
    "Current Native Agent approval event count from storage.",
    ("state",),
    registry=_REGISTRY,
)
_AGENT_APPROVALS_LEGACY = Gauge(
    "smartsre_agent_approvals_total",
    "Legacy alias for smartsre_agent_approvals.",
    ("state",),
    registry=_REGISTRY,
)
_AGENT_HANDOFFS = Gauge(
    "smartsre_agent_handoffs",
    "Current Native Agent handoff event count from storage.",
    registry=_REGISTRY,
)
_AGENT_HANDOFFS_LEGACY = Gauge(
    "smartsre_agent_handoffs_total",
    "Legacy alias for smartsre_agent_handoffs.",
    registry=_REGISTRY,
)
_INDEXING_TASKS = Gauge(
    "smartsre_indexing_tasks",
    "Current indexing tasks grouped by status.",
    ("status",),
    registry=_REGISTRY,
)
_INDEXING_TASKS_LEGACY = Gauge(
    "smartsre_indexing_tasks_total",
    "Legacy alias for smartsre_indexing_tasks.",
    ("status",),
    registry=_REGISTRY,
)
_SCRAPE_ERRORS = Counter(
    "smartsre_metrics_scrape_errors_total",
    "Metrics scrape errors.",
    ("component",),
    registry=_REGISTRY,
)

_SERVICE_INFO.labels(service="SmartSRE Copilot", version="0.1.0.dev0").set(1)


def observe_http_request(
    *,
    method: str,
    path: str,
    status_code: int,
    duration_seconds: float,
) -> None:
    """Record one HTTP request for Prometheus."""
    labels = (method.upper(), _normalize_path(path), str(status_code))
    _HTTP_REQUESTS.labels(*labels).inc()
    _HTTP_REQUEST_DURATION.labels(*labels).observe(max(duration_seconds, 0.0))


def render_prometheus_metrics() -> bytes:
    """Return Prometheus text exposition bytes."""
    try:
        _refresh_database_metrics()
    except Exception as exc:
        logger.warning(f"Prometheus database metrics scrape failed: {exc}")
        _SCRAPE_ERRORS.labels(component="database").inc()
    return generate_latest(_REGISTRY)


def reset_metrics_for_testing() -> None:
    """Clear label children for tests that need isolated metrics state."""
    for metric in (
        _HTTP_REQUESTS,
        _HTTP_REQUEST_DURATION,
        _AGENT_RUNS,
        _AGENT_RUNS_LEGACY,
        _AGENT_APPROVALS,
        _AGENT_APPROVALS_LEGACY,
        _INDEXING_TASKS,
        _INDEXING_TASKS_LEGACY,
    ):
        metric.clear()
    _AGENT_TOOL_CALLS.set(0)
    _AGENT_TOOL_CALLS_LEGACY.set(0)
    _AGENT_HANDOFFS.set(0)
    _AGENT_HANDOFFS_LEGACY.set(0)


def _refresh_database_metrics() -> None:
    engine = get_engine()
    with engine.connect() as connection:
        _replace_gauge_labels(
            _AGENT_RUNS,
            ("status",),
            (
                (str(row[0]), int(row[1]))
                for row in connection.execute(
                    text("SELECT status, COUNT(*) AS count FROM agent_runs GROUP BY status")
                )
            ),
        )
        _replace_gauge_labels(
            _AGENT_RUNS_LEGACY,
            ("status",),
            (
                (str(row[0]), int(row[1]))
                for row in connection.execute(
                    text("SELECT status, COUNT(*) AS count FROM agent_runs GROUP BY status")
                )
            ),
        )

        event_counts = {
            str(row[0]): int(row[1])
            for row in connection.execute(
                text("SELECT event_type, COUNT(*) AS count FROM agent_events GROUP BY event_type")
            )
        }
        _AGENT_TOOL_CALLS.set(event_counts.get("tool_call", 0))
        _AGENT_TOOL_CALLS_LEGACY.set(event_counts.get("tool_call", 0))
        _AGENT_APPROVALS.labels(state="required").set(event_counts.get("approval_required", 0))
        _AGENT_APPROVALS.labels(state="resumed").set(event_counts.get("approval_resume", 0))
        _AGENT_APPROVALS_LEGACY.labels(state="required").set(
            event_counts.get("approval_required", 0)
        )
        _AGENT_APPROVALS_LEGACY.labels(state="resumed").set(event_counts.get("approval_resume", 0))
        _AGENT_HANDOFFS.set(event_counts.get("handoff", 0))
        _AGENT_HANDOFFS_LEGACY.set(event_counts.get("handoff", 0))

        _replace_gauge_labels(
            _INDEXING_TASKS,
            ("status",),
            (
                (str(row[0]), int(row[1]))
                for row in connection.execute(
                    text("SELECT status, COUNT(*) AS count FROM indexing_tasks GROUP BY status")
                )
            ),
        )
        _replace_gauge_labels(
            _INDEXING_TASKS_LEGACY,
            ("status",),
            (
                (str(row[0]), int(row[1]))
                for row in connection.execute(
                    text("SELECT status, COUNT(*) AS count FROM indexing_tasks GROUP BY status")
                )
            ),
        )


def _replace_gauge_labels(
    gauge: Gauge,
    label_names: tuple[str, ...],
    samples: Iterable[tuple[str, int]],
) -> None:
    gauge.clear()
    for label_value, value in samples:
        gauge.labels(**{label_names[0]: label_value}).set(value)


def _normalize_path(path: str) -> str:
    return path or "unknown"
