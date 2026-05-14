"""Authentication and capability checks."""

from __future__ import annotations

import json
from dataclasses import dataclass

from fastapi import Header, HTTPException, Request, status
from loguru import logger

from app.core.config import AppSettings

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


# Cache keys that encode the settings values so tests can use different configs.
_api_key_roles_cache: tuple[str, str] | None = None
_api_key_subjects_cache: tuple[str, str] | None = None


def _clear_auth_caches() -> None:
    """Reset all manual caches in this module (test helper)."""
    global _api_key_roles_cache, _api_key_subjects_cache
    _api_key_roles_cache = None
    _api_key_subjects_cache = None


def _get_settings() -> AppSettings:
    return AppSettings.from_env()


def is_auth_configured(settings: AppSettings | None = None) -> bool:
    """Return whether API-key authentication is configured."""
    if settings is None:
        settings = _get_settings()
    return bool(settings.app_api_key or settings.api_keys_json)


def load_api_key_roles(settings: AppSettings | None = None) -> dict[str, str]:
    """Load API key to role mappings from configuration.

    Results are cached per (app_api_key, api_keys_json) tuple.
    """
    if settings is None:
        settings = _get_settings()
    cache_key = (settings.app_api_key, settings.api_keys_json)
    global _api_key_roles_cache
    if _api_key_roles_cache == cache_key:
        return {}
    mapping: dict[str, str] = {}
    if settings.api_keys_json:
        try:
            raw_mapping = json.loads(settings.api_keys_json)
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

    if settings.app_api_key:
        mapping.setdefault(settings.app_api_key, "admin")

    _api_key_roles_cache = cache_key
    return mapping


def load_api_key_subjects(settings: AppSettings | None = None) -> dict[str, str]:
    """Load stable log subjects without deriving them from secret key material.

    Results are cached per (app_api_key, api_keys_json) tuple.
    """
    if settings is None:
        settings = _get_settings()
    cache_key = (settings.app_api_key, settings.api_keys_json)
    global _api_key_subjects_cache
    if _api_key_subjects_cache == cache_key:
        return {}
    subjects: dict[str, str] = {}
    if settings.api_keys_json:
        try:
            raw_mapping = json.loads(settings.api_keys_json)
            if isinstance(raw_mapping, dict):
                subject_index = 1
                for key, value in raw_mapping.items():
                    if str(value) not in ROLE_CAPABILITIES:
                        continue
                    subjects[str(key)] = f"key:configured-{subject_index}"
                    subject_index += 1
        except json.JSONDecodeError:
            pass

    if settings.app_api_key:
        subjects.setdefault(settings.app_api_key, "key:primary")

    _api_key_subjects_cache = cache_key
    return subjects


# Expose cache_clear on both functions so tests can call
# load_api_key_roles.cache_clear() / load_api_key_subjects.cache_clear()
# without importing the private helper.
load_api_key_roles.cache_clear = _clear_auth_caches  # type: ignore[attr-defined]
load_api_key_subjects.cache_clear = _clear_auth_caches  # type: ignore[attr-defined]


def _has_capability(role: str, capability: str) -> bool:
    capabilities = ROLE_CAPABILITIES.get(role, set())
    return "*" in capabilities or capability in capabilities


def validate_security_configuration(settings: AppSettings | None = None) -> None:
    """Validate production security requirements at startup.

    In production (ENVIRONMENT=production|staging), this raises RuntimeError
    if critical security settings are missing or misconfigured.
    """
    if settings is None:
        settings = _get_settings()
    api_key_roles = load_api_key_roles(settings=settings)
    cors_origins = settings.cors_origins()

    if settings.is_production and not api_key_roles:
        raise RuntimeError(
            "APP_API_KEY or API_KEYS_JSON is required when ENVIRONMENT is production"
        )

    if settings.is_production and "*" in cors_origins:
        raise RuntimeError(
            "CORS_ALLOWED_ORIGINS must not include '*' when ENVIRONMENT is production"
        )

    if (
        settings.is_production
        and settings.agent_decision_provider.strip().lower() == "qwen"
        and not settings.dashscope_api_key.strip()
    ):
        raise RuntimeError(
            "DASHSCOPE_API_KEY is required when AGENT_DECISION_PROVIDER=qwen in production"
        )

    redis_netloc = settings.redis_url.split("://", 1)[-1].split("/", 1)[0]
    if (
        settings.is_production
        and settings.task_queue_backend == "redis"
        and not (settings.redis_password.strip() or "@" in redis_netloc)
    ):
        raise RuntimeError("REDIS_PASSWORD or an authenticated REDIS_URL is required in production")


async def get_current_principal(
    request: Request,
    x_api_key: str | None = Header(default=None),
    settings: AppSettings | None = None,
) -> Principal:
    """Resolve the current request principal."""
    if settings is None:
        settings = _get_settings()
    api_key_roles = load_api_key_roles(settings=settings)

    if not api_key_roles:
        if settings.is_production:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="生产环境需要认证",
                headers={"WWW-Authenticate": "ApiKey"},
            )
        principal = Principal(role="admin", subject="local-dev")
        request.state.principal = principal
        return principal

    if x_api_key and x_api_key in api_key_roles:
        principal = Principal(
            role=api_key_roles[x_api_key], subject=_api_key_subject(x_api_key, settings=settings)
        )
        request.state.principal = principal
        logger.info(
            f"Authenticated request principal: subject={principal.subject}, role={principal.role}"
        )
        return principal

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效的 API 密钥",
        headers={"WWW-Authenticate": "ApiKey"},
    )


def require_capability(capability: str, settings: AppSettings | None = None):
    """Return a FastAPI dependency that enforces one capability."""
    _settings = settings if settings is not None else _get_settings()

    async def capability_dependency(
        request: Request,
        x_api_key: str | None = Header(default=None),
    ) -> Principal:
        principal = await get_current_principal(request, x_api_key, settings=_settings)
        if _has_capability(principal.role, capability):
            return principal

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"缺少能力：{capability}",
        )

    return capability_dependency


async def require_api_key(
    request: Request,
    x_api_key: str | None = Header(default=None),
    settings: AppSettings | None = None,
) -> Principal:
    """Require an API key and return the associated principal."""
    return await get_current_principal(request, x_api_key, settings=settings)


def _api_key_subject(api_key: str, settings: AppSettings | None = None) -> str:
    """Return a stable non-reversible API key subject for logs and audit rows."""
    return load_api_key_subjects(settings=settings).get(api_key, "key:unknown")
