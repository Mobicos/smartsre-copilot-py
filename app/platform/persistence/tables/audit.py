"""Audit persistence tables."""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_logs"
    __table_args__ = (sa.Index("idx_audit_logs_request_id", "request_id"),)

    id: int | None = Field(
        sa_column=sa.Column(sa.BigInteger, primary_key=True, autoincrement=True), default=None
    )
    request_id: str
    method: str
    path: str
    status_code: int
    subject: str | None = None
    role: str | None = None
    client_ip: str | None = None
    user_agent: str | None = None
    error_message: str | None = None
    created_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))
