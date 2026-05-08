"""Conversation persistence tables."""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class Session(SQLModel, table=True):
    __tablename__ = "sessions"

    session_id: str = Field(primary_key=True)
    title: str
    session_type: str = Field(default="chat")
    created_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))
    updated_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))


class Message(SQLModel, table=True):
    __tablename__ = "messages"
    __table_args__ = (
        sa.Index("idx_messages_session_created_at", "session_id", "created_at", "id"),
    )

    id: int | None = Field(
        sa_column=sa.Column(sa.BigInteger, primary_key=True, autoincrement=True), default=None
    )
    session_id: str = Field(foreign_key="sessions.session_id", ondelete="CASCADE")
    role: str
    content: str
    created_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))


class ChatToolEvent(SQLModel, table=True):
    __tablename__ = "chat_tool_events"
    __table_args__ = (
        sa.Index("idx_chat_tool_events_session_created", "session_id", "created_at", "id"),
    )

    id: int | None = Field(
        sa_column=sa.Column(sa.BigInteger, primary_key=True, autoincrement=True), default=None
    )
    session_id: str = Field(foreign_key="sessions.session_id", ondelete="CASCADE")
    exchange_id: str
    tool_name: str
    event_type: str
    payload: str | None = None
    created_at: datetime = Field(sa_column=sa.Column(sa.TIMESTAMP(timezone=True), nullable=False))
