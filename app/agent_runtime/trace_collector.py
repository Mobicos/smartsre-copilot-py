"""OpenTelemetry tracing helpers for Native Agent runtime boundaries."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from typing import Any


class TraceCollector:
    """Create optional spans without making tracing a hard runtime dependency."""

    def __init__(self, tracer_name: str = "smartsre.agent_runtime") -> None:
        self._tracer_name = tracer_name

    @contextmanager
    def span(self, name: str, attributes: dict[str, Any] | None = None) -> Iterator[None]:
        try:
            from opentelemetry import trace
        except Exception:
            with nullcontext():
                yield
            return

        with trace.get_tracer(self._tracer_name).start_as_current_span(name) as span:
            for key, value in (attributes or {}).items():
                span.set_attribute(key, value)
            yield
