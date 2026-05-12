"""FastAPI application entrypoint."""

import os
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from loguru import logger

from app.api.main import api_router
from app.api.providers import initialize_services, shutdown_services
from app.api.responses import error_response
from app.api.routes import health
from app.config import config
from app.core.exceptions import AppException
from app.infrastructure.tasks import agent_resume_dispatcher, task_dispatcher
from app.observability import observe_http_request
from app.platform.persistence import audit_log_repository
from app.security import validate_security_configuration
from app.utils.logger import setup_logger

setup_logger()


def _init_otel() -> None:
    """Initialize OpenTelemetry instrumentation if OTEL_ENABLED is set."""
    if os.getenv("OTEL_ENABLED", "").strip().lower() not in ("1", "true", "yes"):
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
        resource = Resource.create({SERVICE_NAME: "smartsre-copilot"})
        provider = TracerProvider(resource=resource)
        processor = BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint))
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)
        logger.info(f"OpenTelemetry initialized, exporter: {endpoint}")
    except Exception as exc:
        logger.warning(f"OpenTelemetry initialization failed (non-fatal): {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown."""
    logger.info("=" * 60)
    logger.info(f"Starting {config.app_name} v{config.app_version}")
    logger.info(f"Environment: {'debug' if config.debug else 'production'}")
    logger.info(f"Base URL: http://{config.host}:{config.port}")
    logger.info(f"Docs: http://{config.host}:{config.port}/docs")

    _init_otel()

    logger.info("Validating security configuration...")
    validate_security_configuration()
    logger.info("Security configuration validated")

    if config.task_dispatcher_mode == "embedded":
        logger.info("Starting embedded task dispatchers...")
        await task_dispatcher.start()  # type: ignore[attr-defined]
        await agent_resume_dispatcher.start()  # type: ignore[attr-defined]
        logger.info("Embedded task dispatchers started")
    else:
        logger.info("Using detached task dispatcher mode via app/worker.py")

    logger.info("Initializing application services...")
    initialize_services()
    logger.info("Application services initialized")

    logger.info("=" * 60)

    yield

    if task_dispatcher.is_started:  # type: ignore[attr-defined]
        logger.info("Shutting down embedded task dispatchers...")
        await agent_resume_dispatcher.shutdown()  # type: ignore[attr-defined]
        await task_dispatcher.shutdown()  # type: ignore[attr-defined]
    logger.info("Shutting down application services...")
    await shutdown_services()
    logger.info(f"Stopped {config.app_name}")


def _generate_operation_id(route: APIRoute) -> str:
    """Generate stable OpenAPI operation IDs across legacy and versioned prefixes."""
    tag = str(route.tags[0]) if route.tags else "Default"
    method = sorted(route.methods or {"GET"})[0].lower()
    normalized_path = (
        route.path_format.strip("/")
        .replace("/", "_")
        .replace("{", "")
        .replace("}", "")
        .replace("-", "_")
    )
    return f"{tag}-{route.name}-{method}-{normalized_path or 'root'}"


app = FastAPI(
    title=config.app_name,
    version=config.app_version,
    description=(
        "AI-powered SRE assistant with knowledge-grounded chat, "
        "AIOps diagnosis, and native agent workbench"
    ),
    lifespan=lifespan,
    generate_unique_id_function=_generate_operation_id,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    allow_credentials="*" not in config.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

if os.getenv("OTEL_ENABLED", "").strip().lower() in ("1", "true", "yes"):
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
    except ImportError:
        pass


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    request_id = getattr(request.state, "request_id", None)
    logger.warning(f"handled application error {exc.code}: {exc.message}")
    return error_response(
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        request_id=request_id,
        details=exc.details,
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    request_id = getattr(request.state, "request_id", None)
    detail = exc.detail if isinstance(exc.detail, str) else "request_error"
    return error_response(
        status_code=exc.status_code,
        code=str(detail),
        message=str(detail),
        request_id=request_id,
    )


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):
    request_id = getattr(request.state, "request_id", None)
    return error_response(
        status_code=422,
        code="validation_error",
        message="Request validation failed",
        request_id=request_id,
        details={"errors": exc.errors()},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", None)
    logger.exception(f"unhandled application error: {exc}")
    return error_response(
        status_code=500,
        code="internal_error",
        message="Internal server error",
        request_id=request_id,
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
        logger.warning(f"audit log write failed: {exc}")


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    """Attach a request ID to loguru context and audit output."""
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    request.state.request_id = request_id
    started_at = perf_counter()

    with logger.contextualize(request_id=request_id):
        logger.info(f"{request.method} {request.url.path} - started")
        try:
            response = await call_next(request)
        except Exception as exc:
            duration_seconds = perf_counter() - started_at
            route = request.scope.get("route")
            route_path = str(getattr(route, "path", request.url.path))
            observe_http_request(
                method=request.method,
                path=route_path,
                status_code=500,
                duration_seconds=duration_seconds,
            )
            _write_audit_log(
                request,
                request_id=request_id,
                status_code=500,
                error_message=str(exc),
            )
            logger.exception(f"{request.method} {request.url.path} - failed")
            raise

        response.headers["X-Request-ID"] = request_id
        duration_seconds = perf_counter() - started_at
        route = request.scope.get("route")
        route_path = str(getattr(route, "path", request.url.path))
        observe_http_request(
            method=request.method,
            path=route_path,
            status_code=response.status_code,
            duration_seconds=duration_seconds,
        )
        _write_audit_log(
            request,
            request_id=request_id,
            status_code=response.status_code,
        )
        logger.info(f"{request.method} {request.url.path} - completed {response.status_code}")
        return response


app.include_router(health.router, tags=["Health"])
app.include_router(api_router, prefix="/api/v1")
app.include_router(api_router, prefix="/api", include_in_schema=False)  # backward compatibility


@app.get("/")
async def root():
    """Basic API root endpoint."""
    return {
        "message": f"Welcome to {config.app_name} API",
        "version": config.app_version,
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=config.host,
        port=config.port,
        reload=config.debug,
        log_level="info",
    )
