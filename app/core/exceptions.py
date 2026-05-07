"""Application exception hierarchy and API-safe error payloads."""

from __future__ import annotations

from typing import Any


class AppException(Exception):
    """Base exception for expected application failures."""

    status_code = 500
    code = "app_error"
    public_message = "Application error"

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.public_message
        self.code = code or self.code
        self.status_code = status_code or self.status_code
        self.details = details or {}
        super().__init__(self.message)


class DomainException(AppException):
    """Domain or request invariant violation safe to return to callers."""

    status_code = 400
    code = "domain_error"
    public_message = "Invalid request"


class InfrastructureException(AppException):
    """Infrastructure or dependency failure that should not leak internals."""

    status_code = 500
    code = "infrastructure_error"
    public_message = "Service temporarily unavailable"
