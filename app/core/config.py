"""Application settings as a pure dataclass for dependency injection.

This module replaces direct imports of the global `config` singleton (from app.config)
with a typed `AppSettings` interface. Components receive `AppSettings` via constructor
injection, making them testable without patching environment variables.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class McpServerConfig:
    """Configuration for one MCP server."""

    transport: str
    url: str


@dataclass(frozen=True)
class AppSettings:
    """All configuration values as an immutable dataclass.

    Components should receive this via constructor injection rather than
    importing the global `config` singleton from `app.config`.

    Usage::

        class MyService:
            def __init__(self, settings: AppSettings) -> None:
                self._settings = settings
                self._timeout = settings.llm_request_timeout_seconds

        # In production: AppSettings.from_env()
        # In tests: AppSettings.defaults() or AppSettings(...)
    """

    # Application
    app_name: str = "SmartSRE Copilot"
    app_version: str = "0.1.0.dev0"
    environment: str = "dev"

    # Auth
    app_api_key: str = ""
    api_keys_json: str = ""
    cors_allowed_origins: str = "*"

    # Database
    postgres_dsn: str = ""
    postgres_connect_timeout_seconds: int = 5

    # Task queue
    task_dispatcher_mode: str = "embedded"
    task_queue_backend: str = "database"
    task_poll_interval_ms: int = 1000
    task_requeue_timeout_seconds: int = 300
    indexing_task_max_retries: int = 3

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_password: str = ""
    redis_task_queue_name: str = "smartsre:indexing:queue"

    # Rate limiting
    rate_limit_enabled: bool = True
    rate_limit_requests_per_minute: int = 120
    rate_limit_streams_per_minute: int = 20
    rate_limit_burst: int = 20

    # Object storage
    object_storage_backend: str = "local"
    object_storage_local_path: str = "uploads"
    object_storage_local_cache_path: str = "uploads"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket: str = "smartsre-knowledge"
    minio_secure: bool = False

    # LLM / DashScope
    dashscope_api_key: str = ""
    dashscope_model: str = "qwen-max"
    dashscope_embedding_model: str = "text-embedding-v4"
    llm_request_timeout_seconds: float = 60.0
    llm_max_retries: int = 3
    llm_retry_delay_seconds: float = 1.0

    # Vector store
    vector_store_backend: str = "pgvector"
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    pgvector_collection_name: str = "biz"
    pgvector_embedding_dimensions: int = 1024
    milvus_timeout: int = 10000

    # RAG / Chat
    rag_top_k: int = 3
    rag_score_threshold: float = 0.3
    rag_model: str = "qwen-max"
    chat_recursion_limit: int = 12

    # AIOps
    aiops_recursion_limit: int = 24
    aiops_max_steps: int = 8

    # Agent
    agent_decision_provider: str = "deterministic"
    agent_max_steps: int = 5
    agent_step_timeout_seconds: float = 30.0
    agent_total_timeout_seconds: float = 120.0
    agent_approval_timeout_seconds: int = 3600
    agent_resume_queue_name: str = "smartsre:agent:resume:queue"

    # Document chunking
    chunk_max_size: int = 800
    chunk_overlap: int = 100

    # MCP servers
    mcp_cls_transport: str = "streamable-http"
    mcp_cls_url: str = "http://localhost:8003/mcp"
    mcp_monitor_transport: str = "streamable-http"
    mcp_monitor_url: str = "http://localhost:8004/mcp"
    mcp_tools_load_timeout_seconds: float = 8.0

    @property
    def is_production(self) -> bool:
        """Return whether the current environment is production."""
        return self.environment.strip().lower() in {"prod", "production"}

    def mcp_servers(self) -> dict[str, McpServerConfig]:
        """Return configured MCP servers as a dict keyed by server name."""
        return {
            "cls": McpServerConfig(
                transport=self.mcp_cls_transport,
                url=self.mcp_cls_url,
            ),
            "monitor": McpServerConfig(
                transport=self.mcp_monitor_transport,
                url=self.mcp_monitor_url,
            ),
        }

    def cors_origins(self) -> list[str]:
        """Parse the configured CORS allowlist.

        Supports:
        - `*`
        - `https://a.com,https://b.com`
        - `["https://a.com", "https://b.com"]`
        """
        raw_value = self.cors_allowed_origins.strip()
        if not raw_value:
            return []
        if raw_value == "*":
            return ["*"]
        if raw_value.startswith("["):
            import json

            try:
                parsed = json.loads(raw_value)
                if isinstance(parsed, list):
                    return [str(origin).strip() for origin in parsed if str(origin).strip()]
            except json.JSONDecodeError:
                pass
        return [origin.strip() for origin in raw_value.split(",") if origin.strip()]

    @classmethod
    def from_env(cls) -> AppSettings:
        """Build AppSettings from the global config singleton (app.config).

        This is the production entry point. In tests, prefer `defaults()` or
        constructing `AppSettings` directly with specific values.
        """
        from app.config import config

        return cls(
            app_name=config.app_name,
            app_version=config.app_version,
            environment=config.environment,
            app_api_key=config.app_api_key,
            api_keys_json=config.api_keys_json,
            cors_allowed_origins=config.cors_allowed_origins,
            postgres_dsn=config.postgres_dsn,
            postgres_connect_timeout_seconds=config.postgres_connect_timeout_seconds,
            task_dispatcher_mode=config.task_dispatcher_mode,
            task_queue_backend=config.task_queue_backend,
            task_poll_interval_ms=config.task_poll_interval_ms,
            task_requeue_timeout_seconds=config.task_requeue_timeout_seconds,
            indexing_task_max_retries=config.indexing_task_max_retries,
            redis_url=config.redis_url,
            redis_password=config.redis_password,
            redis_task_queue_name=config.redis_task_queue_name,
            rate_limit_enabled=config.rate_limit_enabled,
            rate_limit_requests_per_minute=config.rate_limit_requests_per_minute,
            rate_limit_streams_per_minute=config.rate_limit_streams_per_minute,
            rate_limit_burst=config.rate_limit_burst,
            object_storage_backend=config.object_storage_backend,
            object_storage_local_path=config.object_storage_local_path,
            object_storage_local_cache_path=config.object_storage_local_cache_path,
            minio_endpoint=config.minio_endpoint,
            minio_access_key=config.minio_access_key,
            minio_secret_key=config.minio_secret_key,
            minio_bucket=config.minio_bucket,
            minio_secure=config.minio_secure,
            dashscope_api_key=config.dashscope_api_key,
            dashscope_model=config.dashscope_model,
            dashscope_embedding_model=config.dashscope_embedding_model,
            llm_request_timeout_seconds=config.llm_request_timeout_seconds,
            llm_max_retries=config.llm_max_retries,
            llm_retry_delay_seconds=config.llm_retry_delay_seconds,
            vector_store_backend=config.vector_store_backend,
            milvus_host=config.milvus_host,
            milvus_port=config.milvus_port,
            pgvector_collection_name=config.pgvector_collection_name,
            pgvector_embedding_dimensions=config.pgvector_embedding_dimensions,
            milvus_timeout=config.milvus_timeout,
            rag_top_k=config.rag_top_k,
            rag_score_threshold=config.rag_score_threshold,
            rag_model=config.rag_model,
            chat_recursion_limit=config.chat_recursion_limit,
            aiops_recursion_limit=config.aiops_recursion_limit,
            aiops_max_steps=config.aiops_max_steps,
            agent_decision_provider=config.agent_decision_provider,
            agent_max_steps=config.agent_max_steps,
            agent_step_timeout_seconds=config.agent_step_timeout_seconds,
            agent_total_timeout_seconds=config.agent_total_timeout_seconds,
            agent_approval_timeout_seconds=config.agent_approval_timeout_seconds,
            agent_resume_queue_name=config.agent_resume_queue_name,
            chunk_max_size=config.chunk_max_size,
            chunk_overlap=config.chunk_overlap,
            mcp_cls_transport=config.mcp_cls_transport,
            mcp_cls_url=config.mcp_cls_url,
            mcp_monitor_transport=config.mcp_monitor_transport,
            mcp_monitor_url=config.mcp_monitor_url,
            mcp_tools_load_timeout_seconds=config.mcp_tools_load_timeout_seconds,
        )

    @classmethod
    def defaults(cls) -> AppSettings:
        """Return safe defaults suitable for testing.

        All sensitive fields are empty strings; no real service connections are made.
        """
        return cls()
