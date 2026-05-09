from __future__ import annotations

from app.config import config
from app.infrastructure.knowledge.vector_store_manager import _milvus_string_literal
from app.security.auth import _api_key_subject, load_api_key_subjects
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
    load_api_key_subjects.cache_clear()
    monkeypatch.setattr(config, "app_api_key", "secret-api-key-value")
    monkeypatch.setattr(config, "api_keys_json", '{"viewer-secret": "viewer"}')

    subject = _api_key_subject("secret-api-key-value")
    json_subject = _api_key_subject("viewer-secret")

    assert subject == "key:primary"
    assert json_subject == "key:configured-1"
    assert "secret-api" not in subject
    assert subject == _api_key_subject("secret-api-key-value")
    load_api_key_subjects.cache_clear()
