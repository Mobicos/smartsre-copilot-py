from __future__ import annotations

from fastapi.testclient import TestClient
from loguru import logger

import app.main as app_main


async def _noop_async() -> None:
    return None


def test_request_context_middleware_echoes_request_id_and_binds_logger(monkeypatch):
    monkeypatch.setattr(app_main, "initialize_services", lambda: None)
    monkeypatch.setattr(app_main, "validate_security_configuration", lambda: None)
    monkeypatch.setattr(app_main, "shutdown_services", _noop_async)
    monkeypatch.setattr(app_main.config, "task_dispatcher_mode", "detached")

    records: list[dict[str, object]] = []
    sink_id = logger.add(lambda message: records.append(message.record), level="INFO")
    try:
        with TestClient(app_main.app) as client:
            response = client.get("/", headers={"X-Request-ID": "request-123"})
    finally:
        logger.remove(sink_id)

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "request-123"
    assert any(record["extra"].get("request_id") == "request-123" for record in records)
