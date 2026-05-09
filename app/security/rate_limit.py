"""In-process rate limiting for high-cost API paths."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from time import monotonic
from typing import cast

from fastapi import Header, HTTPException, Request, status

from app.config import config
from app.security.auth import Principal, require_capability


@dataclass(frozen=True)
class RateLimitPolicy:
    """Token bucket policy for a protected endpoint class."""

    requests_per_minute: int
    burst: int

    @property
    def refill_per_second(self) -> float:
        return max(self.requests_per_minute, 1) / 60.0


@dataclass
class _Bucket:
    tokens: float
    updated_at: float


class RateLimiter:
    """Small process-local token bucket limiter keyed by principal or client IP."""

    def __init__(self) -> None:
        self._buckets: dict[str, _Bucket] = {}
        self._lock = Lock()

    def allow(self, key: str, policy: RateLimitPolicy) -> bool:
        now = monotonic()
        capacity = max(policy.burst, 1)
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                self._buckets[key] = _Bucket(tokens=capacity - 1, updated_at=now)
                return True

            elapsed = max(now - bucket.updated_at, 0.0)
            bucket.tokens = min(capacity, bucket.tokens + elapsed * policy.refill_per_second)
            bucket.updated_at = now
            if bucket.tokens < 1:
                return False
            bucket.tokens -= 1
            return True

    def reset_for_testing(self) -> None:
        with self._lock:
            self._buckets.clear()


rate_limiter = RateLimiter()


def require_stream_rate_limit(capability: str):
    """Return a dependency that authenticates and rate-limits high-cost streams."""
    capability_dependency = require_capability(capability)

    async def dependency(
        request: Request,
        x_api_key: str | None = Header(default=None),
    ) -> Principal:
        principal = cast(Principal, await capability_dependency(request, x_api_key))
        if not _rate_limit_enabled():
            return principal

        policy = RateLimitPolicy(
            requests_per_minute=config.rate_limit_streams_per_minute,
            burst=config.rate_limit_burst,
        )
        key = _rate_limit_key(request, principal, scope="stream")
        if not rate_limiter.allow(key, policy):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="rate_limit_exceeded",
            )
        return principal

    return dependency


def _rate_limit_enabled() -> bool:
    return config.rate_limit_enabled or config.is_production


def _rate_limit_key(request: Request, principal: Principal, *, scope: str) -> str:
    if principal.subject and principal.subject != "local-dev":
        return f"{scope}:principal:{principal.subject}"
    client = request.client.host if request.client else "unknown"
    return f"{scope}:ip:{client}"
