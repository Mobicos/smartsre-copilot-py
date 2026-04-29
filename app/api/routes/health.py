"""健康检查接口。"""

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from loguru import logger

from app.config import config
from app.core.container import service_container
from app.core.milvus_client import milvus_manager
from app.infrastructure import redis_manager
from app.infrastructure.tasks import task_dispatcher
from app.persistence import database_manager

router = APIRouter()


def _build_ready_health_payload() -> tuple[int, dict[str, Any]]:
    """构造 readiness 响应载荷。"""
    health_data: dict[str, Any] = {  # pyright: ignore[reportExplicitAny]
        "service": config.app_name,
        "version": config.app_version,
        "status": "healthy",
    }

    for service_name, health in service_container.get_service_health().items():
        health_data[service_name] = {
            "status": health.status,
            "message": health.message,
        }

    database_healthy = database_manager.health_check()
    health_data["database"] = {
        "status": "connected" if database_healthy else "disconnected",
        "message": "数据库连接正常" if database_healthy else "数据库连接异常",
    }
    if config.task_queue_backend == "redis":
        redis_healthy = redis_manager.health_check()
        health_data["redis"] = {
            "status": "connected" if redis_healthy else "disconnected",
            "message": "Redis 连接正常" if redis_healthy else "Redis 连接异常",
        }
    health_data["task_dispatcher"] = {
        "status": "running" if task_dispatcher.is_started else "external",
        "message": (
            "嵌入式任务调度器运行中"
            if task_dispatcher.is_started
            else f"任务调度模式: {config.task_dispatcher_mode}"
        ),
    }

    try:
        milvus_healthy = milvus_manager.health_check()
        milvus_status: str = "connected" if milvus_healthy else "disconnected"
        milvus_message: str = "Milvus 连接正常" if milvus_healthy else "Milvus 连接异常"
        health_data["milvus"] = {"status": milvus_status, "message": milvus_message}
    except Exception as e:
        logger.warning(f"Milvus 健康检查失败: {e}")
        health_data["milvus"] = {"status": "error", "message": f"Milvus 检查失败: {str(e)}"}

    # 判断整体健康状态
    overall_status = "healthy"
    status_code = 200

    # 如果 Milvus 不可用，服务不可用
    if health_data["milvus"]["status"] != "connected":
        overall_status = "unhealthy"
        status_code = 503
        health_data["error"] = "数据库不可用"

    if health_data["embedding"]["status"] != "ready":
        overall_status = "unhealthy"
        status_code = 503
        health_data["error"] = "Embedding 服务未就绪"

    if health_data["vector_store"]["status"] != "ready":
        overall_status = "unhealthy"
        status_code = 503
        health_data["error"] = "VectorStore 未就绪"

    if health_data["database"]["status"] != "connected":
        overall_status = "unhealthy"
        status_code = 503
        health_data["error"] = "数据库不可用"

    if config.task_queue_backend == "redis" and health_data["redis"]["status"] != "connected":
        overall_status = "unhealthy"
        status_code = 503
        health_data["error"] = "Redis 不可用"

    health_data["status"] = overall_status
    return status_code, {
        "code": status_code,
        "message": "服务运行正常" if overall_status == "healthy" else "服务不可用",
        "data": health_data,
    }


@router.get("/health/live")
async def live_health_check():
    """进程存活检查。"""
    return JSONResponse(
        status_code=200,
        content={
            "code": 200,
            "message": "服务存活",
            "data": {
                "service": config.app_name,
                "version": config.app_version,
                "status": "alive",
            },
        },
    )


@router.get("/health/ready")
async def ready_health_check():
    """服务就绪检查。"""
    status_code, payload = _build_ready_health_payload()
    return JSONResponse(status_code=status_code, content=payload)


@router.get("/health")
async def health_check():
    """兼容旧路径的健康检查接口。"""
    status_code, payload = _build_ready_health_payload()
    return JSONResponse(status_code=status_code, content=payload)
