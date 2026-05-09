"""Authentication and capability checks."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache

from fastapi import Header, HTTPException, Request, status
from loguru import logger

from app.config import config

ROLE_CAPABILITIES = {
    "viewer": {"chat:read", "knowledge:read"},
    "operator": {"chat:use", "chat:read", "knowledge:read", "aiops:run"},
    "knowledge_admin": {"chat:use", "chat:read", "knowledge:read", "knowledge:write"},
    "admin": {"*"},
}


@dataclass(frozen=True)
class Principal:
    """Authenticated principal attached to a request."""

    role: str
    subject: str


def is_auth_configured() -> bool:
    """Return whether API-key authentication is configured."""
    return bool(config.app_api_key or config.api_keys_json)


@lru_cache(maxsize=1)
def load_api_key_roles() -> dict[str, str]:
    """Load API key to role mappings from configuration."""
    mapping: dict[str, str] = {}
    if config.api_keys_json:
        try:
            raw_mapping = json.loads(config.api_keys_json)
            if isinstance(raw_mapping, dict):
                for key, value in raw_mapping.items():
                    role = str(value)
                    if role not in ROLE_CAPABILITIES:
                        logger.warning(f"Ignoring API key with unknown role: {role}")
                        continue
                    mapping[str(key)] = role
            else:
                logger.warning("API_KEYS_JSON must be a JSON object of api_key to role")
        except json.JSONDecodeError as exc:
            logger.warning(f"API_KEYS_JSON is not valid JSON: {exc}")

    if config.app_api_key:
        mapping.setdefault(config.app_api_key, "admin")

    return mapping


@lru_cache(maxsize=1)
def load_api_key_subjects() -> dict[str, str]:
    """Load stable log subjects without deriving them from secret key material."""
    subjects: dict[str, str] = {}
    if config.api_keys_json:
        try:
            raw_mapping = json.loads(config.api_keys_json)
            if isinstance(raw_mapping, dict):
                subject_index = 1
                for key, value in raw_mapping.items():
                    if str(value) not in ROLE_CAPABILITIES:
                        continue
                    subjects[str(key)] = f"key:configured-{subject_index}"
                    subject_index += 1
        except json.JSONDecodeError:
            pass

    if config.app_api_key:
        subjects.setdefault(config.app_api_key, "key:primary")

    return subjects


def _has_capability(role: str, capability: str) -> bool:
    capabilities = ROLE_CAPABILITIES.get(role, set())
    return "*" in capabilities or capability in capabilities


def validate_security_configuration() -> None:
    """Validate production security requirements at startup."""
    api_key_roles = load_api_key_roles()
    cors_origins = config.cors_origins

    if config.is_production and not api_key_roles:
        raise RuntimeError(
            "APP_API_KEY or API_KEYS_JSON is required when ENVIRONMENT is production"
        )

    if config.is_production and "*" in cors_origins:
        raise RuntimeError(
            "CORS_ALLOWED_ORIGINS must not include '*' when ENVIRONMENT is production"
        )

    if (
        config.is_production
        and config.agent_decision_provider.strip().lower() == "qwen"
        and not config.dashscope_api_key.strip()
    ):
        raise RuntimeError(
            "DASHSCOPE_API_KEY is required when AGENT_DECISION_PROVIDER=qwen in production"
        )

    redis_netloc = config.redis_url.split("://", 1)[-1].split("/", 1)[0]
    if (
        config.is_production
        and config.task_queue_backend == "redis"
        and not (config.redis_password.strip() or "@" in redis_netloc)
    ):
        raise RuntimeError("REDIS_PASSWORD or an authenticated REDIS_URL is required in production")


async def get_current_principal(
    request: Request,
    x_api_key: str | None = Header(default=None),
) -> Principal:
    """Resolve the current request principal."""
    api_key_roles = load_api_key_roles()

    if not api_key_roles:
        if config.is_production:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication is required in production",
                headers={"WWW-Authenticate": "ApiKey"},
            )
        principal = Principal(role="admin", subject="local-dev")
        request.state.principal = principal
        return principal

    if x_api_key and x_api_key in api_key_roles:
        principal = Principal(role=api_key_roles[x_api_key], subject=_api_key_subject(x_api_key))
        request.state.principal = principal
        logger.info(
            f"Authenticated request principal: subject={principal.subject}, role={principal.role}"
        )
        return principal

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API key",
        headers={"WWW-Authenticate": "ApiKey"},
    )


def require_capability(capability: str):
    """Return a FastAPI dependency that enforces one capability."""

    async def capability_dependency(
        request: Request,
        x_api_key: str | None = Header(default=None),
    ) -> Principal:
        principal = await get_current_principal(request, x_api_key)
        if _has_capability(principal.role, capability):
            return principal

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing capability: {capability}",
        )

    return capability_dependency


async def require_api_key(
    request: Request,
    x_api_key: str | None = Header(default=None),
) -> Principal:
    """Require an API key and return the associated principal."""
    return await get_current_principal(request, x_api_key)


def _api_key_subject(api_key: str) -> str:
    """Return a stable non-reversible API key subject for logs and audit rows."""
    return load_api_key_subjects().get(api_key, "key:unknown")
