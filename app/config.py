"""Application configuration."""

import json
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"
UPLOADS_DIR = BASE_DIR / "uploads"
LOGS_DIR = BASE_DIR / "logs"

_DEFAULT_SECRETS = {
    "changethis",
    "changeme",
    "minioadmin",
    "secret",
    "password",
    "smartsre",
    "your_dashscope_api_key",
    "replace_with_a_secure_key",
    "<replace-with-strong-redis-password>",
    "replace-with-strong-redis-password",
    "dev-only-minio-user",
    "dev-only-minio-password",
    "dev-only-postgres-password",
}

_DEFAULT_DSN_FRAGMENTS = (
    "postgresql://smartsre:smartsre@",
    "postgresql+psycopg://smartsre:smartsre@",
    "dev-only-postgres-password@",
)


class Settings(BaseSettings):
    """Typed application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_ignore_empty=True,
    )

    # Application settings
    app_name: str = "SmartSRE Copilot"
    app_version: str = "0.1.0.dev0"
    environment: str = "dev"
    debug: bool = False
    # Intentionally bind all interfaces by default for container/server deployments.
    host: str = "0.0.0.0"  # nosec B104
    port: int = 9900
    cors_allowed_origins: str = "*"
    postgres_dsn: str = ""
    postgres_connect_timeout_seconds: int = 5
    app_api_key: str = ""
    api_keys_json: str = ""
    task_dispatcher_mode: str = "embedded"
    task_queue_backend: str = "database"
    task_poll_interval_ms: int = 1000
    task_requeue_timeout_seconds: int = 300
    indexing_task_max_retries: int = 3
    redis_url: str = "redis://localhost:6379/0"
    redis_password: str = ""
    redis_task_queue_name: str = "smartsre:indexing:queue"
    rate_limit_enabled: bool = True
    rate_limit_requests_per_minute: int = 120
    rate_limit_streams_per_minute: int = 20
    rate_limit_burst: int = 20
    object_storage_backend: str = "local"
    object_storage_local_path: str = str(UPLOADS_DIR)
    object_storage_local_cache_path: str = str(UPLOADS_DIR)
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket: str = "smartsre-knowledge"
    minio_secure: bool = False

    # DashScope settings
    dashscope_api_key: str = ""
    dashscope_model: str = "qwen-max"
    dashscope_embedding_model: str = "text-embedding-v4"

    # Milvus settings
    llm_request_timeout_seconds: float = 60.0
    llm_max_retries: int = 3
    llm_retry_delay_seconds: float = 1.0

    vector_store_backend: str = "pgvector"
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    pgvector_collection_name: str = "biz"
    pgvector_embedding_dimensions: int = 1024
    milvus_timeout: int = 10000

    # RAG settings
    rag_top_k: int = 3
    rag_model: str = "qwen-max"
    chat_recursion_limit: int = 12
    aiops_recursion_limit: int = 24
    aiops_max_steps: int = 8
    agent_decision_provider: str = "deterministic"
    agent_max_steps: int = 5
    agent_step_timeout_seconds: float = 30.0
    agent_total_timeout_seconds: float = 120.0
    agent_approval_timeout_seconds: int = 3600
    agent_resume_queue_name: str = "smartsre:agent:resume:queue"

    # Document chunking settings
    chunk_max_size: int = 800
    chunk_overlap: int = 100

    # MCP server settings
    mcp_cls_transport: str = "streamable-http"
    mcp_cls_url: str = "http://localhost:8003/mcp"
    mcp_monitor_transport: str = "streamable-http"
    mcp_monitor_url: str = "http://localhost:8004/mcp"
    mcp_tools_load_timeout_seconds: float = 8.0

    @model_validator(mode="after")
    def _check_default_secrets(self) -> "Settings":
        """Warn or error when secrets still contain placeholder values."""
        secret_fields = {
            "app_api_key": self.app_api_key,
            "postgres_dsn": self.postgres_dsn,
            "dashscope_api_key": self.dashscope_api_key,
            "minio_access_key": self.minio_access_key,
            "minio_secret_key": self.minio_secret_key,
            "redis_password": self.redis_password,
        }
        issues: list[str] = []
        for field_name, value in secret_fields.items():
            if value and value.strip().lower() in _DEFAULT_SECRETS:
                issues.append(f"{field_name} is set to a default/placeholder value")
        if self.postgres_dsn and any(
            fragment in self.postgres_dsn.strip().lower() for fragment in _DEFAULT_DSN_FRAGMENTS
        ):
            issues.append("postgres_dsn contains the default smartsre database password")

        if not issues:
            return self

        message = f"Security configuration issues: {'; '.join(issues)}"
        if self.is_production:
            raise ValueError(message)
        logger.warning(message)
        return self

    @property
    def sqlalchemy_database_uri(self) -> str:
        """Return a SQLAlchemy-compatible DSN (psycopg3 driver)."""
        raw = self.postgres_dsn
        if not raw:
            return ""
        if raw.startswith("postgresql+"):
            return raw
        # Convert postgresql:// to postgresql+psycopg:// for SQLAlchemy.
        return raw.replace("postgresql://", "postgresql+psycopg://", 1)

    @property
    def is_production(self) -> bool:
        """Return whether the current environment is production."""
        return self.environment.strip().lower() in {"prod", "production"}

    @property
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
            try:
                parsed = json.loads(raw_value)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                return [str(origin).strip() for origin in parsed if str(origin).strip()]

        return [origin.strip() for origin in raw_value.split(",") if origin.strip()]

    @property
    def mcp_servers(self) -> dict[str, dict[str, Any]]:
        """Return configured MCP servers."""
        return {
            "cls": {
                "transport": self.mcp_cls_transport,
                "url": self.mcp_cls_url,
            },
            "monitor": {
                "transport": self.mcp_monitor_transport,
                "url": self.mcp_monitor_url,
            },
        }


# 全局配置实例
config = Settings()
