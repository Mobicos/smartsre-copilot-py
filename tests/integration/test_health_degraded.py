from __future__ import annotations

from types import SimpleNamespace

from app.api.providers import ServiceHealth


def test_ready_health_payload_marks_configured_services_as_degraded(monkeypatch):
    from app.api.routes import health

    monkeypatch.setattr(health, "db_health_check", lambda: True)
    monkeypatch.setattr(
        health,
        "get_service_health",
        lambda: {
            "embedding": ServiceHealth(status="ready", message="Embedding ready"),
            "vector_store": ServiceHealth(status="ready", message="Vector store ready"),
            "object_storage": ServiceHealth(
                status="configured",
                message="Object storage backend: local",
            ),
            "decision_runtime": ServiceHealth(
                status="configured",
                message="Deterministic decision runtime is configured",
                detail={"provider": "deterministic"},
            ),
            "rag_agent": ServiceHealth(status="ready", message="RAG Agent ready"),
            "aiops": ServiceHealth(status="ready", message="AIOps ready"),
            "checkpoint": ServiceHealth(status="ready", message="Checkpoint ready"),
        },
    )
    monkeypatch.setattr(
        health,
        "get_vector_store_manager",
        lambda: SimpleNamespace(backend_name="milvus", health_check=lambda: True),
    )
    monkeypatch.setattr(health.redis_manager, "health_check", lambda: True)
    monkeypatch.setattr(health, "task_dispatcher", SimpleNamespace(is_started=False))
    monkeypatch.setattr(
        health,
        "agent_resume_dispatcher",
        SimpleNamespace(is_started=False),
    )
    monkeypatch.setattr(
        health.indexing_task_repository,
        "list_tasks_by_status",
        lambda statuses: [],
    )

    status_code, payload = health._build_ready_health_payload()

    assert status_code == 200
    assert payload["message"] == "degraded"
    assert payload["data"]["status"] == "degraded"
    assert "warning" in payload["data"]
    assert "object_storage" in payload["data"]["degraded_components"]
    assert "decision_runtime" in payload["data"]["degraded_components"]
