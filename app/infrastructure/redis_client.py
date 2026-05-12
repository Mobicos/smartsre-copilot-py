"""Redis client management utilities."""

from __future__ import annotations

import json
from typing import Any, cast
from urllib.parse import quote, urlsplit, urlunsplit

from loguru import logger

from app.core.config import AppSettings

_RedisClient: Any = None
_RedisError: Any = Exception

try:
    from redis import Redis as _ImportedRedisClient
    from redis.exceptions import RedisError as _ImportedRedisError

    _RedisClient = _ImportedRedisClient
    _RedisError = _ImportedRedisError
except Exception:  # pragma: no cover - redis may be absent in some environments

    class _FallbackRedisError(Exception):
        """Fallback Redis error when redis is not installed."""

    _RedisError = _FallbackRedisError


RedisClient: Any = _RedisClient
RedisError = _RedisError


class RedisManager:
    """Simple Redis connection wrapper for queue operations."""

    def __init__(self, redis_url: str, settings: AppSettings) -> None:
        self.redis_url = redis_url
        self._settings = settings
        self._client: Any | None = None

    @property
    def is_initialized(self) -> bool:
        return self._client is not None

    def initialize(self) -> None:
        if self._client is not None:
            return
        self._connect()

    def _connect(self) -> None:
        if RedisClient is None:
            raise RuntimeError("Redis support requires the optional 'redis' dependency")

        redis_url = _redis_url_with_configured_password(self.redis_url, self._settings)
        self._client = RedisClient.from_url(redis_url, decode_responses=True)
        self._client.ping()
        logger.info("Redis initialized")

    def _ensure_connection(self) -> None:
        try:
            self.initialize()
            assert self._client is not None
            self._client.ping()
        except RedisError as exc:
            logger.warning(f"Redis connection unhealthy, reconnecting: {exc}")
            self._client = None
            self._connect()

    def health_check(self) -> bool:
        try:
            self._ensure_connection()
            return True
        except Exception as exc:
            logger.error(f"Redis health check failed: {exc}")
            return False

    def enqueue_json(self, queue_name: str, payload: dict[str, Any]) -> None:
        self._ensure_connection()
        assert self._client is not None
        raw_payload = json.dumps(payload, ensure_ascii=False)
        try:
            self._client.rpush(queue_name, raw_payload)
        except RedisError as exc:
            logger.warning(f"Redis enqueue failed, reconnecting once: {exc}")
            self._client = None
            self._connect()
            assert self._client is not None
            self._client.rpush(queue_name, raw_payload)

    def dequeue_json(self, queue_name: str, timeout_seconds: int) -> dict[str, Any] | None:
        self._ensure_connection()
        assert self._client is not None
        try:
            result = cast(
                tuple[Any, str] | None, self._client.blpop(queue_name, timeout=timeout_seconds)
            )
        except RedisError as exc:
            logger.warning(f"Redis dequeue failed, reconnecting once: {exc}")
            self._client = None
            self._connect()
            assert self._client is not None
            result = cast(
                tuple[Any, str] | None, self._client.blpop(queue_name, timeout=timeout_seconds)
            )
        if result is None:
            return None

        _, raw_payload = result
        payload = json.loads(raw_payload)
        if not isinstance(payload, dict):
            logger.warning(f"Redis queue '{queue_name}' returned a non-object payload")
            return None
        return cast(dict[str, Any], payload)


def _redis_url_with_configured_password(redis_url: str, settings: AppSettings) -> str:
    if not settings.redis_password.strip():
        return redis_url
    parts = urlsplit(redis_url)
    if "@" in parts.netloc:
        return redis_url
    password = quote(settings.redis_password, safe="")
    netloc = f":{password}@{parts.netloc}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


# Lazy-initialized singleton. Replaces the old module-level `redis_manager = RedisManager(...)`.
_redis_manager_instance: RedisManager | None = None
_redis_settings: AppSettings | None = None


def _get_redis_manager() -> RedisManager:
    """Return the lazily-initialized global RedisManager instance."""
    global _redis_manager_instance, _redis_settings
    if _redis_manager_instance is None:
        settings = _redis_settings if _redis_settings is not None else AppSettings.from_env()
        _redis_manager_instance = RedisManager(settings.redis_url, settings=settings)
    return _redis_manager_instance


def _configure_redis_manager(settings: AppSettings) -> None:
    """Update the global redis manager settings (for testing / reconfiguration)."""
    global _redis_manager_instance, _redis_settings
    _redis_settings = settings
    _redis_manager_instance = None


def __getattr__(name: str) -> RedisManager:
    """Support `from app.infrastructure.redis_client import redis_manager`."""
    if name == "redis_manager":
        return _get_redis_manager()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
