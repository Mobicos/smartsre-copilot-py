"""AIOps persistence tables."""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class AIOpsRun(SQLModel, table=True):
    __tablename__ = "aiops_runs"

    run_id: str = Field(primary_key=True)
    session_id: str
    status: str
    task_input: str
    report: str | None = None
    error_message: str | None = None
    created_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))
    updated_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))


class AIOpsRunEvent(SQLModel, table=True):
    __tablename__ = "aiops_run_events"
    __table_args__ = (sa.Index("idx_aiops_run_events_run_created", "run_id", "created_at", "id"),)

    id: int | None = Field(
        sa_column=sa.Column(sa.BigInteger, primary_key=True, autoincrement=True), default=None
    )
    run_id: str = Field(foreign_key="aiops_runs.run_id", ondelete="CASCADE")
    event_type: str
    stage: str
    message: str
    payload: str | None = None
    created_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))
