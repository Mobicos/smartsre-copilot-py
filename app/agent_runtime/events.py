"""Typed runtime events for Native Agent runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AgentRuntimeEvent:
    """Runtime event emitted by the Native Agent loop."""

    type: str
    stage: str
    run_id: str
    message: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    status: str | None = None
    final_report: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to the API-compatible event shape."""
        data: dict[str, Any] = {
            "type": self.type,
            "stage": self.stage,
            "run_id": self.run_id,
        }
        if self.message:
            data["message"] = self.message
        if self.payload:
            data["payload"] = self.payload
        if self.status is not None:
            data["status"] = self.status
        if self.final_report is not None:
            data["final_report"] = self.final_report
        return data
