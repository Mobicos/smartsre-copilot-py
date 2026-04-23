"""认证与访问控制。"""

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
    """当前请求主体。"""

    role: str
    subject: str


def is_auth_configured() -> bool:
    """当前是否已配置任一认证方式。"""
    return bool(config.app_api_key or config.api_keys_json)


@lru_cache(maxsize=1)
def load_api_key_roles() -> dict[str, str]:
    """加载 API Key 到角色的映射。"""
    mapping: dict[str, str] = {}
    if config.api_keys_json:
        try:
            raw_mapping = json.loads(config.api_keys_json)
            if isinstance(raw_mapping, dict):
                for key, value in raw_mapping.items():
                    role = str(value)
                    if role not in ROLE_CAPABILITIES:
                        logger.warning(f"忽略未知角色映射: {role}")
                        continue
                    mapping[str(key)] = role
            else:
                logger.warning("API_KEYS_JSON 不是对象结构，已忽略")
        except json.JSONDecodeError as exc:
            logger.warning(f"API_KEYS_JSON 解析失败，已忽略: {exc}")

    if config.app_api_key:
        mapping.setdefault(config.app_api_key, "admin")

    return mapping


def _has_capability(role: str, capability: str) -> bool:
    capabilities = ROLE_CAPABILITIES.get(role, set())
    return "*" in capabilities or capability in capabilities


def validate_security_configuration() -> None:
    """在启动阶段校验安全配置。"""
    api_key_roles = load_api_key_roles()
    cors_origins = config.cors_origins

    if config.is_production and not api_key_roles:
        raise RuntimeError("生产环境要求配置 APP_API_KEY 或 API_KEYS_JSON，当前认证配置为空")

    if config.is_production and "*" in cors_origins:
        raise RuntimeError("生产环境禁止使用通配符 CORS，请设置 CORS_ALLOWED_ORIGINS 为明确白名单")


async def get_current_principal(
    request: Request,
    x_api_key: str | None = Header(default=None),
) -> Principal:
    """解析当前请求主体。"""
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
        logger.info(f"认证成功: subject={principal.subject}, role={principal.role}")
        return principal

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API key",
        headers={"WWW-Authenticate": "ApiKey"},
    )


def require_capability(capability: str):
    """返回基于能力校验的依赖。"""

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
    """兼容旧用法的 API Key 校验。"""
    return await get_current_principal(request, x_api_key)
