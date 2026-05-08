"""Health check APIs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse, PlainTextResponse
from loguru import logger

from app.api.providers import get_service_health, get_vector_store_manager
from app.config import config
from app.infrastructure import redis_manager
from app.infrastructure.tasks import agent_resume_dispatcher, task_dispatcher
from app.observability import render_prometheus_metrics
from app.platform.persistence.database import health_check as db_health_check
from app.platform.persistence.repositories.indexing import indexing_task_repository

router = APIRouter()

_DEGRADED_STATUSES = {
    "configured",
    "degraded",
    "external",
    "idle",
    "not_initialized",
}


def _build_ready_health_payload() -> tuple[int, dict[str, Any]]:
    health_data: dict[str, Any] = {
        "service": config.app_name,
        "version": config.app_version,
        "status": "healthy",
    }

    for service_name, health in get_service_health().items():
        health_data[service_name] = {
            "status": health.status,
            "message": health.message,
            **({"detail": health.detail} if health.detail else {}),
        }

    database_healthy = db_health_check()
    health_data["database"] = {
        "status": "connected" if database_healthy else "disconnected",
        "message": "Database connected" if database_healthy else "Database disconnected",
    }

    if config.task_queue_backend == "redis":
        redis_healthy = redis_manager.health_check()
        health_data["redis"] = {
            "status": "connected" if redis_healthy else "disconnected",
            "message": "Redis connected" if redis_healthy else "Redis disconnected",
        }

    health_data["task_dispatcher"] = {
        "status": "running" if task_dispatcher.is_started else "external",
        "message": (
            "Embedded task dispatcher is running"
            if task_dispatcher.is_started
            else f"Task dispatcher mode: {config.task_dispatcher_mode}"
        ),
    }
    health_data["agent_resume_dispatcher"] = {
        "status": "running" if agent_resume_dispatcher.is_started else "idle",
        "queue": config.agent_resume_queue_name,
    }

    try:
        task_counts = {
            status: len(indexing_task_repository.list_tasks_by_status([status]))
            for status in sorted(indexing_task_repository.ALLOWED_TASK_STATUSES)
        }
        active_count = task_counts.get("queued", 0) + task_counts.get("processing", 0)
        health_data["indexing_tasks"] = {
            "status": "active" if active_count else "idle",
            "counts": task_counts,
        }
    except Exception as exc:
        logger.warning(f"Indexing task health summary failed: {exc}")
        health_data["indexing_tasks"] = {
            "status": "error",
            "message": "Indexing task status unavailable",
        }

    try:
        vector_manager = get_vector_store_manager()
        vector_healthy = vector_manager.health_check()
        health_data["vector_backend"] = {
            "backend": vector_manager.backend_name,
            "status": "connected" if vector_healthy else "disconnected",
        }
    except Exception as exc:
        logger.warning(f"Vector backend health check failed: {exc}")
        health_data["vector_backend"] = {
            "backend": config.vector_store_backend,
            "status": "error",
            "message": str(exc),
        }

    degraded_components: list[str] = [
        service_name
        for service_name, health in get_service_health().items()
        if health.status in _DEGRADED_STATUSES
    ]
    overall_status = "healthy"
    status_code = 200

    if health_data["vector_backend"]["status"] != "connected":
        overall_status = "unhealthy"
        status_code = 503
        health_data["error"] = "Vector backend unavailable"

    if health_data["embedding"]["status"] != "ready":
        overall_status = "unhealthy"
        status_code = 503
        health_data["error"] = "Embedding service unavailable"

    if health_data["vector_store"]["status"] != "ready":
        overall_status = "unhealthy"
        status_code = 503
        health_data["error"] = "Vector store unavailable"

    if health_data["database"]["status"] != "connected":
        overall_status = "unhealthy"
        status_code = 503
        health_data["error"] = "Database unavailable"

    if config.task_queue_backend == "redis" and health_data["redis"]["status"] != "connected":
        overall_status = "unhealthy"
        status_code = 503
        health_data["error"] = "Redis unavailable"

    if overall_status == "healthy" and degraded_components:
        overall_status = "degraded"
        health_data["warning"] = "Some runtime services are configured but not yet initialized"

    if degraded_components:
        health_data["degraded_components"] = degraded_components

    health_data["status"] = overall_status
    return status_code, {
        "code": status_code,
        "message": overall_status,
        "data": health_data,
    }


@router.get("/health/live")
async def live_health_check():
    return JSONResponse(
        status_code=200,
        content={
            "code": 200,
            "message": "alive",
            "data": {
                "service": config.app_name,
                "version": config.app_version,
                "status": "alive",
            },
        },
    )


@router.get("/health/ready")
async def ready_health_check():
    status_code, payload = _build_ready_health_payload()
    return JSONResponse(status_code=status_code, content=payload)


@router.get("/health")
async def health_check():
    status_code, payload = _build_ready_health_payload()
    return JSONResponse(status_code=status_code, content=payload)


@router.get("/metrics", include_in_schema=False)
async def prometheus_metrics():
    return PlainTextResponse(
        render_prometheus_metrics(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
