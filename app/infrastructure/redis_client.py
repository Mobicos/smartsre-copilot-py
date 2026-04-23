"""Redis client management utilities."""

from __future__ import annotations

import json
from typing import Any, TypeAlias, cast

from loguru import logger

from app.config import config

try:
    from redis import Redis
    from redis.exceptions import RedisError as BaseRedisError
except Exception:  # pragma: no cover - redis may be absent in some environments
    Redis = None
    BaseRedisError = Exception

RedisError: TypeAlias = BaseRedisError


class RedisManager:
    """Simple Redis connection wrapper for queue operations."""

    def __init__(self, redis_url: str) -> None:
        self.redis_url = redis_url
        self._client: Redis | None = None

    @property
    def is_initialized(self) -> bool:
        return self._client is not None

    def initialize(self) -> None:
        if self._client is not None:
            return
        if Redis is None:
            raise RuntimeError("Redis support requires the optional 'redis' dependency")

        self._client = Redis.from_url(self.redis_url, decode_responses=True)
        self._client.ping()
        logger.info(f"Redis initialized: {self.redis_url}")

    def health_check(self) -> bool:
        try:
            self.initialize()
            assert self._client is not None
            return bool(self._client.ping())
        except Exception as exc:
            logger.error(f"Redis health check failed: {exc}")
            return False

    def enqueue_json(self, queue_name: str, payload: dict[str, Any]) -> None:
        self.initialize()
        assert self._client is not None
        self._client.rpush(queue_name, json.dumps(payload, ensure_ascii=False))

    def dequeue_json(self, queue_name: str, timeout_seconds: int) -> dict[str, Any] | None:
        self.initialize()
        assert self._client is not None
        result = self._client.blpop(queue_name, timeout=timeout_seconds)
        if result is None:
            return None

        _, raw_payload = result
        payload = json.loads(raw_payload)
        if not isinstance(payload, dict):
            logger.warning(f"Redis queue '{queue_name}' returned a non-object payload")
            return None
        return cast(dict[str, Any], payload)


redis_manager = RedisManager(config.redis_url)
