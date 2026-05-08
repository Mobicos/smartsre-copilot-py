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
        principal = Principal(role=api_key_roles[x_api_key], subject=x_api_key[:8])
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
