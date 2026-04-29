"""Chat API schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    """Chat request payload."""

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={"example": {"Id": "session-123", "Question": "什么是向量数据库？"}},
    )

    id: str = Field(..., description="会话 ID", alias="Id")
    question: str = Field(..., description="用户问题", alias="Question")


class ClearRequest(BaseModel):
    """Clear chat session request."""

    model_config = ConfigDict(populate_by_name=True)

    session_id: str = Field(..., description="会话 ID", alias="sessionId")


class SessionInfoResponse(BaseModel):
    """Chat session information response."""

    session_id: str = Field(..., description="会话 ID")
    message_count: int = Field(..., description="消息数量")
    history: list[dict[str, str]] = Field(..., description="历史消息列表")


class ApiResponse(BaseModel):
    """Generic API response."""

    status: str = Field(..., description="状态")
    message: str = Field(..., description="消息")
    data: Any | None = Field(None, description="数据")
