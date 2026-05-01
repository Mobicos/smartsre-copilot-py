"""Audit log repository."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Session

from app.platform.persistence.database import get_engine
from app.platform.persistence.schema import AuditLog


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
        entry = AuditLog(
            request_id=request_id,
            method=method,
            path=path,
            status_code=status_code,
            subject=subject,
            role=role,
            client_ip=client_ip,
            user_agent=user_agent,
            error_message=error_message,
            created_at=datetime.now(UTC),
        )
        with Session(bind=get_engine()) as session:
            session.add(entry)
            session.commit()

    def log_request_with_session(
        self,
        session: Session,
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
        entry = AuditLog(
            request_id=request_id,
            method=method,
            path=path,
            status_code=status_code,
            subject=subject,
            role=role,
            client_ip=client_ip,
            user_agent=user_agent,
            error_message=error_message,
            created_at=datetime.now(UTC),
        )
        session.add(entry)


audit_log_repository = AuditLogRepository()
