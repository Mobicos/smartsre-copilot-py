"""配置管理模块。

使用 Pydantic Settings 实现类型安全的配置管理。
"""

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"
UPLOADS_DIR = BASE_DIR / "uploads"
LOGS_DIR = BASE_DIR / "logs"

logger = logging.getLogger(__name__)

_DEFAULT_SECRETS = {
    "changethis",
    "changeme",
    "secret",
    "password",
    "your_dashscope_api_key",
    "replace_with_a_secure_key",
}


class Settings(BaseSettings):
    """应用配置"""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_ignore_empty=True,
    )

    # 应用配置
    app_name: str = "SmartSRE Copilot"
    app_version: str = "1.3.0"
    environment: str = "dev"
    debug: bool = False
    # Intentionally bind all interfaces by default for container/server deployments.
    host: str = "0.0.0.0"  # nosec B104
    port: int = 9900
    cors_allowed_origins: str = "*"
    postgres_dsn: str = ""
    app_api_key: str = ""
    api_keys_json: str = ""
    task_dispatcher_mode: str = "embedded"
    task_queue_backend: str = "database"
    task_poll_interval_ms: int = 1000
    task_requeue_timeout_seconds: int = 300
    indexing_task_max_retries: int = 3
    redis_url: str = "redis://localhost:6379/0"
    redis_task_queue_name: str = "smartsre:indexing:queue"

    # DashScope 配置
    dashscope_api_key: str = ""  # 默认空字符串，实际使用需从环境变量加载
    dashscope_model: str = "qwen-max"
    dashscope_embedding_model: str = "text-embedding-v4"  # v4 支持多种维度（默认 1024）

    # Milvus 配置
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_timeout: int = 10000  # 毫秒

    # RAG 配置
    rag_top_k: int = 3
    rag_model: str = "qwen-max"  # 使用快速响应模型，不带扩展思考
    chat_recursion_limit: int = 12
    aiops_recursion_limit: int = 24
    aiops_max_steps: int = 8

    # 文档分块配置
    chunk_max_size: int = 800
    chunk_overlap: int = 100

    # MCP 服务配置
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
        }
        issues: list[str] = []
        for field_name, value in secret_fields.items():
            if value and value.strip().lower() in _DEFAULT_SECRETS:
                issues.append(f"{field_name} is set to a default/placeholder value")

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
        # postgresql://… → postgresql+psycopg://…
        return raw.replace("postgresql://", "postgresql+psycopg://", 1)

    @property
    def is_production(self) -> bool:
        """当前是否为生产环境。"""
        return self.environment.strip().lower() in {"prod", "production"}

    @property
    def cors_origins(self) -> list[str]:
        """解析 CORS 白名单。

        支持:
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
        """获取完整的 MCP 服务器配置"""
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
