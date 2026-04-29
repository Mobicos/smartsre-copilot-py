"""Audit log repository."""

from __future__ import annotations

from datetime import UTC, datetime

from app.platform.persistence.database import database_manager


def utc_now() -> str:
    """Return an ISO 8601 UTC timestamp."""
    return datetime.now(UTC).isoformat()


class AuditLogRepository:
    """Request audit log repository."""

    def log_request(
        self,
        *,
        request_id: str,
        method: str,
        path: str,
        status_code: int,
        subject: str | None,
        role: str | None,
        client_ip: str | None,
        user_agent: str | None,
        error_message: str | None = None,
    ) -> None:
        database_manager.initialize()
        with database_manager.get_connection() as connection:
            connection.execute(
                """
                INSERT INTO audit_logs (
                    request_id, method, path, status_code, subject, role,
                    client_ip, user_agent, error_message, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    method,
                    path,
                    status_code,
                    subject,
                    role,
                    client_ip,
                    user_agent,
                    error_message,
                    utc_now(),
                ),
            )


audit_log_repository = AuditLogRepository()
