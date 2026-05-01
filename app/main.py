"""FastAPI 应用入口

主应用程序，配置路由、中间件等
"""

from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.api.routes import aiops, chat, file, health, native_agent
from app.config import config
from app.core.container import service_container
from app.core.milvus_client import milvus_manager
from app.infrastructure.tasks import task_dispatcher
from app.platform.persistence import audit_log_repository
from app.security import validate_security_configuration


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时执行
    logger.info("=" * 60)
    logger.info(f"🚀 {config.app_name} v{config.app_version} 启动中...")
    logger.info(f"📝 环境: {'开发' if config.debug else '生产'}")
    logger.info(f"🌐 监听地址: http://{config.host}:{config.port}")
    logger.info(f"📚 API 文档: http://{config.host}:{config.port}/docs")

    logger.info("🔐 正在校验安全配置...")
    validate_security_configuration()
    logger.info("✅ 安全配置校验通过")

    if config.task_dispatcher_mode == "embedded":
        logger.info("🧵 正在启动嵌入式任务调度器...")
        await task_dispatcher.start()
        logger.info("✅ 嵌入式任务调度器启动成功")
    else:
        logger.info("🧵 当前为 detached 模式，请单独启动 app/worker.py")

    # 初始化核心依赖
    logger.info("🔌 正在初始化核心依赖...")
    service_container.initialize_required_services()
    logger.info("✅ 核心依赖初始化成功")

    logger.info("=" * 60)

    yield

    # 关闭时执行
    if task_dispatcher.is_started:
        logger.info("🧵 正在停止任务调度器...")
        await task_dispatcher.shutdown()
    logger.info("🔌 正在关闭 Milvus 连接...")
    milvus_manager.close()
    await service_container.shutdown()
    logger.info(f"👋 {config.app_name} 关闭")


# 创建 FastAPI 应用
app = FastAPI(
    title=config.app_name,
    version=config.app_version,
    description="基于 LangChain 的智能oncall运维系统",
    lifespan=lifespan,
    generate_unique_id_function=lambda route: (
        f"{route.tags[0]}-{route.name}" if route.tags else route.name
    ),
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    allow_credentials="*" not in config.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _write_audit_log(
    request: Request,
    *,
    request_id: str,
    status_code: int,
    error_message: str | None = None,
) -> None:
    principal = getattr(request.state, "principal", None)
    client = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    try:
        audit_log_repository.log_request(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status_code=status_code,
            subject=getattr(principal, "subject", None),
            role=getattr(principal, "role", None),
            client_ip=client,
            user_agent=user_agent,
            error_message=error_message,
        )
    except Exception as exc:
        logger.warning(f"[request_id={request_id}] 审计日志写入失败: {exc}")


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    """为每个请求注入 request_id 并记录基础审计日志。"""
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    request.state.request_id = request_id

    logger.info(f"[request_id={request_id}] {request.method} {request.url.path} - started")
    try:
        response = await call_next(request)
    except Exception as exc:
        _write_audit_log(
            request,
            request_id=request_id,
            status_code=500,
            error_message=str(exc),
        )
        logger.exception(f"[request_id={request_id}] {request.method} {request.url.path} - failed")
        raise

    response.headers["X-Request-ID"] = request_id
    _write_audit_log(
        request,
        request_id=request_id,
        status_code=response.status_code,
    )
    logger.info(
        f"[request_id={request_id}] {request.method} {request.url.path} - completed {response.status_code}"
    )
    return response


# 注册路由
app.include_router(health.router, tags=["健康检查"])
app.include_router(chat.router, prefix="/api", tags=["对话"])
app.include_router(file.router, prefix="/api", tags=["文件管理"])
app.include_router(aiops.router, prefix="/api", tags=["AIOps智能运维"])
app.include_router(native_agent.router, prefix="/api", tags=["Native Agent"])


@app.get("/")
async def root():
    """返回 API 根信息。"""
    return {
        "message": f"Welcome to {config.app_name} API",
        "version": config.app_version,
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app", host=config.host, port=config.port, reload=config.debug, log_level="info"
    )
