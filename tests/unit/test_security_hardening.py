from __future__ import annotations

from app.infrastructure.knowledge.vector_store_manager import _milvus_string_literal
from app.security.auth import _api_key_subject
from app.security.rate_limit import RateLimiter, RateLimitPolicy


def test_milvus_string_literal_escapes_injected_expression_parts():
    payload = 'foo" || metadata["tenant"] != "prod\\bar\nnext'

    literal = _milvus_string_literal(payload)

    assert literal == '"foo\\" || metadata[\\"tenant\\"] != \\"prod\\\\bar\\nnext"'
    assert literal.startswith('"')
    assert literal.endswith('"')


def test_rate_limiter_isolates_keys_and_enforces_burst():
    limiter = RateLimiter()
    policy = RateLimitPolicy(requests_per_minute=1, burst=2)

    assert limiter.allow("stream:principal:a", policy) is True
    assert limiter.allow("stream:principal:a", policy) is True
    assert limiter.allow("stream:principal:a", policy) is False
    assert limiter.allow("stream:principal:b", policy) is True


def test_api_key_subject_is_stable_identifier_not_key_derived(monkeypatch):
    from app.core.config import AppSettings

    # Clear manual caches used by load_api_key_subjects and load_api_key_roles
    from app.security import auth

    auth._api_key_roles_cache = None
    auth._api_key_subjects_cache = None

    def patched_from_env():
        # Start from defaults, override the two fields we want to test
        import dataclasses

        defaults = AppSettings.defaults()
        overrides = {
            "app_api_key": "secret-api-key-value",
            "api_keys_json": '{"viewer-secret": "viewer"}',
        }
        field_names = {f.name for f in dataclasses.fields(AppSettings)}
        kwargs = {
            name: overrides[name] if name in overrides else getattr(defaults, name)
            for name in field_names
        }
        return AppSettings(**kwargs)

    monkeypatch.setattr(AppSettings, "from_env", staticmethod(patched_from_env))

    subject = _api_key_subject("secret-api-key-value")
    # Clear caches so second call performs fresh load (pre-existing cache behavior)
    auth._api_key_subjects_cache = None
    auth._api_key_roles_cache = None

    json_subject = _api_key_subject("viewer-secret")

    assert subject == "key:primary"
    assert json_subject == "key:configured-1"
    assert "secret-api" not in subject
    # Clean up
    auth._api_key_roles_cache = None
    auth._api_key_subjects_cache = None
