from __future__ import annotations

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.config import config
from app.security.auth import (
    _has_capability,
    get_current_principal,
    load_api_key_roles,
    load_api_key_subjects,
    validate_security_configuration,
)


@pytest.fixture(autouse=True)
def clear_auth_cache():
    load_api_key_roles.cache_clear()
    load_api_key_subjects.cache_clear()
    yield
    load_api_key_roles.cache_clear()
    load_api_key_subjects.cache_clear()


def _request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": []})


def test_production_requires_configured_api_key(monkeypatch):
    monkeypatch.setattr(config, "environment", "prod")
    monkeypatch.setattr(config, "app_api_key", "")
    monkeypatch.setattr(config, "api_keys_json", "")

    with pytest.raises(RuntimeError, match="APP_API_KEY"):
        validate_security_configuration()


def test_production_rejects_wildcard_cors(monkeypatch):
    monkeypatch.setattr(config, "environment", "prod")
    monkeypatch.setattr(config, "app_api_key", "admin-token")
    monkeypatch.setattr(config, "api_keys_json", "")
    monkeypatch.setattr(config, "cors_allowed_origins", "*")

    with pytest.raises(RuntimeError, match="CORS_ALLOWED_ORIGINS"):
        validate_security_configuration()


def test_load_api_key_roles_ignores_unknown_roles(monkeypatch):
    monkeypatch.setattr(config, "app_api_key", "admin-token")
    monkeypatch.setattr(
        config,
        "api_keys_json",
        '{"viewer-token": "viewer", "bad-token": "unknown"}',
    )

    roles = load_api_key_roles()

    assert roles == {
        "viewer-token": "viewer",
        "admin-token": "admin",
    }


def test_capability_mapping_blocks_unauthorized_role():
    assert _has_capability("operator", "aiops:run")
    assert not _has_capability("viewer", "chat:use")
    assert _has_capability("admin", "anything")


async def test_local_dev_without_api_keys_gets_admin_principal(monkeypatch):
    monkeypatch.setattr(config, "environment", "dev")
    monkeypatch.setattr(config, "app_api_key", "")
    monkeypatch.setattr(config, "api_keys_json", "")

    principal = await get_current_principal(_request())

    assert principal.role == "admin"
    assert principal.subject == "local-dev"


async def test_configured_api_keys_reject_missing_header(monkeypatch):
    monkeypatch.setattr(config, "environment", "dev")
    monkeypatch.setattr(config, "app_api_key", "admin-token")
    monkeypatch.setattr(config, "api_keys_json", "")

    with pytest.raises(HTTPException) as exc_info:
        await get_current_principal(_request())

    assert exc_info.value.status_code == 401
