"""AIOps compatibility API schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AIOpsRequest(BaseModel):
    """AIOps diagnosis request."""

    model_config = ConfigDict(json_schema_extra={"example": {"session_id": "session-123"}})

    session_id: str | None = Field(default="default", description="会话ID，用于追踪诊断历史")
