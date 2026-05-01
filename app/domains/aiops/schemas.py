"""AIOps compatibility API schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AIOpsRequest(BaseModel):
    """AIOps diagnosis request.

    The compatibility endpoint accepts several frontend field names so older
    and newer clients can both pass the real incident description.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "session_id": "session-123",
                "goal": "API latency jumped from 80ms to 800ms after 10:20.",
            }
        },
    )

    session_id: str | None = Field(
        default="default",
        alias="sessionId",
        description="Conversation ID used to track diagnosis history.",
    )
    goal: str | None = Field(default=None, min_length=1, description="Diagnosis goal.")
    query: str | None = Field(default=None, min_length=1, description="User query.")
    question: str | None = Field(default=None, min_length=1, description="User question.")
    problem: str | None = Field(default=None, min_length=1, description="Problem statement.")

    def diagnosis_goal(self) -> str | None:
        """Return the first non-empty diagnosis goal from compatible clients."""
        for value in (self.goal, self.query, self.question, self.problem):
            if value and value.strip():
                return value.strip()
        return None
